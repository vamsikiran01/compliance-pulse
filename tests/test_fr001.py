import os
import pytest
from fastapi.testclient import TestClient

os.environ["DB_PATH"] = "test_compliance_pulse.db"
from services.api.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_db():
    if os.path.exists("test_compliance_pulse.db"):
        os.remove("test_compliance_pulse.db")
    yield
    if os.path.exists("test_compliance_pulse.db"):
        os.remove("test_compliance_pulse.db")


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_t1_upload_success_and_persistence():
    headers = {"Authorization": "Bearer demo-token-org-alpha", "X-Tenant-ID": "org_alpha"}
    files = {"file": ("soc2_rfp_sample.txt", b"Q1: Do you encrypt data at rest? Yes, AES-256.", "text/plain")}
    res = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "uploaded"
    assert data["tenant_id"] == "org_alpha"

    list_res = client.get("/api/v1/documents", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["count"] == 1


def test_t2_invalid_empty_or_bad_extension():
    headers = {"Authorization": "Bearer demo-token-org-alpha", "X-Tenant-ID": "org_alpha"}
    bad_ext = {"file": ("malware.exe", b"binary", "application/octet-stream")}
    res1 = client.post("/api/v1/documents/upload", headers=headers, files=bad_ext)
    assert res1.status_code == 422

    empty_file = {"file": ("empty.txt", b"", "text/plain")}
    res2 = client.post("/api/v1/documents/upload", headers=headers, files=empty_file)
    assert res2.status_code == 422


def test_t3_unauthenticated_blocked():
    files = {"file": ("rfp.txt", b"Sample RFP text", "text/plain")}
    res = client.post("/api/v1/documents/upload", files=files)
    assert res.status_code == 401


def test_t4_cross_tenant_forbidden_and_isolated():
    alpha_headers = {"Authorization": "Bearer demo-token-org-alpha", "X-Tenant-ID": "org_alpha"}
    files = {"file": ("alpha_secret.txt", b"Confidential Alpha Policy", "text/plain")}
    client.post("/api/v1/documents/upload", headers=alpha_headers, files=files)

    # Spoofed tenant header -> 403
    spoof_headers = {"Authorization": "Bearer demo-token-org-beta", "X-Tenant-ID": "org_alpha"}
    res_spoof = client.get("/api/v1/documents", headers=spoof_headers)
    assert res_spoof.status_code == 403

    # Beta user sees 0 Alpha documents
    beta_headers = {"Authorization": "Bearer demo-token-org-beta", "X-Tenant-ID": "org_beta"}
    res_beta = client.get("/api/v1/documents", headers=beta_headers)
    assert res_beta.status_code == 200
    assert res_beta.json()["count"] == 0


def test_t5_duplicate_md5_idempotent():
    headers = {"Authorization": "Bearer demo-token-org-alpha", "X-Tenant-ID": "org_alpha"}
    files = {"file": ("rfp_v1.txt", b"Identical RFP Content", "text/plain")}
    first = client.post("/api/v1/documents/upload", headers=headers, files=files)
    second = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert first.status_code == 201
    assert second.json()["status"] == "duplicate_skipped"
    assert first.json()["id"] == second.json()["id"]
