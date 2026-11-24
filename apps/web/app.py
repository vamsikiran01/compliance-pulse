import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="CompliancePulse | FR-001 Document Intake", layout="wide")

st.markdown(
    '''
    <style>
    .stApp { background-color: #FAF5FF; }
    h1, h2, h3 { color: #6B21A8; }
    .badge-ok { background: #F3E8FF; color: #6B21A8; padding: 4px 10px; border-radius: 8px; font-weight: 600; }
    </style>
    ''',
    unsafe_allow_html=True,
)

st.title("CompliancePulse — FR-001 Secure RFP Document Intake")
st.caption("Vertical Slice 1 | FastAPI + SQLite Persistence + Tenant Isolation (RAG/LangGraph Deferred)")

with st.sidebar:
    st.header("Session & Tenant Context")
    tenant_choice = st.selectbox("Active Tenant Organization", ["org_alpha", "org_beta", "unauthenticated_guest"])
    spoof_cross_tenant = st.checkbox("Simulate Cross-Tenant Access (403 Test)", value=False)

    if tenant_choice == "unauthenticated_guest":
        headers = {}
    else:
        token = f"demo-token-{tenant_choice.replace('_', '-')}"
        target_tenant = "org_alpha" if (spoof_cross_tenant and tenant_choice == "org_beta") else tenant_choice
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": target_tenant}

st.subheader("1. Upload RFP / Security Questionnaire Document")
uploaded_file = st.file_uploader("Choose a synthetic RFP file (TXT, CSV, PDF, DOCX)", type=["txt", "csv", "pdf", "docx"])

if st.button("Upload & Verify Document", type="primary"):
    if not uploaded_file:
        st.warning("Validation Error (422): Please select a file before submitting.")
    else:
        with st.spinner("Uploading and verifying MD5 hash..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}
                resp = requests.post(f"{API_BASE}/api/v1/documents/upload", headers=headers, files=files, timeout=5)
                if resp.status_code in (200, 201):
                    st.success(f"Success ({resp.status_code}): {resp.json()}")
                elif resp.status_code == 401:
                    st.error("401 Unauthorized: Missing or invalid session token.")
                elif resp.status_code == 403:
                    st.error("403 Permission Denied: Cross-tenant access blocked by backend.")
                else:
                    st.error(f"Error ({resp.status_code}): {resp.text}")
            except requests.exceptions.RequestException as exc:
                st.error(f"Backend Connection Error: Ensure FastAPI is running on {API_BASE}. ({exc})")

st.divider()
st.subheader("2. Persisted Tenant Documents (Database View)")
try:
    list_resp = requests.get(f"{API_BASE}/api/v1/documents", headers=headers, timeout=5)
    if list_resp.status_code == 200:
        docs = list_resp.json().get("documents", [])
        if not docs:
            st.info("Empty State: No documents uploaded for this tenant yet.")
        else:
            st.dataframe(docs, use_container_width=True)
    elif list_resp.status_code == 401:
        st.error("401 Unauthorized: Sign in with a valid tenant token to view documents.")
    elif list_resp.status_code == 403:
        st.error("403 Permission Denied: Tenant isolation enforced.")
except requests.exceptions.RequestException:
    st.warning("Backend offline — start FastAPI server to load persisted documents.")
