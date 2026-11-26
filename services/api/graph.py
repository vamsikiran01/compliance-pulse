import sqlite3, json, hashlib
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from services.api.rag import answer_rfp_question

class CompliancePulseState(TypedDict, total=False):
    tenant_id: str
    actor_id: str
    question_id: str
    question_text: str
    route: str
    draft_answer: str
    citations: list[str]
    proposal_id: str
    args_digest: str
    approval_status: str
    reviewer_id: str
    execution_status: str
    receipt_id: str
    audit_events: list[str]

def canonical_digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def build_compliance_graph(db_conn: sqlite3.Connection, checkpointer: SqliteSaver):
    def classify_and_route(state: CompliancePulseState) -> dict:
        q = state.get("question_text", "").strip()
        events = list(state.get("audit_events", []))
        if len(q) < 8:
            events.append("ROUTE_CLARIFY")
            return {"route": "CLARIFY", "audit_events": events}
        if "delete all" in q.lower() or "drop table" in q.lower() or "bypass" in q.lower():
            events.append("ROUTE_REJECT_UNSAFE")
            return {"route": "REJECT", "approval_status": "REJECTED", "execution_status": "NOT_RUN", "audit_events": events}
        events.append("ROUTE_ANSWER")
        return {"route": "ANSWER", "audit_events": events}

    def rag_draft_node(state: CompliancePulseState) -> dict:
        events = list(state.get("audit_events", []))
        if state.get("route") != "ANSWER":
            return {"draft_answer": "Clarification required before drafting.", "citations": [], "audit_events": events}
        rag_out = answer_rfp_question(db_conn, state["tenant_id"], state["question_text"], use_live_llm=False)
        proposal_payload = {
            "tenant_id": state["tenant_id"],
            "question_id": state["question_id"],
            "answer": rag_out["answer"],
            "citations": rag_out["citations"],
        }
        digest = canonical_digest(proposal_payload)
        proposal_id = f"PROP-{state['question_id']}"
        events.append(f"PROPOSAL_FROZEN:{proposal_id}")
        return {
            "draft_answer": rag_out["answer"],
            "citations": rag_out["citations"],
            "proposal_id": proposal_id,
            "args_digest": digest,
            "approval_status": "PENDING_REVIEW",
            "execution_status": "NOT_RUN",
            "audit_events": events,
        }

    def human_approval_gate(state: CompliancePulseState) -> dict:
        events = list(state.get("audit_events", []))
        if state.get("route") != "ANSWER":
            return {"approval_status": state.get("approval_status", "NOT_REQUIRED"), "audit_events": events}

        # Pause graph cleanly before any external export or write side effect
        decision_payload = interrupt({
            "proposal_id": state["proposal_id"],
            "tenant_id": state["tenant_id"],
            "initiator_id": state["actor_id"],
            "args_digest": state["args_digest"],
            "draft_answer": state["draft_answer"],
            "citations": state["citations"],
        })

        reviewer_id = decision_payload.get("reviewer_id", "")
        reviewer_tenant = decision_payload.get("reviewer_tenant", "")
        decision = decision_payload.get("decision", "REJECT").upper()
        submitted_digest = decision_payload.get("args_digest", "")
        expired = bool(decision_payload.get("expired", False))

        # Server-side policy checks (BR-06, BR-07, Tenant Isolation)
        if reviewer_tenant != state["tenant_id"]:
            events.append("APPROVAL_DENIED_CROSS_TENANT")
            return {"approval_status": "DENIED_TENANT", "execution_status": "NOT_RUN", "audit_events": events}
        if reviewer_id == state["actor_id"]:
            events.append("APPROVAL_DENIED_SELF_APPROVAL")
            return {"approval_status": "DENIED_SELF_APPROVAL", "execution_status": "NOT_RUN", "audit_events": events}
        if expired:
            events.append("APPROVAL_EXPIRED")
            return {"approval_status": "EXPIRED", "execution_status": "NOT_RUN", "audit_events": events}
        if submitted_digest != state["args_digest"]:
            events.append("APPROVAL_INVALIDATED_DIGEST_MISMATCH")
            return {"approval_status": "INVALIDATED", "execution_status": "NOT_RUN", "audit_events": events}
        if decision != "APPROVE":
            events.append("APPROVAL_REJECTED_BY_LEAD")
            return {"approval_status": "REJECTED", "reviewer_id": reviewer_id, "execution_status": "NOT_RUN", "audit_events": events}

        events.append("APPROVAL_APPROVED_BY_LEAD")
        return {"approval_status": "APPROVED", "reviewer_id": reviewer_id, "audit_events": events}

    def execute_export_node(state: CompliancePulseState) -> dict:
        events = list(state.get("audit_events", []))
        if state.get("approval_status") != "APPROVED":
            events.append("EXPORT_SKIPPED_NOT_APPROVED")
            return {"execution_status": "NOT_RUN", "audit_events": events}
        receipt = f"SBX-EXP-{state['proposal_id']}-{state['args_digest'][:8]}"
        events.append(f"EXPORT_SUCCEEDED:{receipt}")
        return {"execution_status": "SUCCEEDED", "receipt_id": receipt, "audit_events": events}

    g = StateGraph(CompliancePulseState)
    g.add_node("classify_and_route", classify_and_route)
    g.add_node("rag_draft", rag_draft_node)
    g.add_node("human_approval", human_approval_gate)
    g.add_node("execute_export", execute_export_node)

    g.add_edge(START, "classify_and_route")
    g.add_edge("classify_and_route", "rag_draft")
    g.add_edge("rag_draft", "human_approval")
    g.add_edge("human_approval", "execute_export")
    g.add_edge("execute_export", END)

    return g.compile(checkpointer=checkpointer)
