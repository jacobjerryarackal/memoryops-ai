import React from "react";

interface MemoryFiltersProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  statusFilter: string;
  setStatusFilter: (status: string) => void;
  typeFilter: string;
  setTypeFilter: (type: string) => void;
}

export function MemoryFilters({
  searchQuery,
  setSearchQuery,
  statusFilter,
  setStatusFilter,
  typeFilter,
  setTypeFilter,
}: MemoryFiltersProps) {
  return (
    <div className="bg-[#11131c]/50 p-3 rounded-lg border border-white/5 flex flex-col md:flex-row gap-3 items-center justify-between">
      <input
        type="text"
        placeholder="Search memory payload or slot..."
        className="glass-input text-xs w-full md:max-w-xs focus-ring"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
      />
      
      <div className="flex gap-2 w-full md:w-auto items-center justify-end">
        <select
          aria-label="Filter status"
          className="glass-input text-[11px] py-1.5 focus-ring"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="pending">Pending</option>
          <option value="archived">Archived</option>
          <option value="rejected">Rejected</option>
        </select>

        <select
          aria-label="Filter type"
          className="glass-input text-[11px] py-1.5 focus-ring"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          <option value="semantic">Semantic</option>
          <option value="procedural">Procedural</option>
          <option value="episodic">Episodic</option>
        </select>
      </div>
    </div>
  );
}
