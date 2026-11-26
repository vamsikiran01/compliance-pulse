import sqlite3, pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from services.api.rag import ingest_policy_version, answer_rfp_question
from services.api.graph import build_compliance_graph
from services.api.llm import call_llm_json

@pytest.fixture
def rag_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    # Seed org_alpha v1 (will be superseded by v2)
    ingest_policy_version(conn, "org_alpha", "DOC-001", "Security Policy", "v1.0", [
        (1, "Legacy policy: customer databases use AES-128 encryption at rest.")
    ])
    # Seed org_alpha v2 (ACTIVE)
    ingest_policy_version(conn, "org_alpha", "DOC-001", "Security Policy", "v2.0", [
        (1, "All customer data at rest is encrypted using AES-256 via AWS KMS customer-managed keys."),
        (2, "Audit logs are retained in hot searchable storage for 30 days.")
    ])
    # Seed org_beta private document (must never leak to org_alpha)
    ingest_policy_version(conn, "org_beta", "DOC-BETA-99", "Beta Secret Policy", "v1.0", [
        (1, "Org Beta uses proprietary quantum key distribution and secret Project Titan protocols.")
    ])
    yield conn
    conn.close()

# --- MANDATORY 6-CASE RAG EVALUATION CORPUS (RAG-01 to RAG-06) ---
def test_rag_01_current_active_policy(rag_db):
    res = answer_rfp_question(rag_db, "org_alpha", "How is customer data encrypted at rest?")
    assert res["status"] == "ANSWERED"
    assert "AES-256" in res["answer"]
    assert "[Source: DOC-001, v2.0, p.1]" in res["citations"]

def test_rag_02_outdated_version_superseded(rag_db):
    res = answer_rfp_question(rag_db, "org_alpha", "What encryption standard is used at rest?")
    assert "AES-128" not in res["answer"]
    assert all("v1.0" not in c for c in res["citations"])

def test_rag_03_contradictory_active_policies(rag_db):
    ingest_policy_version(rag_db, "org_alpha", "DOC-004", "Enterprise Addendum", "v2.0", [
        (1, "Enterprise audit logs must be retained in hot storage for 90 days.")
    ])
    res = answer_rfp_question(rag_db, "org_alpha", "How many days are audit logs retained?")
    assert res["status"] == "CONFLICT_REVIEW"
    assert res["conflict_detected"] is True
    assert any("DOC-001" in c for c in res["citations"])
    assert any("DOC-004" in c for c in res["citations"])

def test_rag_04_missing_evidence_abstains(rag_db):
    res = answer_rfp_question(rag_db, "org_alpha", "Do you operate space satellites on Mars?")
    assert res["status"] == "ABSTAINED"
    assert res["citations"] == []
    assert "Insufficient evidence" in res["answer"]

def test_rag_05_cross_tenant_isolation(rag_db):
    res = answer_rfp_question(rag_db, "org_alpha", "Tell me about Project Titan quantum key distribution")
    assert res["status"] == "ABSTAINED"
    assert res["chunks"] == []
    assert "DOC-BETA-99" not in str(res)

def test_rag_06_mid_session_policy_update(rag_db):
    before = answer_rfp_question(rag_db, "org_alpha", "How is customer data encrypted at rest?")
    assert "[Source: DOC-001, v2.0, p.1]" in before["citations"]
    ingest_policy_version(rag_db, "org_alpha", "DOC-001", "Security Policy", "v3.0", [
        (1, "All customer data at rest is encrypted using AES-256-GCM with HSM rotation every 90 days.")
    ])
    after = answer_rfp_question(rag_db, "org_alpha", "How is customer data encrypted at rest?")
    assert "[Source: DOC-001, v3.0, p.1]" in after["citations"]
    assert all("v2.0" not in c for c in after["citations"])

# --- MANDATORY NEGATIVE & LANGGRAPH HUMAN-IN-THE-LOOP SUITE (D5-T01 to D5-T10) ---
def test_langgraph_checkpoint_interrupt_and_approval_lifecycle(tmp_path, rag_db):
    ckpt_path = str(tmp_path / "checkpoints.db")
    config = {"configurable": {"thread_id": "thread_org_alpha_q01"}}

    # 1. Start graph run -> pauses at G-08 human_approval_gate
    with SqliteSaver.from_conn_string(ckpt_path) as saver:
        graph = build_compliance_graph(rag_db, saver)
        paused = graph.invoke({
            "tenant_id": "org_alpha",
            "actor_id": "analyst_01",
            "question_id": "Q01",
            "question_text": "How is customer data encrypted at rest?",
        }, config=config)
        assert "__interrupt__" in paused
        assert paused["execution_status"] == "NOT_RUN"
        digest = paused["args_digest"]

    # 2. Simulate API process restart (new SqliteSaver instance) -> state survives!
    with SqliteSaver.from_conn_string(ckpt_path) as saver_restarted:
        graph2 = build_compliance_graph(rag_db, saver_restarted)
        snap = graph2.get_state(config)
        assert snap.values["proposal_id"] == "PROP-Q01"

        # 3. Negative Test: Self-approval by initiator blocked (BR-07)
        self_attempt = graph2.invoke(Command(resume={
            "reviewer_id": "analyst_01",
            "reviewer_tenant": "org_alpha",
            "decision": "APPROVE",
            "args_digest": digest,
        }), config=config)
        assert self_attempt["approval_status"] == "DENIED_SELF_APPROVAL"
        assert self_attempt["execution_status"] == "NOT_RUN"

    # 4. Valid Compliance Lead approval on fresh thread -> executes once with receipt
    config_ok = {"configurable": {"thread_id": "thread_org_alpha_q02"}}
    with SqliteSaver.from_conn_string(ckpt_path) as saver3:
        graph3 = build_compliance_graph(rag_db, saver3)
        p2 = graph3.invoke({
            "tenant_id": "org_alpha",
            "actor_id": "analyst_01",
            "question_id": "Q02",
            "question_text": "How is customer data encrypted at rest?",
        }, config=config_ok)
        approved = graph3.invoke(Command(resume={
            "reviewer_id": "lead_01",
            "reviewer_tenant": "org_alpha",
            "decision": "APPROVE",
            "args_digest": p2["args_digest"],
        }), config=config_ok)
        assert approved["approval_status"] == "APPROVED"
        assert approved["execution_status"] == "SUCCEEDED"
        assert approved["receipt_id"].startswith("SBX-EXP-PROP-Q02")

def test_llm_429_rate_limit_fallback():
    res = call_llm_json("test", {"status": "SAFE_FALLBACK"}, simulate_429=True)
    assert res["status"] == "SAFE_FALLBACK"
    assert res["_meta"]["mode"] == "DEMO_FALLBACK"
    assert res["_meta"]["fallback_reason"] == "HTTP_429_SIMULATED"
