
import requests

url = "https://administrators-cork-warnings-tip.trycloudflare.com/api/generate"

payload = {
    "model": "qwen3:8b",
    "prompt": "Explain artificial intelligence in simple words.",
    "stream": False
}

response = requests.post(url, json=payload)

result = response.json()

print("AI Response:")
print(result["response"])
