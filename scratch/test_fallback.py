"""Smoke test: simulate the new fallback chain by calling send_chat with role=general.
Both Ollama keys will 429, then OpenRouter should succeed via the chain.
"""
import sys, os
sys.path.insert(0, r"c:\Users\atubt\Documents\Codex\Louis-Agent")

# Load .env
from pathlib import Path
env_path = Path(r"c:\Users\atubt\Documents\Codex\Louis-Agent\.env")
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip("'\"")

import louis

print(f"Ollama keys:     {len(louis._ollama_keys)}")
print(f"OpenRouter keys: {len(louis._openrouter_keys)}")
print()

msgs = [
    {"role": "system", "content": "Reply with just 'OK'."},
    {"role": "user",   "content": "Say OK"},
]

try:
    answer, provider = louis.send_chat(msgs, "gemma4:31b", "https://ollama.com",
                                        temperature=0.1, role="general")
    print(f"\nSUCCESS via: {provider}")
    print(f"Reply:       {answer[:100]}")
except louis.SetupFault as e:
    print(f"\nFAILED: {e}")
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
