LMSTUDIO_URL = "http://127.0.0.1:1234/v1"


# ------------------------------------------------------- local AI (Gemma)
def lm_models(url=LMSTUDIO_URL):
    import requests
    try:
        data = requests.get(f"{url}/models", timeout=3).json()["data"]
        return [m["id"] for m in data]
    except Exception:
        return []


def ai_report(summary, model, url=LMSTUDIO_URL):
    import requests
    prompt = ("You are a power systems engineer. Write a short plain-English "
              "load flow study summary: voltage problems, losses, and practical "
              "suggestions. Use ONLY the numbers given, do not invent any.\n\n"
              + summary)
    r = requests.post(f"{url}/chat/completions", timeout=300, json={
        "model": model, "temperature": 0.3, "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
