import React from "react";
import { MemoryRecord } from "../../lib/types/memory";
import { MemoryCard } from "./MemoryCard";
import { EmptyState } from "../common/EmptyState";

interface MemoryListProps {
  memories: MemoryRecord[];
  handleTransitionStatus: (id: string, status: string) => Promise<void>;
  handleEdit: (memory: MemoryRecord) => void;
  handleShowEvidence: (memory: MemoryRecord) => Promise<void>;
  handleDeleteMemory: (id: string) => Promise<void>;
}

export function MemoryList({
  memories,
  handleTransitionStatus,
  handleEdit,
  handleShowEvidence,
  handleDeleteMemory,
}: MemoryListProps) {
  if (memories.length === 0) {
    return <EmptyState message="No records matched the selected query or scopes." />;
  }

  return (
    <div className="space-y-2.5">
      {memories.map((m) => (
        <MemoryCard
          key={m.id}
          memory={m}
          handleTransitionStatus={handleTransitionStatus}
          handleEdit={handleEdit}
          handleShowEvidence={handleShowEvidence}
          handleDeleteMemory={handleDeleteMemory}
        />
      ))}
    </div>
  );
}
