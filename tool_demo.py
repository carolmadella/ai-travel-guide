"""
tool_demo.py
Proof of concept: the AI decides when to call two simple tools.
Every decision is printed so we can see what the agent chose.
"""

import random
from datetime import date

import anthropic
from dotenv import load_dotenv

load_dotenv()                    # read ANTHROPIC_API_KEY from .env
client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"


# ---------------------------------------------------------------
# 1. The tools: normal Python functions
# ---------------------------------------------------------------

def get_today_date():
    """Return today's date as text, for example 'Thursday, November 05, 2026'."""
    return date.today().strftime("%A, %B %d, %Y")


def roll_dice(sides):
    """Roll one die with the given number of sides and return the result."""
    return str(random.randint(1, sides))


# ---------------------------------------------------------------
# 2. Tool descriptions: what the AI reads to decide which tool to use
# ---------------------------------------------------------------

TOOLS = [
    {
        "name": "get_today_date",
        "description": "Get today's date. Use this whenever the user asks about "
                       "today's date or the day of the week.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "roll_dice",
        "description": "Roll one die and return the number it lands on.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sides": {"type": "integer", "description": "Number of sides, e.g. 6 or 20"}
            },
            "required": ["sides"],
        },
    },
]


def run_tool(name, arguments):
    """Run the Python function that matches the tool the AI chose."""
    if name == "get_today_date":
        return get_today_date()
    if name == "roll_dice":
        return roll_dice(int(arguments["sides"]))
    return f"Error: unknown tool '{name}'"


# ---------------------------------------------------------------
# 3. The agent loop
# ---------------------------------------------------------------

def ask_agent(question):
    """Send the question to the AI. While the AI asks for tools, run them
    and send the results back. Stop when the AI gives its final answer."""
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=500, tools=TOOLS, messages=messages
        )

        # The AI is done choosing tools: print its answer and stop
        if response.stop_reason != "tool_use":
            if len(messages) == 1:
                print("[Agent decided] No tool needed")
            for block in response.content:
                if block.type == "text":
                    print("Agent:", block.text)
            return

        # The AI chose one or more tools: keep its turn in the conversation
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[Agent chose tool] {block.name}({block.input})")
                result = run_tool(block.name, block.input)
                print(f"[Tool result]      {result}")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
        # Send the results back so the AI can continue
        messages.append({"role": "user", "content": tool_results})


def main():
    """Ask questions until the user types 'quit'."""
    print("Tool demo. Type a question, or 'quit' to exit.")
    while True:
        question = input("\nYou: ").strip()
        if question.lower() == "quit":
            break
        if question:
            ask_agent(question)


if __name__ == "__main__":
    main()