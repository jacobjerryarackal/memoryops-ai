/* eslint-disable @typescript-eslint/no-explicit-any */
import React from "react";
import { MemoryRecord } from "../../lib/types/memory";

interface EvidencePanelProps {
  evidenceMemory: MemoryRecord | null;
  evidenceData: any;
  evidenceLoading: boolean;
  handleClose: () => void;
}

export function EvidencePanel({
  evidenceMemory,
  evidenceData,
  evidenceLoading,
  handleClose,
}: EvidencePanelProps) {
  if (!evidenceMemory) return null;

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="evidence-modal-title"
    >
      <div className="glass-panel w-full max-w-2xl p-5 space-y-4 bg-[#0d0f16] max-h-[85vh] flex flex-col">
        <div className="flex justify-between items-center border-b border-white/5 pb-3">
          <h3 id="evidence-modal-title" className="text-sm font-semibold text-white uppercase tracking-wider">
            Memory Evidence & Provenance
          </h3>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close modal"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-xs">
          {evidenceLoading ? (
            <div className="py-20 text-center text-gray-500 shimmer">Fetching evidence data...</div>
          ) : !evidenceData ? (
            <div className="py-20 text-center text-red-400">Failed to fetch evidence bundle.</div>
          ) : (
            <div className="space-y-4">
              {/* Origin Metadatas */}
              <div className="space-y-2">
                <h4 className="font-bold text-[#00f0ff] uppercase tracking-wide text-[10px]">Admission Details</h4>
                <div className="bg-black/20 p-3 rounded border border-white/5 space-y-1.5 font-mono">
                  <div><span className="text-gray-500 font-semibold">ID:</span> <span className="text-white">{evidenceData.memory_id}</span></div>
                  <div><span className="text-gray-500 font-semibold">Decision:</span> <span className="text-emerald-400 font-bold">{evidenceData.initial_policy_decision}</span></div>
                  <div><span className="text-gray-500 font-semibold">Reason:</span> <span className="text-gray-300">{evidenceData.initial_policy_reason}</span></div>
                  <div><span className="text-gray-500 font-semibold">Slot Coordinate:</span> <span className="text-[#00f0ff]">{evidenceData.identity_slot || "None"}</span></div>
                </div>
              </div>

              {/* Audit Trail */}
              <div className="space-y-2">
                <h4 className="font-bold text-[#00f0ff] uppercase tracking-wide text-[10px]">Historical Audit Trail</h4>
                {!evidenceData.audit_trail || evidenceData.audit_trail.length === 0 ? (
                  <div className="text-gray-500 italic p-2">No historical mutations audited.</div>
                ) : (
                  <div className="space-y-2">
                    {evidenceData.audit_trail.map((evt: any) => (
                      <div key={evt.id} className="bg-black/20 p-3 rounded border border-white/5 space-y-1.5 font-mono text-[11px]">
                        <div className="flex justify-between font-bold">
                          <span className="text-[#00f0ff]">{evt.action}</span>
                          <span className="text-gray-500">{new Date(evt.created_at).toLocaleString()}</span>
                        </div>
                        <div className="text-gray-300"><span className="text-gray-500 font-semibold">Reason:</span> {evt.reason}</div>
                        {evt.trace_id && <div className="text-[10px] text-gray-500"><span className="font-semibold">Trace ID:</span> {evt.trace_id}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end border-t border-white/5 pt-3">
          <button
            type="button"
            onClick={handleClose}
            className="btn-secondary text-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
