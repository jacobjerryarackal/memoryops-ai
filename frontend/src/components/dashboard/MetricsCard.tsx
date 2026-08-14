import React from "react";
import { TenantMetrics } from "../../lib/types/governance";
import { EmptyState } from "../common/EmptyState";

interface MetricsCardProps {
  metrics: TenantMetrics | null;
}

export function MetricsCard({ metrics }: MetricsCardProps) {
  if (!metrics) {
    return <EmptyState message="Failed to fetch statistics." />;
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-4">
        <div className="glass-panel p-4 text-center">
          <div className="text-xl font-bold text-white">{metrics.total_memories}</div>
          <div className="text-[9px] uppercase tracking-wider font-semibold text-gray-400 mt-1">Total Seeded</div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-xl font-bold text-emerald-400">{metrics.by_status.active || 0}</div>
          <div className="text-[9px] uppercase tracking-wider font-semibold text-gray-400 mt-1">Active Status</div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-xl font-bold text-purple-400">{metrics.audit_events}</div>
          <div className="text-[9px] uppercase tracking-wider font-semibold text-gray-400 mt-1">Audit Entries</div>
        </div>
      </div>

      {/* Status breakdown */}
      <div className="glass-panel p-4 space-y-4">
        <h4 className="text-[10px] font-bold uppercase tracking-wider text-white">Status Breakdown</h4>
        <div className="space-y-3.5">
          {Object.entries(metrics.by_status).map(([key, val]) => {
            const percentage = metrics.total_memories > 0 ? (val / metrics.total_memories) * 100 : 0;
            return (
              <div key={key} className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="capitalize">{key}</span>
                  <span>{val} ({percentage.toFixed(0)}%)</span>
                </div>
                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      key === "active"
                        ? "bg-emerald-400"
                        : key === "pending"
                        ? "bg-amber-400"
                        : key === "rejected"
                        ? "bg-red-500"
                        : "bg-gray-500"
                    }`}
                    style={{ width: `${percentage}%` }}
                  ></div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Action history counts */}
      <div className="glass-panel p-4 space-y-4">
        <h4 className="text-[10px] font-bold uppercase tracking-wider text-white">Action Metrics</h4>
        <div className="space-y-3.5">
          {Object.entries(metrics.by_action).map(([key, val]) => {
            const percentage = metrics.audit_events > 0 ? (val / metrics.audit_events) * 100 : 0;
            return (
              <div key={key} className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="capitalize">{key.replace("memory_", "")}</span>
                  <span>{val} ({percentage.toFixed(0)}%)</span>
                </div>
                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#00f0ff]"
                    style={{ width: `${percentage}%` }}
                  ></div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
