# docs/14-stack-and-design-contract.md
PRODUCT_SLUG: compliance-pulse
PRD_VERSION: 913f3ea
FR_IDS_IN_SCOPE: FR-001 (Document Upload & Validation / Auth-Scoped Slice 1)
FRONTEND: Streamlit (Python)
STYLE: Deep Purple (#6B21A8) + Light Lavender (#F3E8FF) + Accessible Forms/Tables
ANIMATION_3D: None / CSS transitions only (no 3D, no Motion+)
BACKEND: Python 3.14 + FastAPI + Pydantic
DATABASE_AUTH: SQLite (local dev persistence) -> Supabase PostgreSQL + Auth (production target), tenant_id isolation
AI_RAG_GRAPH: DEFERRED to later slices (no RAG, LangGraph, or MCP in first slice)
MCP_APIS: GET /health, POST /api/v1/documents/upload (deferred endpoints in later slices)
TEST_COMMANDS: py -3 -m pytest -v
DEPLOY: Local dev first (FastAPI + Streamlit); free-tier cloud later
FORBIDDEN_CHANGES: No paid tiers, no invented FRs, no secrets committed
