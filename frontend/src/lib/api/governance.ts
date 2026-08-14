import { request } from "./client";
import { AuditEvent, TenantMetrics } from "../types/governance";

export const governanceApi = {
  async listAudit(
    tenantId: string,
    userId?: string,
    memoryId?: string,
    limit?: number
  ): Promise<AuditEvent[]> {
    const params = new URLSearchParams({ tenant_id: tenantId });
    if (userId) params.append("user_id", userId);
    if (memoryId) params.append("memory_id", memoryId);
    if (limit) params.append("limit", String(limit));
    return request<AuditEvent[]>(`/api/audit?${params.toString()}`);
  },

  async getMetrics(tenantId: string): Promise<TenantMetrics> {
    return request<TenantMetrics>(`/api/metrics?tenant_id=${tenantId}`);
  },
};
