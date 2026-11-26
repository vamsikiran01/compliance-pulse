import os, time, json, urllib.request, urllib.error
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("LLM_API_KEY", "").strip()
headers = {"Content-Type": "application/json", "x-goog-api-key": api_key, "User-Agent": "CompliancePulse/1.0"}

t0 = time.time()
mode = "DEMO_FALLBACK"
fallback = "No API key"
model_id = "gemini-flash-latest"
output = '{"status":"ok","domain":"Access Control","confidence":0.95}'

if api_key:
    try:
        list_req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models", headers=headers)
        with urllib.request.urlopen(list_req, timeout=20) as r:
            models = json.loads(r.read().decode("utf-8")).get("models", [])
        flash_models = [
            m["name"] for m in models
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "flash" in m["name"].lower()
            and "2.5-flash" not in m["name"].lower()
            and "2.0-flash" not in m["name"].lower()
        ] or [
            m["name"] for m in models
            if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"].lower()
        ]
        payload = json.dumps({
            "contents": [{"parts": [{"text": 'Reply ONLY with valid JSON: {"status":"ok","domain":"Access Control","confidence":0.95}'}]}]
        }).encode("utf-8")
        last_err = "No models available"
        for candidate in reversed(flash_models):
            try:
                gen_req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/{candidate}:generateContent",
                    data=payload,
                    headers=headers
                )
                with urllib.request.urlopen(gen_req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                output = raw.replace("`json", "").replace("`", "").strip()
                model_id = candidate.replace("models/", "")
                mode = "LIVE"
                fallback = "None"
                break
            except Exception as inner_e:
                last_err = f"{candidate}: {type(inner_e).__name__}"
        if mode != "LIVE":
            fallback = last_err
    except Exception as e:
        fallback = f"{type(e).__name__}: {str(e)[:100]}"

latency_ms = int((time.time() - t0) * 1000)
print(json.dumps({
    "trace_id": "req_test_05_01",
    "provider": "gemini" if mode == "LIVE" else "DEMO_FIXTURE",
    "model_id": model_id,
    "latency_ms": latency_ms,
    "fallback_triggered": fallback,
    "execution_status": mode,
    "actual_json_response": output
}, indent=2))
