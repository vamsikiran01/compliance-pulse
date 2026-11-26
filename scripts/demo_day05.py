import json
from fastapi.testclient import TestClient
from services.api.main import app

client = TestClient(app)
h_lead = {"Authorization": "Bearer demo-token-alpha"}
h_analyst = {"Authorization": "Bearer demo-token-alpha-analyst"}

r1 = client.post("/api/v1/knowledge/versions", headers=h_lead, json={
    "doc_code": "DOC-001",
    "title": "SOC 2 Security Controls",
    "version": "v2.0",
    "pages": [[1, "All customer data at rest is encrypted using AES-256 via AWS KMS customer-managed keys."]]
})

r2 = client.post("/api/v1/agent/runs", headers=h_analyst, json={
    "question_id": "Q101",
    "question_text": "How is customer data encrypted at rest?"
})
paused = r2.json()
tid = paused["thread_id"]

r3 = client.post(f"/api/v1/approvals/{tid}/decision", headers=h_lead, json={
    "decision": "APPROVE",
    "args_digest": paused["args_digest"],
    "comment": "Verified against SOC 2 v2.0"
})

print(json.dumps({
    "step1_ingest": r1.json(),
    "step2_graph_paused": {
        "thread_id": tid,
        "status": paused["status"],
        "proposal_id": paused["proposal_id"],
        "citations": paused["citations"]
    },
    "step3_lead_approved": r3.json()
}, indent=2))
