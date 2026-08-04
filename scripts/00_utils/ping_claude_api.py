"""Minimal connectivity check for the rotated ANTHROPIC_API_KEY.
Not a tip-verifier training call -- see tip_verifier.py's docstring gate and the
project's coaching-tip-training-deferred decision."""
from anthropic import Anthropic

ENV_PATH = r'C:\Users\jackp\tennis_app\backend\.env'


def read_env_var(path, key):
    with open(path) as f:
        for line in f:
            if line.startswith(f'{key}='):
                return line.split('=', 1)[1].strip()
    raise KeyError(key)


client = Anthropic(api_key=read_env_var(ENV_PATH, 'ANTHROPIC_API_KEY'))
resp = client.messages.create(
    model='claude-sonnet-5',
    max_tokens=16,
    messages=[{'role': 'user', 'content': 'Reply with exactly: pong'}],
)
print(resp.content[0].text)
