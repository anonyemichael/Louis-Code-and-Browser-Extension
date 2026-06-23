"""Test all 4 API keys individually."""
import json, urllib.request, urllib.error, sys, time

# ── Keys from .env ──
OLLAMA_KEYS = [
    "337f9f6fd61f404688ee08691b1fa215.rVcdFp4VyXY09sojSxFGZXlm",
    "e4eb997e22714150942d4a5ac5f29c19.ZftAGUetj2ULF5IiVlmPINU8",
]
OPENROUTER_KEYS = [
    "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",
    "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",
]

OLLAMA_URL    = "https://ollama.com/api/chat"
OLLAMA_MODEL  = "gemma4:31b"    # smallest/fastest to test quickly

OR_URL   = "https://openrouter.ai/api/v1/chat/completions"
OR_MODEL = "google/gemma-4-31b-it:free"

TINY_MSG = [{"role": "user", "content": "Say OK"}]


def post(url, headers, payload, timeout=30):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, str(e)
    except Exception as e:
        return None, None, str(e)


def test_ollama(key, idx):
    print(f"\n{'='*60}")
    print(f"  Ollama Key #{idx}:  ...{key[-12:]}")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"model": OLLAMA_MODEL, "messages": TINY_MSG, "stream": False,
               "options": {"temperature": 0.1}}
    t0 = time.time()
    status, body, err = post(OLLAMA_URL, headers, payload)
    elapsed = time.time() - t0
    if err and status:
        print(f"  STATUS:  {status}  ({elapsed:.1f}s)")
        # Try to extract short error
        try:
            parsed = json.loads(body) if isinstance(body, str) else body
            print(f"  ERROR:   {json.dumps(parsed)[:200]}")
        except Exception:
            print(f"  ERROR:   {str(body)[:200]}")
        return False
    elif err:
        print(f"  STATUS:  NETWORK ERROR  ({elapsed:.1f}s)")
        print(f"  ERROR:   {err[:200]}")
        return False
    else:
        print(f"  STATUS:  {status} OK  ({elapsed:.1f}s)")
        # Extract reply
        msg = body.get("message", {})
        content = msg.get("content", "")[:80] if isinstance(msg, dict) else str(body)[:80]
        print(f"  REPLY:   {content}")
        return True


def test_openrouter(key, idx):
    print(f"\n{'='*60}")
    print(f"  OpenRouter Key #{idx}:  ...{key[-12:]}")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/local/louis-cli",
        "X-Title": "Louis CLI Test",
    }
    payload = {"model": OR_MODEL, "messages": TINY_MSG, "temperature": 0.1, "max_tokens": 16}
    t0 = time.time()
    status, body, err = post(OR_URL, headers, payload)
    elapsed = time.time() - t0
    if err and status:
        print(f"  STATUS:  {status}  ({elapsed:.1f}s)")
        try:
            parsed = json.loads(body) if isinstance(body, str) else body
            print(f"  ERROR:   {json.dumps(parsed)[:200]}")
        except Exception:
            print(f"  ERROR:   {str(body)[:200]}")
        return False
    elif err:
        print(f"  STATUS:  NETWORK ERROR  ({elapsed:.1f}s)")
        print(f"  ERROR:   {err[:200]}")
        return False
    else:
        print(f"  STATUS:  {status} OK  ({elapsed:.1f}s)")
        choices = body.get("choices", [])
        content = choices[0].get("message", {}).get("content", "")[:80] if choices else str(body)[:80]
        print(f"  REPLY:   {content}")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("  LOUIS API KEY HEALTH CHECK")
    print("=" * 60)

    results = {}

    for i, key in enumerate(OLLAMA_KEYS, 1):
        ok = test_ollama(key, i)
        results[f"Ollama #{i}"] = "✓ WORKING" if ok else "✗ FAILED"

    for i, key in enumerate(OPENROUTER_KEYS, 1):
        ok = test_openrouter(key, i)
        results[f"OpenRouter #{i}"] = "✓ WORKING" if ok else "✗ FAILED"

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print("=" * 60)
    for name, status in results.items():
        icon = "🟢" if "WORKING" in status else "🔴"
        print(f"  {icon}  {name:20s}  {status}")
    print("=" * 60)
