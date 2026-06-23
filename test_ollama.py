import requests

key1 = "337f9f6fd61f404688ee08691b1fa215.rVcdFp4VyXY09sojSxFGZXlm"
key2 = "e4eb997e22714150942d4a5ac5f29c19.ZftAGUetj2ULF5IiVlmPINU8"

for idx, key in enumerate([key1, key2]):
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3-coder:30b",
        "messages": [{"role": "user", "content": "hi"}]
    }
    
    print(f"Testing Key #{idx+1} on /api/chat...")
    res = requests.post("https://ollama.com/api/chat", json=payload, headers=headers)
    print(res.status_code, res.text)
    
    print(f"Testing Key #{idx+1} on /v1/chat/completions...")
    res = requests.post("https://ollama.com/v1/chat/completions", json=payload, headers=headers)
    print(res.status_code, res.text)
