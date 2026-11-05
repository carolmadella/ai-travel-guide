"""
test_api.py
First test: send one message to the Claude API and print the reply.
"""

import anthropic
from dotenv import load_dotenv

# Read ANTHROPIC_API_KEY from the .env file (it is never written in the code)
load_dotenv()

# The client finds the key automatically
client = anthropic.Anthropic()

# Send one message to the model and wait for the reply
message = client.messages.create(
    model="claude-haiku-5-5",   # the fastest and cheapest model, good for testing
    max_tokens=200,
    messages=[
        {"role": "user", "content": "In one sentence, what is an AI agent?"}
    ],
)

# The reply comes back as a list of content blocks; print the text ones
for block in message.content:
    if block.type == "text":
        print(block.text)

# Tokens are what the API charges for, so it's good to watch them
print(f"Tokens used: {message.usage.input_tokens} in, {message.usage.output_tokens} out")