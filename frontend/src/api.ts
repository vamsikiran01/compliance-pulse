import { Role, TenantId } from './types';

function getToken(tenant: TenantId, role: Role): string {
  if (tenant === 'org_beta') return 'demo-token-beta';
  return role === 'COMPLIANCE_LEAD' ? 'demo-token-alpha' : 'demo-token-alpha-analyst';
}

export async function apiIngestPolicy(
  tenant: TenantId,
  role: Role,
  doc_code: string,
  title: string,
  version: string,
  text: string
) {
  const res = await fetch('/api/v1/knowledge/versions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken(tenant, role)}`,
    },
    body: JSON.stringify({ doc_code, title, version, pages: [[1, text]] }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiQueryKnowledge(tenant: TenantId, role: Role, question: string, useLiveLlm = false) {
  const res = await fetch('/api/v1/knowledge/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken(tenant, role)}`,
    },
    body: JSON.stringify({ question, use_live_llm: useLiveLlm }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiStartGraphRun(tenant: TenantId, role: Role, question_id: string, question_text: string) {
  const res = await fetch('/api/v1/agent/runs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken(tenant, role)}`,
    },
    body: JSON.stringify({ question_id, question_text }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiDecideApproval(
  tenant: TenantId,
  role: Role,
  thread_id: string,
  decision: 'APPROVE' | 'REJECT',
  args_digest: string
) {
  const res = await fetch(`/api/v1/approvals/${thread_id}/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken(tenant, role)}`,
    },
    body: JSON.stringify({ decision, args_digest, comment: 'Reviewed in CompliancePulse G-08 Gate' }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Approval blocked by policy');
  return data;
}
