import sqlite3, os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from services.api.rag import ingest_policy_version, answer_rfp_question
from services.api.graph import build_compliance_graph

router = APIRouter(prefix="/api/v1", tags=["Day 05 RAG & LangGraph"])

DB_PATH = os.getenv("COMPLIANCE_DB_PATH", "compliance_pulse.db")
CKPT_PATH = os.getenv("LANGGRAPH_CKPT_PATH", "checkpoints.db")

TOKENS = {
    "demo-token-alpha": {"user_id": "usr_alpha_01", "tenant_id": "org_alpha", "role": "COMPLIANCE_LEAD"},
    "demo-token-alpha-analyst": {"user_id": "usr_alpha_09", "tenant_id": "org_alpha", "role": "COMPLIANCE_ANALYST"},
    "demo-token-beta": {"user_id": "usr_beta_01", "tenant_id": "org_beta", "role": "COMPLIANCE_LEAD"},
}

def require_actor(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")
    token = authorization.replace("Bearer ", "").strip()
    actor = TOKENS.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="Invalid session token")
    return actor

class PolicyIngestReq(BaseModel):
    doc_code: str
    title: str
    version: str
    pages: list[list]  # [[1, "text..."], [2, "text..."]]

class KnowledgeQueryReq(BaseModel):
    question: str
    use_live_llm: bool = False

class GraphRunReq(BaseModel):
    question_id: str
    question_text: str

class ApprovalDecisionReq(BaseModel):
    decision: str  # APPROVE | REJECT
    args_digest: str
    comment: str | None = None

@router.post("/knowledge/versions")
def api_ingest_policy(body: PolicyIngestReq, authorization: str | None = Header(default=None)):
    actor = require_actor(authorization)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        pages_tuples = [(int(p[0]), str(p[1])) for p in body.pages]
        res = ingest_policy_version(conn, actor["tenant_id"], body.doc_code, body.title, body.version, pages_tuples)
        return {"tenant_id": actor["tenant_id"], **res}
    finally:
        conn.close()

@router.post("/knowledge/query")
def api_query_knowledge(body: KnowledgeQueryReq, authorization: str | None = Header(default=None)):
    actor = require_actor(authorization)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        res = answer_rfp_question(conn, actor["tenant_id"], body.question, use_live_llm=body.use_live_llm)
        return {"tenant_id": actor["tenant_id"], **res}
    finally:
        conn.close()

@router.post("/agent/runs")
def api_start_graph_run(body: GraphRunReq, authorization: str | None = Header(default=None)):
    actor = require_actor(authorization)
    thread_id = f"thread_{actor['tenant_id']}_{body.question_id}"
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        with SqliteSaver.from_conn_string(CKPT_PATH) as saver:
            graph = build_compliance_graph(conn, saver)
            out = graph.invoke({
                "tenant_id": actor["tenant_id"],
                "actor_id": actor["user_id"],
                "question_id": body.question_id,
                "question_text": body.question_text,
            }, config={"configurable": {"thread_id": thread_id}})
        interrupted = "__interrupt__" in out
        return {
            "thread_id": thread_id,
            "tenant_id": actor["tenant_id"],
            "status": "INTERRUPTED" if interrupted else "COMPLETED",
            "proposal_id": out.get("proposal_id"),
            "args_digest": out.get("args_digest"),
            "draft_answer": out.get("draft_answer"),
            "citations": out.get("citations", []),
            "approval_status": out.get("approval_status"),
            "execution_status": out.get("execution_status"),
        }
    finally:
        conn.close()

@router.post("/approvals/{thread_id}/decision")
def api_decide_approval(thread_id: str, body: ApprovalDecisionReq, authorization: str | None = Header(default=None)):
    actor = require_actor(authorization)
    if not thread_id.startswith(f"thread_{actor['tenant_id']}_"):
        raise HTTPException(status_code=404, detail="Proposal thread not found in tenant scope")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        with SqliteSaver.from_conn_string(CKPT_PATH) as saver:
            graph = build_compliance_graph(conn, saver)
            out = graph.invoke(Command(resume={
                "reviewer_id": actor["user_id"],
                "reviewer_tenant": actor["tenant_id"],
                "decision": body.decision,
                "args_digest": body.args_digest,
            }), config={"configurable": {"thread_id": thread_id}})
        if out.get("approval_status") == "DENIED_SELF_APPROVAL":
            raise HTTPException(status_code=403, detail="BR-07 Violation: Initiator cannot approve own proposal")
        if out.get("approval_status") == "INVALIDATED":
            raise HTTPException(status_code=409, detail="Proposal digest mismatch: payload invalidated")
        return {
            "thread_id": thread_id,
            "approval_status": out.get("approval_status"),
            "execution_status": out.get("execution_status"),
            "receipt_id": out.get("receipt_id"),
            "audit_events": out.get("audit_events", []),
        }
    finally:
        conn.close()
