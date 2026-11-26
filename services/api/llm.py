import os, json, time, urllib.request, urllib.error
from dotenv import load_dotenv

load_dotenv()

def call_llm_json(prompt: str, fallback_payload: dict, simulate_429: bool = False) -> dict:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model_id = os.getenv("LLM_MODEL_ID", "gemini-3.5-flash-lite")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "25"))

    if simulate_429 or not api_key:
        res = dict(fallback_payload)
        res["_meta"] = {
            "mode": "DEMO_FALLBACK",
            "model_id": model_id,
            "fallback_reason": "HTTP_429_SIMULATED" if simulate_429 else "NO_API_KEY",
        }
        return res

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
        "User-Agent": "CompliancePulse/1.0",
    }

    last_err = "UNKNOWN"
    for attempt in range(2):
        try:
            t0 = time.time()
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_data = json.loads(resp.read().decode("utf-8"))
            text = raw_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            cleaned = text.replace("`json", "").replace("`", "").strip()
            parsed = json.loads(cleaned)
            parsed["_meta"] = {
                "mode": "LIVE",
                "model_id": model_id,
                "latency_ms": int((time.time() - t0) * 1000),
            }
            return parsed
        except urllib.error.HTTPError as e:
            last_err = f"HTTP_{e.code}"
            if e.code == 429 and attempt == 0:
                time.sleep(0.5)
                continue
            break
        except Exception as e:
            last_err = type(e).__name__
            break

    res = dict(fallback_payload)
    res["_meta"] = {"mode": "DEMO_FALLBACK", "model_id": model_id, "fallback_reason": last_err}
    return res
