"""
travel_tools.py
The three tools the travel agent can use. Each tool is a normal Python
function that calls a free web API and returns its answer as JSON text.
Every tool checks its inputs and turns problems into error messages
the AI can read, instead of crashing the program.
"""

import json
import math
from pathlib import Path

import requests

# Every request gives up after this many seconds instead of waiting forever
TIMEOUT_SECONDS = 10

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# OpenStreetMap's public servers are sometimes busy, so we try two of them
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
FALLBACK_FILE = Path(__file__).parent / "attractions_fallback.json"

# Public APIs ask programs to identify themselves
HEADERS = {"User-Agent": "ai-travel-guide-student-project/1.0"}

# The only attraction categories the AI may ask for, and the
# OpenStreetMap tag filter that finds each one
CATEGORY_FILTERS = {
    "museum": '["tourism"="museum"]',
    "gallery": '["tourism"="gallery"]',
    "park": '["leisure"="park"]',
    "historic": '["historic"~"^(monument|memorial|castle|fort|ruins|archaeological_site|city_gate)$"]',
    "viewpoint": '["tourism"="viewpoint"]',
    "attraction": '["tourism"="attraction"]',
}

MAX_RESULTS = 10          # never send the AI more than 10 attractions
MAX_RADIUS_KM = 20        # searching a bigger area is slow and not useful

# Common short names for countries, matched to their 2-letter country codes
COUNTRY_NICKNAMES = {"usa": "us", "america": "us", "uk": "gb", "england": "gb", "britain": "gb"}


# ---------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------

def check_text(value, field, max_length=100):
    """Make sure a text argument is present and not too long."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field}' must be a non-empty text value.")
    if len(value) > max_length:
        raise ValueError(f"'{field}' must be {max_length} characters or fewer.")
    return value.strip()


def check_coordinates(latitude, longitude):
    """Make sure latitude and longitude are real numbers in valid ranges."""
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude must be -90 to 90 and longitude -180 to 180.")
    return latitude, longitude


def distance_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two points on Earth (haversine formula)."""
    earth_radius_km = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


# ---------------------------------------------------------------
# Tool 1: find_location
# ---------------------------------------------------------------

def find_location(place):
    """Turn a city or town name into coordinates using the free
    Open-Meteo Geocoding API. Returns up to 3 matches, because names
    can repeat (for example, there is a Paris in France and in Texas).
    Accepts "City" or "City, Region/Country", like "Boston, USA"."""
    place = check_text(place, "place")
    # The geocoder only understands the city name, so we search for the part
    # before the first comma and use the rest to choose the right match
    city, _, hint = place.partition(",")
    city = city.strip() or place
    hint = hint.strip().lower()
    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 10, "language": "en", "format": "json"},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()      # turn HTTP errors (like 500) into exceptions
        results = response.json().get("results", [])
    except (requests.RequestException, ValueError) as error:
        # ValueError covers a response that is not valid JSON
        return json.dumps({"error": f"Could not get data from the location service: {error}"})

    matches = []
    for result in results:
        # Skip any result that is missing the fields we need
        if "latitude" not in result or "longitude" not in result:
            continue
        matches.append({
            "name": result.get("name", city),
            "region": result.get("admin1", ""),
            "country": result.get("country", ""),
            "country_code": result.get("country_code", ""),
            "latitude": result["latitude"],
            "longitude": result["longitude"],
        })

    # If the user gave a region or country, keep only the matches that fit it
    if hint:
        hint_words = set(hint.replace(",", " ").split())
        hint_words |= {COUNTRY_NICKNAMES[word] for word in hint_words if word in COUNTRY_NICKNAMES}
        fitting = [
            match for match in matches
            if (match["region"] and match["region"].lower() in hint)
            or (match["country"] and match["country"].lower() in hint)
            or match["country_code"].lower() in hint_words
        ]
        if fitting:
            # Matches whose region was named (like "Texas") go first
            fitting.sort(key=lambda match: not (match["region"] and match["region"].lower() in hint))
            matches = fitting

    for match in matches:
        del match["country_code"]        # only needed for the check above
    if not matches:
        return json.dumps({"error": f"No location found for '{place}'."})
    return json.dumps({"matches": matches[:3]})


