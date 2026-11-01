import urllib.request, json

url = "http://192.168.37.1:18080/chat/completions"
body = json.dumps({
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_tokens": 20,
}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=90).read())
print("content =", r["choices"][0]["message"]["content"])
