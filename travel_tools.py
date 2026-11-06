"""
travel_tools.py
The real tools the travel agent can use. Each tool is a normal Python
function that calls a free web API and returns its answer as JSON text.
"""

import json

import requests

# Every request gives up after 10 seconds instead of waiting forever
TIMEOUT_SECONDS = 10

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def find_location(place):
    """Turn a city or town name into coordinates using the free
    Open-Meteo Geocoding API. Returns up to 3 matches, because names
    can repeat (for example, there is a Paris in France and in Texas)."""
    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": place, "count": 3, "language": "en", "format": "json"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()      # turn HTTP errors (like 500) into exceptions
    except requests.RequestException as error:
        return json.dumps({"error": f"Could not reach the location service: {error}"})

    results = response.json().get("results", [])
    if not results:
        return json.dumps({"error": f"No location found for '{place}'."})

    # Keep only the fields the AI needs
    matches = [
        {
            "name": result["name"],
            "region": result.get("admin1", ""),
            "country": result.get("country", ""),
            "latitude": result["latitude"],
            "longitude": result["longitude"],
        }
        for result in results
    ]
    return json.dumps({"matches": matches})


# Description of each tool for the AI. The AI reads only this, never the code above.
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
]


def run_tool(name, arguments):
    """Run the Python function that matches the tool the AI chose."""
    if name == "find_location":
        return find_location(arguments.get("place", ""))
    return json.dumps({"error": f"Unknown tool '{name}'."})


# Test the tools on their own, without the AI: python travel_tools.py
if __name__ == "__main__":
    for test_place in ["Chicago", "Paris, France", "Xyzzyville"]:
        print(test_place, "->", find_location(test_place))