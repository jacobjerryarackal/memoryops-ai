/* eslint-disable @typescript-eslint/no-explicit-any */
import { request } from "./client";
import { AuditEvent } from "../types/governance";

export const evidenceApi = {
  async getProvenance(
    memoryId: string,
    tenantId: string,
    userId: string
  ): Promise<Record<string, any>> {
    return request<Record<string, any>>(
      `/api/memories/${memoryId}/provenance?tenant_id=${tenantId}&user_id=${userId}`
    );
  },

  async getEvidence(
    memoryId: string,
    tenantId: string,
    userId: string
  ): Promise<Record<string, any>> {
    return request<Record<string, any>>(
      `/api/memories/${memoryId}/evidence?tenant_id=${tenantId}&user_id=${userId}`
    );
  },

  async getAudit(
    memoryId: string,
    tenantId: string,
    userId: string,
    limit?: number
  ): Promise<AuditEvent[]> {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      user_id: userId,
    });
    if (limit) params.append("limit", String(limit));
    return request<AuditEvent[]>(
      `/api/memories/${memoryId}/audit?${params.toString()}`
    );
  },
};
