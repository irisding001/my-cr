import requests

resp = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": "say hello"}],
        "stream": False,
    },
    timeout=60,
)
print("Status:", resp.status_code)
print("Response:", resp.text[:1000])
