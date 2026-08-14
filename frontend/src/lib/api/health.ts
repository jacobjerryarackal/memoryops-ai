import { request } from "./client";

export const healthApi = {
  async checkHealth(): Promise<{ status: string; version: string; uptime_seconds: number }> {
    return request<{ status: string; version: string; uptime_seconds: number }>("/healthz");
  },
};
