import React from "react";
import { AuditEvent } from "../../lib/types/governance";
import { EmptyState } from "../common/EmptyState";

interface AuditTimelineProps {
  auditLogs: AuditEvent[];
}

export function AuditTimeline({ auditLogs }: AuditTimelineProps) {
  if (auditLogs.length === 0) {
    return <EmptyState message="No audited history log events detected." />;
  }

  return (
    <div className="space-y-2">
      {auditLogs.map((log) => (
        <div key={log.id} className="glass-panel p-3.5 flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <span className="font-mono text-xs font-semibold text-[#00f0ff] uppercase tracking-wider">
              {log.action.replace("memory_", "")}
            </span>
            <span className="font-mono text-[9px] text-gray-500">
              {new Date(log.created_at).toLocaleString()}
            </span>
          </div>
          <p className="text-[11px] text-gray-300 leading-relaxed">
            Reason: {log.reason}
          </p>
          <div className="flex justify-between items-center border-t border-white/5 pt-2 mt-1 text-[8px] font-mono text-gray-500">
            <span>ID: {log.id}</span>
            {log.trace_id && <span>Trace: {log.trace_id}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