# ---------------------------------------------------------------
# Tool 2: find_attractions
# ---------------------------------------------------------------

def search_openstreetmap(latitude, longitude, category, radius_km):
    """Ask OpenStreetMap (Overpass API) for named places of one category
    near the coordinates. Returns a list of attractions, closest first."""
    radius_m = int(radius_km * 1000)
    query = (
        "[out:json][timeout:20];"
        f'nwr{CATEGORY_FILTERS[category]}["name"](around:{radius_m},{latitude},{longitude});'
        "out center 40;"
    )
    last_error = None
    for url in OVERPASS_URLS:
        try:
            response = requests.post(
                url, data={"data": query}, headers=HEADERS, timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])
            break                     # this server worked, so stop trying others
        except (requests.RequestException, ValueError) as error:
            last_error = error        # remember the problem and try the next server
    else:
        raise last_error              # every server failed: let the caller use the backup

    attractions = {}
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        # Points have lat/lon; areas and buildings have a "center" instead
        point = element.get("center", element)
        if not name or "lat" not in point or "lon" not in point:
            continue
        attractions[name] = {      # using the name as the key removes duplicates
            "name": name,
            "category": category,
            "distance_km": round(distance_km(latitude, longitude, point["lat"], point["lon"]), 1),
            "website": tags.get("website", ""),
        }
    return sorted(attractions.values(), key=lambda place: place["distance_km"])


def search_fallback(latitude, longitude, category, radius_km):
    """Search the small backup dataset. Used only when OpenStreetMap fails."""
    try:
        with open(FALLBACK_FILE, encoding="utf-8") as file:
            cities = json.load(file)["cities"]
    except (OSError, ValueError, KeyError) as error:
        # Missing or broken backup file: report no results instead of crashing
        print(f"[Warning] Backup dataset could not be read ({type(error).__name__})")
        return []
    results = []
    for city in cities:
        for place in city["attractions"]:
            km = distance_km(latitude, longitude, place["latitude"], place["longitude"])
            if place["category"] == category and km <= radius_km:
                results.append({
                    "name": place["name"],
                    "category": category,
                    "distance_km": round(km, 1),
                    "website": "",
                })
    return sorted(results, key=lambda place: place["distance_km"])


def find_attractions(latitude, longitude, category, radius_km=5):
    """Find real attractions of one category near a location. Uses
    OpenStreetMap first and the backup dataset if OpenStreetMap fails."""
    latitude, longitude = check_coordinates(latitude, longitude)
    if category not in CATEGORY_FILTERS:
        raise ValueError(f"'category' must be one of: {', '.join(CATEGORY_FILTERS)}.")
    try:
        radius_km = float(radius_km)
    except (TypeError, ValueError):
        raise ValueError("'radius_km' must be a number.")
    radius_km = min(max(radius_km, 1), MAX_RADIUS_KM)    # keep it between 1 and 20 km

    try:
        attractions = search_openstreetmap(latitude, longitude, category, radius_km)
        source = "OpenStreetMap"
    except (requests.RequestException, ValueError) as error:
        print(f"[Warning] OpenStreetMap unavailable ({type(error).__name__}), using backup data")
        attractions = search_fallback(latitude, longitude, category, radius_km)
        source = "backup dataset (OpenStreetMap was unavailable)"

    if not attractions:
        return json.dumps({
            "source": source,
            "attractions": [],
            "message": f"No {category} attractions found within {radius_km:g} km.",
        })
    return json.dumps({"source": source, "attractions": attractions[:MAX_RESULTS]})


# ---------------------------------------------------------------
# Tool 3: get_weather
# ---------------------------------------------------------------

