import { request } from "./client";
import { MemoryRecord } from "../types/memory";
import { ChatResponse } from "../types/api";

export const memoriesApi = {
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
};
