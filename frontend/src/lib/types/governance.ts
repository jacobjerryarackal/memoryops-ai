/* eslint-disable @typescript-eslint/no-explicit-any */

export interface AuditEvent {
  id: string;
  tenant_id: string;
  user_id?: string;
  memory_id?: string;
  action: string;
  reason?: string;
  metadata: Record<string, any>;
  trace_id?: string;
  created_at: string;
}

export interface TenantMetrics {
  total_memories: number;
  by_status: {
    active: number;
    pending: number;
    rejected: number;
    archived: number;
    deleted: number;
    [key: string]: number;
  };
  audit_events: number;
  by_action: {
    memory_created: number;
    memory_deleted: number;
    memory_approved: number;
    [key: string]: number;
  };
}
