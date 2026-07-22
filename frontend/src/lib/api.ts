export interface MemoryRecord {
  id: string;
  tenant_id: string;
  user_id: string;
  content: string;
  memory_type: string;
  status: string;
  sensitivity: string;
  importance: number;
  confidence: number;
  reinforcement_count: number;
  source_kind: string;
  source_conversation_id?: string;
  source_excerpt?: string;
  initial_policy_decision: string;
  initial_policy_reason: string;
  created_at: string;
  updated_at: string;
  archived_at?: string;
  deleted_at?: string;
  identity_slot?: string;
}

export interface UsedMemory {
  memory_id: string;
  content: string;
  memory_type: string;
  score: number;
  reason: string;
  score_breakdown: {
    semantic_score: number;
    keyword_score: number;
    importance_score: number;
    recency_score: number;
    confidence_score: number;
    reinforcement_score: number;
  };
  source?: {
    kind: string;
    excerpt?: string;
  };
}

export interface CandidateMemory {
  content: string;
  memory_type: string;
  confidence: number;
  importance: number;
  sensitivity: string;
  decision: string;
  reason: string;
  memory_id?: string;
}

export interface ChatResponse {
  assistant_message: string;
  used_memories: UsedMemory[];
  candidate_memories: CandidateMemory[];
  audit_event_ids: string[];
  temporary_chat: boolean;
  retrieval_mode: string;
  trace_id: string;
}

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
  };
  audit_events: number;
  by_action: {
    memory_created: number;
    memory_deleted: number;
    memory_approved: number;
  };
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    let errMsg = `Request failed with status ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.error?.message) {
        errMsg = errBody.error.message;
      }
    } catch {
      // ignore
    }
    throw new Error(errMsg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async chat(
    tenantId: string,
    userId: string,
    message: string,
    temporaryChat: boolean
  ): Promise<ChatResponse> {
    return request<ChatResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantId,
        user_id: userId,
        message,
        temporary_chat: temporaryChat,
      }),
    });
  },

  async listMemories(
    tenantId: string,
    userId: string,
    status?: string,
    memoryType?: string
  ): Promise<MemoryRecord[]> {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      user_id: userId,
    });
    if (status) params.append("status", status);
    if (memoryType) params.append("memory_type", memoryType);
    return request<MemoryRecord[]>(`/api/memories?${params.toString()}`);
  },

  async getMemory(
    memoryId: string,
    tenantId: string,
    userId: string
  ): Promise<MemoryRecord> {
    return request<MemoryRecord>(
      `/api/memories/${memoryId}?tenant_id=${tenantId}&user_id=${userId}`
    );
  },

  async getProvenance(
    memoryId: string,
    tenantId: string,
    userId: string
  ): Promise<Record<string, any>> {
    return request<Record<string, any>>(
      `/api/memories/${memoryId}/provenance?tenant_id=${tenantId}&user_id=${userId}`
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

  async patchMemory(
    memoryId: string,
    payload: {
      tenant_id: string;
      user_id: string;
      content?: string;
      importance?: number;
      confidence?: number;
      status?: string;
      sensitivity?: string;
      source_kind?: string;
      source_conversation_id?: string;
      source_excerpt?: string;
    }
  ): Promise<MemoryRecord> {
    return request<MemoryRecord>(`/api/memories/${memoryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  async deleteMemory(
    memoryId: string,
    tenantId: string,
    userId: string
  ): Promise<{ memory_id: string; status: string; deleted_at: string }> {
    return request<{ memory_id: string; status: string; deleted_at: string }>(
      `/api/memories/${memoryId}`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          user_id: userId,
        }),
      }
    );
  },

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

  async checkHealth(): Promise<{ status: string; version: string; uptime_seconds: number }> {
    return request<{ status: string; version: string; uptime_seconds: number }>("/healthz");
  },
};
