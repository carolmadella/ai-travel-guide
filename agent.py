"""
agent.py
AI Travel Guide - a command-line AI agent. The AI model decides which
tools to call (and with what arguments) to answer each question.
Every decision is printed so you can see what the agent chose.
"""

import anthropic
from dotenv import load_dotenv

from travel_tools import TOOLS, run_tool

load_dotenv()                    # read ANTHROPIC_API_KEY from .env
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


def ask_agent(messages, question):
    """Send one question to the AI and let it call tools until it has an answer.
    The AI's choices and each tool result are printed so we can see them."""
    start_length = len(messages)      # so we can undo this turn if something fails
    messages.append({"role": "user", "content": question})
    used_a_tool = False

    for round_number in range(MAX_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except anthropic.APIError as error:
            # Network problem, bad API key, server busy, etc.
            print(f"[Error] Could not reach the AI service: {error}")
            del messages[start_length:]       # forget the unfinished turn
            return

        # Keep the AI's turn in the conversation history
        messages.append({"role": "assistant", "content": response.content})

        # The AI is done with tools and is giving its final answer
        if response.stop_reason != "tool_use":
            if not used_a_tool:
                print("[Agent decided] No tool needed")
            for block in response.content:
                if block.type == "text":
                    print("Agent:", block.text)
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
        question = input("\nYou: ").strip()
        if question.lower() == "quit":
            print("Goodbye!")
            break
        if question:
            ask_agent(messages, question)


if __name__ == "__main__":
    main()