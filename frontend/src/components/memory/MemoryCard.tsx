import React from "react";
import { MemoryRecord } from "../../lib/types/memory";

interface MemoryCardProps {
  memory: MemoryRecord;
  handleTransitionStatus: (id: string, status: string) => Promise<void>;
  handleEdit: (memory: MemoryRecord) => void;
  handleShowEvidence: (memory: MemoryRecord) => Promise<void>;
  handleDeleteMemory: (id: string) => Promise<void>;
}

export function MemoryCard({
  memory,
  handleTransitionStatus,
  handleEdit,
  handleShowEvidence,
  handleDeleteMemory,
}: MemoryCardProps) {
  const m = memory;
  return (
    <div className="glass-panel p-4 flex flex-col md:flex-row items-start justify-between gap-4">
      <div className="space-y-2 min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[9px] font-bold text-gray-400 bg-white/5 px-2 py-0.5 rounded border border-white/5">
            {m.memory_type}
          </span>
          {m.identity_slot && (
            <span className="font-mono text-[9px] font-semibold text-[#00f0ff] bg-[#00f0ff]/5 px-2 py-0.5 rounded border border-[#00f0ff]/10">
              {m.identity_slot}
            </span>
          )}
          <span className={`badge badge-${m.status}`}>{m.status}</span>
          <span className="text-[9px] font-mono text-gray-500">
            Importance: {m.importance} | Confidence: {m.confidence.toFixed(2)}
          </span>
        </div>
        
        <p className="text-xs font-semibold text-white leading-relaxed">
          &quot;{m.content}&quot;
        </p>
        
        <div className="text-[9px] font-mono text-gray-600">
          Created: {new Date(m.created_at).toLocaleString()}
        </div>
      </div>

      {/* Action menus */}
      <div className="flex flex-wrap items-center gap-1.5 mt-2 md:mt-0 flex-shrink-0">
        {m.status === "pending" && (
          <>
            <button
              onClick={() => handleTransitionStatus(m.id, "active")}
              className="btn-secondary text-[10px] py-1 px-2.5 text-emerald-400 border-emerald-500/10 hover:bg-emerald-500/5 focus-ring"
            >
              Approve
            </button>
            <button
              onClick={() => handleTransitionStatus(m.id, "rejected")}
              className="btn-secondary text-[10px] py-1 px-2.5 text-red-400 border-red-500/10 hover:bg-red-500/5 focus-ring"
            >
              Reject
            </button>
          </>
        )}
        {m.status === "active" && (
          <>
            <button
              onClick={() => handleTransitionStatus(m.id, "archived")}
              className="btn-secondary text-[10px] py-1 px-2.5 text-amber-400 border-amber-500/10 hover:bg-amber-500/5 focus-ring"
            >
              Archive
            </button>
            <button
              onClick={() => handleEdit(m)}
              className="btn-secondary text-[10px] py-1 px-2.5 text-gray-300 focus-ring"
            >
              Edit
            </button>
          </>
        )}
        {m.status === "archived" && (
          <button
            onClick={() => handleTransitionStatus(m.id, "active")}
            className="btn-secondary text-[10px] py-1 px-2.5 text-emerald-400 border-emerald-500/10 hover:bg-emerald-500/5 focus-ring"
          >
            Restore
          </button>
        )}
        {m.status !== "deleted" && (
          <>
            <button
              onClick={() => handleShowEvidence(m)}
              className="btn-secondary text-[10px] py-1 px-2.5 text-[#00f0ff] border-[#00f0ff]/10 hover:bg-[#00f0ff]/5 focus-ring"
            >
              Evidence
            </button>
            <button
              onClick={() => handleDeleteMemory(m.id)}
              className="btn-secondary text-[10px] py-1 px-2.5 text-red-500/80 border-red-500/10 hover:bg-red-500/5 focus-ring"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}
