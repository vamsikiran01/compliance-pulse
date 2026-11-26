import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = os.getenv("DB_PATH", "compliance_pulse.db")

app = FastAPI(title="CompliancePulse API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_TOKENS = {
    "demo-token-org-alpha": {"user_id": "user_alpha_01", "tenant_id": "org_alpha", "role": "compliance_analyst"},
    "demo-token-org-beta": {"user_id": "user_beta_01", "tenant_id": "org_beta", "role": "compliance_analyst"},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            filename TEXT NOT NULL,
            md5_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        '''
    )
    conn.commit()
    return conn


def verify_user(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "").strip()
    user = VALID_TOKENS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if x_tenant_id and x_tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")
    return user


@app.get("/health")
def health():
    return {"status": "ok", "service": "compliance-pulse-api", "slice": "FR-001"}


@app.post("/api/v1/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(verify_user),
):
    if not file.filename:
        raise HTTPException(status_code=422, detail="Filename is required")
    allowed_ext = (".pdf", ".docx", ".txt", ".csv")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=422, detail="Unsupported file type. Allowed: PDF, DOCX, TXT, CSV")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    md5_hash = hashlib.md5(content).hexdigest()
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM documents WHERE tenant_id = ? AND md5_hash = ?",
            (user["tenant_id"], md5_hash),
        ).fetchone()
        if existing:
            return {
                "id": existing["id"],
                "filename": existing["filename"],
                "md5_hash": existing["md5_hash"],
                "status": "duplicate_skipped",
                "tenant_id": existing["tenant_id"],
                "created_at": existing["created_at"],
            }

        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            '''
            INSERT INTO documents (id, tenant_id, uploaded_by, filename, md5_hash, size_bytes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (doc_id, user["tenant_id"], user["user_id"], file.filename, md5_hash, len(content), "uploaded", created_at),
        )
        conn.commit()
        return {
            "id": doc_id,
            "filename": file.filename,
            "md5_hash": md5_hash,
            "status": "uploaded",
            "tenant_id": user["tenant_id"],
            "created_at": created_at,
        }
    finally:
        conn.close()


@app.get("/api/v1/documents")
def list_documents(user: dict = Depends(verify_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, tenant_id, uploaded_by, filename, md5_hash, size_bytes, status, created_at FROM documents WHERE tenant_id = ? ORDER BY created_at DESC",
            (user["tenant_id"],),
        ).fetchall()
        return {"tenant_id": user["tenant_id"], "count": len(rows), "documents": [dict(r) for r in rows]}
    finally:
        conn.close()

from fastapi.middleware.cors import CORSMiddleware
from services.api.day05_routes import router as day05_router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(day05_router)
