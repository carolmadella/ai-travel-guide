"""
agent.py
AI Travel Guide - a command-line AI agent. The AI model decides which
tools to call (and with what arguments) to answer each question.
Every decision is printed so you can see what the agent chose.
"""

import os
import sys

import anthropic
from dotenv import load_dotenv

from travel_tools import TOOLS, run_tool

load_dotenv()                    # read ANTHROPIC_API_KEY from .env

# Stop early with a clear message if the API key is missing
if not os.getenv("ANTHROPIC_API_KEY"):
    print("[Error] No API key found. Create a .env file in this folder with the line:")
    print("        ANTHROPIC_API_KEY=your-key-here")
    sys.exit(1)

client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"

# Safety limit: the agent may call tools at most this many rounds per
# question, so it can never get stuck in an endless loop
MAX_TOOL_ROUNDS = 6

# Instructions the AI follows for the whole conversation
SYSTEM_PROMPT = (
    "You are a friendly travel guide. Use your tools to get real data "
    "instead of guessing. "
    "Only recommend or mention attractions that the find_attractions tool returned. "
    "Never name other places from your own memory, not even as examples. "
    "If a search finds nothing, you may try once more with a larger radius "
    "(up to 20 km). If it still finds nothing, say so honestly. "
    "Recommend 3 to 5 places that best match the user's interests and briefly "
    "explain why. If a tool returns an error, explain the problem to the user "
    "in simple words."
)


def call_ai(messages):
    """Send the conversation to the AI. Returns the response, or None if
    something went wrong (after printing a message the user can act on)."""
    try:
        return client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
    # The specific errors come first, because they are kinds of APIError
    except anthropic.AuthenticationError:
        print("[Error] The API key was rejected. Check ANTHROPIC_API_KEY in your .env file.")
    except anthropic.APIConnectionError:
        print("[Error] Could not connect to the AI service. Check your internet connection.")
    except anthropic.RateLimitError:
        print("[Error] Too many requests right now. Wait a minute and try again.")
    except anthropic.APIStatusError as error:
        print(f"[Error] The AI service had a problem (status {error.status_code}). Try again.")
    except anthropic.APIError as error:
        print(f"[Error] Unexpected problem with the AI service: {error}")
    return None


def ask_agent(messages, question):
    """Send one question to the AI and let it call tools until it has an answer.
    The AI's choices and each tool result are printed so we can see them."""
    start_length = len(messages)      # so we can undo this turn if something fails
    messages.append({"role": "user", "content": question})
    used_a_tool = False

    for round_number in range(MAX_TOOL_ROUNDS):
        response = call_ai(messages)
        if response is None:
            del messages[start_length:]       # forget the unfinished turn
            return

        # Keep the AI's turn in the conversation history
        messages.append({"role": "assistant", "content": response.content})

        # The AI is done with tools and is giving its final answer
        if response.stop_reason != "tool_use":
            if not used_a_tool:
                print("[Agent decided] No tool needed")
            texts = [block.text for block in response.content if block.type == "text"]
            if not texts:
                print("[Note] The agent did not return an answer. Please ask again.")
                del messages[start_length:]
                return
            for text in texts:
                print("Agent:", text)
            if response.stop_reason == "max_tokens":
                print("[Note] The answer was cut off because it was too long.")
            return

        # The AI asked for one or more tools: run each one and send back the results
        used_a_tool = True
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[Agent chose tool] {block.name}({block.input})")
                result = run_tool(block.name, block.input)
                print(f"[Tool result]      {result}")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )

        # Unexpected response: the AI said it wanted a tool but did not name one
        if not tool_results:
            print("[Note] The agent sent an unexpected response. Please ask again.")
            del messages[start_length:]
            return
        messages.append({"role": "user", "content": tool_results})

    # The loop ended without a final answer: the safety limit was reached
    print(f"[Stopped] The agent used {MAX_TOOL_ROUNDS} tool rounds without "
          "finishing. Please try a simpler question.")
    del messages[start_length:]               # forget the unfinished turn


def main():
    """Ask questions until the user types 'quit'. The same messages list is
    reused, so the agent remembers the whole conversation."""
    print("AI Travel Guide. Ask about a place, or type 'quit' to exit.")
    messages = []
    while True:
        try:
            question = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D: exit politely instead of showing a traceback
            print("\nGoodbye!")
            break
        if question.lower() == "quit":
            print("Goodbye!")
            break
        if question:
            ask_agent(messages, question)


if __name__ == "__main__":
    main()