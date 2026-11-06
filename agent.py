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

# Instructions the AI follows for the whole conversation
SYSTEM_PROMPT = (
    "You are a friendly travel guide. Use your tools to get real data "
    "instead of guessing. If a tool returns an error, explain the problem "
    "to the user in simple words."
)


def ask_agent(messages, question):
    """Add the question to the conversation and send it to the AI. While the
    AI asks for tools, run them and send the results back. Stop when the AI
    gives its final answer. 'messages' keeps the whole conversation, so the
    AI remembers earlier questions and answers."""
    messages.append({"role": "user", "content": question})
    used_a_tool = False

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        # Keep the AI's turn in the conversation history
        messages.append({"role": "assistant", "content": response.content})

        # The AI is done choosing tools: print its answer and stop
        if response.stop_reason != "tool_use":
            if not used_a_tool:
                print("[Agent decided] No tool needed")
            for block in response.content:
                if block.type == "text":
                    print("Agent:", block.text)
            return

        # The AI chose one or more tools: run each one and collect the results
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
        # Send the results back so the AI can continue
        messages.append({"role": "user", "content": tool_results})


def main():
    """Ask questions until the user types 'quit'. The same conversation
    history is used for every question, so follow-up questions work."""
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