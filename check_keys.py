import os
import requests
from dotenv import load_dotenv

load_dotenv()

keys_str = os.getenv("OPENROUTER_API_KEYS", "")
keys = [k.strip() for k in keys_str.split(",") if k.strip()]

print(f"Found {len(keys)} OpenRouter keys in .env")

for idx, key in enumerate(keys):
    try:
        res = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"}
        )
        if res.status_code == 200:
            data = res.json()
            print(f"Key #{idx+1}: Active. Details: {data}")
        else:
            print(f"Key #{idx+1}: Failed. Status Code: {res.status_code}, Response: {res.text}")
    except Exception as e:
        print(f"Key #{idx+1}: Error checking key: {e}")