# Open-Meteo sends a number for the weather; these are the plain-English meanings
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def get_weather(latitude, longitude, days=3, units="fahrenheit"):
    """Get the daily weather forecast (up to 7 days) for a location using
    the free Open-Meteo Forecast API."""
    latitude, longitude = check_coordinates(latitude, longitude)
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ValueError("'days' must be a whole number.")
    days = min(max(days, 1), 7)                          # keep it between 1 and 7
    if units not in ("celsius", "fahrenheit"):
        raise ValueError("'units' must be 'celsius' or 'fahrenheit'.")

    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max",
                "temperature_unit": units,
                "timezone": "auto",                      # dates in the city's own time zone
                "forecast_days": days,
            },
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        daily = response.json()["daily"]
        forecast = []
        for i, date in enumerate(daily["time"]):
            forecast.append({
                "date": date,
                "conditions": WEATHER_CODES.get(daily["weather_code"][i], "unknown"),
                "high": daily["temperature_2m_max"][i],
                "low": daily["temperature_2m_min"][i],
                "chance_of_rain_percent": daily["precipitation_probability_max"][i],
            })
    except (requests.RequestException, ValueError) as error:
        return json.dumps({"error": f"Could not get data from the weather service: {error}"})
    except (KeyError, IndexError, TypeError):
        # The service answered, but not in the shape we expected
        return json.dumps({"error": "The weather service sent an unexpected response."})

    unit_symbol = "°F" if units == "fahrenheit" else "°C"
    return json.dumps({"temperature_unit": unit_symbol, "forecast": forecast})


# ---------------------------------------------------------------
# Tool descriptions for the AI. The AI reads only these, never the code above.
# ---------------------------------------------------------------

TOOLS = [
    {
        "name": "find_location",
        "description": (
            "Find the coordinates (latitude and longitude) of a city or town. "
            "Use this first whenever the user mentions a place, because the other "
            "tools need coordinates. Returns up to 3 matches; pick the one that fits "
            "what the user asked for (for example, the right country)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {
                    "type": "string",
                    "description": "City or town name, optionally with the country, e.g. 'Paris, France'",
                }
            },
            "required": ["place"],
        },
    },
    {
        "name": "find_attractions",
        "description": (
            "Find real, named attractions of ONE category near a latitude and longitude, "
            "using OpenStreetMap data. Returns names and distances, closest first. "
            "Call it again with a different category if the user is interested in more "
            "than one kind of place. Only recommend attractions that this tool returns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude from find_location"},
                "longitude": {"type": "number", "description": "Longitude from find_location"},
                "category": {
                    "type": "string",
                    "enum": list(CATEGORY_FILTERS),
                    "description": "Kind of attraction to search for",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers, 1 to 20 (default 5)",
                },
            },
            "required": ["latitude", "longitude", "category"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get the daily weather forecast (1 to 7 days, starting today) for a "
            "latitude and longitude. Use it when the user asks about weather, what to "
            "pack, or whether to plan indoor or outdoor activities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude from find_location"},
                "longitude": {"type": "number", "description": "Longitude from find_location"},
                "days": {"type": "integer", "description": "Number of days, 1 to 7 (default 3)"},
                "units": {
                    "type": "string",
                    "enum": ["fahrenheit", "celsius"],
                    "description": "Temperature unit (default fahrenheit)",
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
]


def run_tool(name, arguments):
    """Run the Python function that matches the tool the AI chose.
    Bad or missing arguments become an error message for the AI."""
    try:
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
        if name == "find_location":
            return find_location(arguments.get("place"))
        if name == "find_attractions":
            return find_attractions(
                arguments.get("latitude"),
                arguments.get("longitude"),
                arguments.get("category"),
                arguments.get("radius_km", 5),
            )
        if name == "get_weather":
            return get_weather(
                arguments.get("latitude"),
                arguments.get("longitude"),
                arguments.get("days", 3),
                arguments.get("units", "fahrenheit"),
            )
        return json.dumps({"error": f"Unknown tool '{name}'."})
    except ValueError as error:
        return json.dumps({"error": f"Invalid arguments for {name}: {error}"})


# Test the tools on their own, without the AI: python travel_tools.py
if __name__ == "__main__":
    print(run_tool("find_location", {"place": "Chicago"}))
    print(run_tool("find_location", {"place": "Paris, USA"}))
    print(run_tool("find_attractions", {"latitude": 41.8781, "longitude": -87.6298, "category": "museum"}))
    print(run_tool("find_attractions", {"latitude": 41.8781, "longitude": -87.6298, "category": "casino"}))
    print(run_tool("find_attractions", {"latitude": "abc", "longitude": -87.6298, "category": "park"}))
    print(run_tool("get_weather", {"latitude": 41.8781, "longitude": -87.6298, "days": 3}))