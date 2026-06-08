import requests

url = "https://api.stability.ai/v2beta/stable-image/generate/core"

headers = {
    "Authorization": "Bearer sk-MYAPIKEY",
    "Accept": "image/*"
}

files = {
    "prompt": (None, "Lighthouse on a cliff overlooking the ocean"),
    "output_format": (None, "webp")
}

response = requests.post(url, headers=headers, files=files)

print(response.status_code)
print(response.text)

if response.status_code == 200:
    with open("lighthouse.webp", "wb") as f:
        f.write(response.content)