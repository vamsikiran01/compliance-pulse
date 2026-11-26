export type Role = 'COMPLIANCE_LEAD' | 'COMPLIANCE_ANALYST';
export type TenantId = 'org_alpha' | 'org_beta';

export interface PolicyVersion {
  id: string;
  tenant_id: TenantId;
  doc_code: string;
  title: string;
  version: string;
  status: 'ACTIVE' | 'SUPERSEDED';
  chunk_count: number;
  content_hash: string;
  updated_at: string;
  excerpt: string;
}

export interface RfpQuestion {
  id: string;
  code: string;
  domain: string;
  question: string;
  risk: 'HIGH' | 'MEDIUM' | 'LOW';
  status: 'DRAFTED' | 'INTERRUPTED' | 'APPROVED' | 'CONFLICT' | 'ABSTAINED';
  draft: string;
  citations: string[];
  thread_id?: string;
  proposal_id?: string;
  args_digest?: string;
  initiator_id?: string;
  receipt_id?: string;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  tenant_id: TenantId;
  actor: string;
  action: string;
  target: string;
  status: 'SUCCESS' | 'PAUSED' | 'BLOCKED';
}
