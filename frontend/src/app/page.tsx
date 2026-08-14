"use client";

import { useEffect, useState, FormEvent, useCallback } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { Navbar } from "../components/layout/Navbar";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { MemoryFilters } from "../components/memory/MemoryFilters";
import { MemoryList } from "../components/memory/MemoryList";
import { EvidencePanel } from "../components/memory/EvidencePanel";
import { AuditTimeline } from "../components/governance/AuditTimeline";
import { MetricsCard } from "../components/dashboard/MetricsCard";

import { useHealth } from "../hooks/useHealth";
import { useMetrics } from "../hooks/useMetrics";
import { useEvidence } from "../hooks/useEvidence";
import { useMemories } from "../hooks/useMemories";
import { memoriesApi } from "../lib/api/memories";
import { UsedMemory } from "../lib/types/memory";
import { CandidateMemory } from "../lib/types/api";

export default function Home() {
  // Scoping Coordinates
  const [tenantId, setTenantId] = useState("tenant_demo");
  const [userId, setUserId] = useState("user_demo");
  
  // Chat States
  const [message, setMessage] = useState("");
  const [temporaryChat, setTemporaryChat] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState<
    Array<{
      sender: "user" | "assistant";
      text: string;
      usedMemories?: UsedMemory[];
      candidateMemories?: CandidateMemory[];
      traceId?: string;
      timestamp: Date;
    }>
  >([]);

  // Navigation & UI Layout States
  const [activeTab, setActiveTab] = useState<"memories" | "audit" | "metrics">("memories");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Hook-managed States
  const { connectionStatus, systemVersion, checkSystemHealth } = useHealth();
  const { metrics, auditLogs, metricsLoading, loadMetricsAndAudits } = useMetrics(tenantId);
  const {
    evidenceMemory,
    evidenceData,
    evidenceLoading,
    handleShowEvidence,
    handleCloseEvidence
  } = useEvidence(tenantId, userId);

  const {
    memoriesLoading,
    statusFilter,
    setStatusFilter,
    typeFilter,
    setTypeFilter,
    searchQuery,
    setSearchQuery,
    editMemory,
    setEditMemory,
    editContent,
    setEditContent,
    actionError,
    setActionError,
    loadMemories,
    handleTransitionStatus,
    handleEditContentSubmit,
    handleDeleteMemory,
    filteredMemories,
  } = useMemories(tenantId, userId, loadMetricsAndAudits);

  // Load all dashboard statistics & memory items
  const loadDashboardData = useCallback(async (tId = tenantId, uId = userId) => {
    setActionError(null);
    try {
      await checkSystemHealth();
      await loadMetricsAndAudits(tId);
      await loadMemories(tId, uId);
    } catch (err) {
      console.error("Dashboard synchronization failed:", err);
    }
  }, [tenantId, userId, checkSystemHealth, loadMetricsAndAudits, loadMemories, setActionError]);

  // Trigger load on state mounts or scopes change
  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // Handle chat submission
  const handleSendChat = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    if (!message.trim() || chatLoading) return;

    const userPrompt = message;
    setMessage("");
    setChatLoading(true);
    setActionError(null);

    // Append user message immediately
    setChatHistory((prev) => [
      ...prev,
      { sender: "user", text: userPrompt, timestamp: new Date() },
    ]);

    try {
      const resp = await memoriesApi.chat(tenantId, userId, userPrompt, temporaryChat);
      
      // Append assistant message and its explainability metadata
      setChatHistory((prev) => [
        ...prev,
        {
          sender: "assistant",
          text: resp.assistant_message,
          usedMemories: resp.used_memories,
          candidateMemories: resp.candidate_memories,
          traceId: resp.trace_id,
          timestamp: new Date(),
        },
      ]);

      // Reload dashboard stats to show newly persisted memories/audit events
      await loadDashboardData();
    } catch (err) {
      console.error(err);
      const errMsg = err instanceof Error ? err.message : "Failed to communicate with write path.";
      setChatHistory((prev) => [
        ...prev,
        {
          sender: "assistant",
          text: `[SYSTEM ERROR]: ${errMsg}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Shortcut queries helper
  const loadPromptShortcut = (text: string) => {
    setMessage(text);
  };

  // Helper to format timestamps gracefully
  const formatMessageTime = (date: Date | undefined) => {
    if (!date) return "Just now";
    try {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return "Just now";
    }
  };

  const govLoading = memoriesLoading || metricsLoading;

  return (
    <div className="flex-1 flex flex-col lg:flex-row h-screen min-h-screen bg-[#090a0f] text-[#e4e7eb] font-sans antialiased overflow-hidden">
      
      {/* 1. Left Collapsible Sidebar */}
      <Sidebar
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        tenantId={tenantId}
        setTenantId={setTenantId}
        userId={userId}
        setUserId={setUserId}
        loadPromptShortcut={loadPromptShortcut}
      />

      {/* 2. Main Workspace */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        
        {/* Top bar panel */}
        <Navbar
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          systemVersion={systemVersion}
          connectionStatus={connectionStatus}
        />

        {/* Invariance error banners */}
        {actionError && (
          <ErrorState message={actionError} onDismiss={() => setActionError(null)} />
        )}

        {/* Content panes split */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden min-w-0">
          
          {/* A. Left Pane: Dynamic Chat Loop */}
          <section
            className="w-full lg:w-[42%] border-b lg:border-b-0 lg:border-r border-white/5 flex flex-col bg-[#090a0f]/60 overflow-hidden"
            aria-label="Cognitive Chat stream"
          >
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {chatHistory.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
                  <div className="h-12 w-12 rounded-xl bg-white/3 border border-white/5 flex items-center justify-center text-lg text-gray-400">
                    🧠
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-xs font-semibold text-white">Cognitive Interaction Loop</h3>
                    <p className="text-[11px] text-gray-500 max-w-[240px] leading-relaxed">
                      Send a chat message to propose or retrieve memories scoped under current tenant.
                    </p>
                  </div>
                </div>
              ) : (
                chatHistory.map((item, index) => (
                  <div
                    key={index}
                    className={`flex flex-col gap-1.5 animate-fade-in ${
                      item.sender === "user" ? "items-end" : "items-start"
                    }`}
                  >
                    <div className="text-[9px] font-mono text-gray-500 px-1 flex items-center gap-1.5">
                      <span>{item.sender === "user" ? "USER" : "ASSISTANT"}</span>
                      <span>•</span>
                      <span>{formatMessageTime(item.timestamp)}</span>
                    </div>
                    
                    <div
                      className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-xs leading-relaxed ${
                        item.sender === "user"
                          ? "bg-[#252836] border border-white/10 text-white font-medium shadow-md"
                          : "bg-[#141620] border border-white/5 text-gray-200"
                      }`}
                    >
                      {item.text}
                    </div>

                    {/* Explainability panel details */}
                    {item.sender === "assistant" &&
                      (!!(item.usedMemories?.length) || !!(item.candidateMemories?.length)) && (
                        <div className="w-full max-w-[90%] mt-1.5 p-3 bg-black/20 border border-white/5 rounded-md space-y-3">
                          
                          {/* Memories referenced */}
                          {item.usedMemories && item.usedMemories.length > 0 && (
                            <div className="space-y-2">
                              <span className="text-[9px] font-semibold text-emerald-400 tracking-wider uppercase block">
                                Read Path: Referenced Memories ({item.usedMemories.length})
                              </span>
                              <div className="flex flex-col gap-2">
                                {item.usedMemories.map((m, mIdx) => (
                                  <div key={mIdx} className="bg-white/2 p-2 rounded border border-white/5 text-[11px] space-y-1">
                                    <div className="flex justify-between items-center text-[9px] font-mono text-gray-500">
                                      <span>ID: {m.memory_id.substring(0, 8)}...</span>
                                      <span className="text-[#00f0ff] font-semibold">
                                        Score: {(m.score * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                    <p className="text-gray-300">&quot;{m.content}&quot;</p>
                                    
                                    {/* Breakdown bars */}
                                    <div className="space-y-1 pt-1 border-t border-white/5 mt-1 text-[9px] font-mono">
                                      <div className="text-gray-500">Reason: {m.reason}</div>
                                      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-gray-500 text-[8px]">
                                        <div className="flex justify-between">
                                          <span>Semantic:</span>
                                          <span>{m.score_breakdown.semantic_score.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Keyword:</span>
                                          <span>{m.score_breakdown.keyword_score.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Importance:</span>
                                          <span>{m.score_breakdown.importance_score.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Recency:</span>
                                          <span>{m.score_breakdown.recency_score.toFixed(2)}</span>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Candidate decisions */}
                          {item.candidateMemories && item.candidateMemories.length > 0 && (
                            <div className="space-y-2">
                              <span className="text-[9px] font-semibold text-[#8b5cf6] tracking-wider uppercase block">
                                Write Path: Extracted Candidate Decisions
                              </span>
                              <div className="flex flex-col gap-2">
                                {item.candidateMemories.map((cm, cmIdx) => (
                                  <div key={cmIdx} className="bg-white/2 p-2 rounded border border-white/5 text-[11px] space-y-1">
                                    <div className="flex justify-between items-start gap-2">
                                      <span className="text-gray-300 font-medium leading-relaxed">&quot;{cm.content}&quot;</span>
                                      <span
                                        className={`badge flex-shrink-0 ${
                                          cm.decision === "SAVE"
                                            ? "badge-active"
                                            : cm.decision === "BLOCK"
                                            ? "badge-rejected"
                                            : "badge-pending"
                                        }`}
                                      >
                                        {cm.decision}
                                      </span>
                                    </div>
                                    <div className="text-[9px] font-mono text-gray-500">
                                      Reason: {cm.reason}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {item.traceId && (
                            <div className="text-[8px] font-mono text-gray-600 text-right pt-0.5 border-t border-white/2">
                              Trace ID: {item.traceId}
                            </div>
                          )}
                        </div>
                      )}
                  </div>
                ))
              )}
            </div>

            {/* Form Input console */}
            <form
              onSubmit={handleSendChat}
              className="p-4 border-t border-white/5 bg-[#0d0f16]/50 flex flex-col gap-3"
            >
              <div className="flex items-center justify-between">
                <label htmlFor="temp-chat-toggle" className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    id="temp-chat-toggle"
                    type="checkbox"
                    className="h-3.5 w-3.5 rounded border-white/10 bg-black/40 text-[#00f0ff] focus:ring-0 focus:ring-offset-0"
                    checked={temporaryChat}
                    onChange={(e) => setTemporaryChat(e.target.checked)}
                  />
                  <span className="text-[10px] text-gray-400 font-mono tracking-wide uppercase">
                    Bypass persistence (Temporary Chat)
                  </span>
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="chat-input"
                  type="text"
                  className="flex-1 glass-input focus-ring"
                  placeholder="Propose facts or preferences..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  disabled={chatLoading}
                  autoComplete="off"
                />
                <button
                  type="submit"
                  className="btn-primary focus-ring h-[34px]"
                  disabled={chatLoading || !message.trim()}
                >
                  {chatLoading ? (
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-black animate-ping"></span>
                      Syncing
                    </span>
                  ) : (
                    "Send"
                  )}
                </button>
              </div>
            </form>
          </section>

          {/* B. Right Pane: Governance Dashboard */}
          <section
            className="flex-1 flex flex-col bg-[#090a0f]/20 overflow-hidden min-w-0"
            aria-label="Governance Control Plane"
          >
            {/* View navigation Tabs */}
            <div className="h-12 border-b border-white/5 flex justify-between items-center px-6 bg-[#0d0f16]/30">
              <nav className="flex gap-5" role="tablist">
                <button
                  role="tab"
                  aria-selected={activeTab === "memories"}
                  onClick={() => setActiveTab("memories")}
                  className={`h-12 text-xs font-semibold tracking-wider uppercase border-b-2 transition-all ${
                    activeTab === "memories"
                      ? "border-[#00f0ff] text-white"
                      : "border-transparent text-gray-400 hover:text-white"
                  }`}
                >
                  Registry
                </button>
                <button
                  role="tab"
                  aria-selected={activeTab === "audit"}
                  onClick={() => setActiveTab("audit")}
                  className={`h-12 text-xs font-semibold tracking-wider uppercase border-b-2 transition-all ${
                    activeTab === "audit"
                      ? "border-[#00f0ff] text-white"
                      : "border-transparent text-gray-400 hover:text-white"
                  }`}
                >
                  Audit Trail
                </button>
                <button
                  role="tab"
                  aria-selected={activeTab === "metrics"}
                  onClick={() => setActiveTab("metrics")}
                  className={`h-12 text-xs font-semibold tracking-wider uppercase border-b-2 transition-all ${
                    activeTab === "metrics"
                      ? "border-[#00f0ff] text-white"
                      : "border-transparent text-gray-400 hover:text-white"
                  }`}
                >
                  Metrics
                </button>
              </nav>

              <button
                onClick={() => loadDashboardData()}
                className="btn-secondary text-[11px] py-1 px-3 h-7 flex items-center focus-ring"
                disabled={govLoading}
              >
                {govLoading ? "Syncing..." : "Sync"}
              </button>
            </div>

            {/* Scrollable dashboard container */}
            <div className="flex-1 overflow-y-auto p-5">
              
              {/* Tab 1: Memories list */}
              {activeTab === "memories" && (
                <div className="space-y-4">
                  {/* Search and Filters toolbar */}
                  <MemoryFilters
                    searchQuery={searchQuery}
                    setSearchQuery={setSearchQuery}
                    statusFilter={statusFilter}
                    setStatusFilter={setStatusFilter}
                    typeFilter={typeFilter}
                    setTypeFilter={setTypeFilter}
                  />

                  {/* Skeletons or list items */}
                  {govLoading ? (
                    <LoadingState count={3} height="h-24" />
                  ) : (
                    <MemoryList
                      memories={filteredMemories}
                      handleTransitionStatus={handleTransitionStatus}
                      handleEdit={m => {
                        setEditMemory(m);
                        setEditContent(m.content);
                      }}
                      handleShowEvidence={handleShowEvidence}
                      handleDeleteMemory={handleDeleteMemory}
                    />
                  )}
                </div>
              )}

              {/* Tab 2: Audit Logs */}
              {activeTab === "audit" && (
                <div className="space-y-4">
                  {govLoading ? (
                    <LoadingState count={2} height="h-20" />
                  ) : (
                    <AuditTimeline auditLogs={auditLogs} />
                  )}
                </div>
              )}

              {/* Tab 3: Metrics summary */}
              {activeTab === "metrics" && (
                <div className="space-y-5">
                  {govLoading ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-3 gap-4 h-16">
                        {[1, 2, 3].map((n) => (
                          <div key={n} className="shimmer rounded-lg border border-white/5"></div>
                        ))}
                      </div>
                      <div className="h-44 shimmer rounded-lg border border-white/5"></div>
                    </div>
                  ) : (
                    <MetricsCard metrics={metrics} />
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* 3. Edit Dialog Overlay Modal */}
      {editMemory && (
        <div
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
        >
          <div className="glass-panel w-full max-w-md p-5 space-y-4 bg-[#0d0f16]">
            <h3 id="modal-title" className="text-sm font-semibold text-white uppercase tracking-wider">
              Edit Memory Record
            </h3>
            
            <form onSubmit={handleEditContentSubmit} className="space-y-4">
              <div className="flex flex-col gap-2">
                <label className="text-xs text-gray-400" htmlFor="edit-text-area">
                  Content Payload
                </label>
                <textarea
                  id="edit-text-area"
                  rows={4}
                  className="glass-input resize-none w-full focus-ring"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setEditMemory(null);
                    setEditContent("");
                  }}
                  className="btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary text-xs focus-ring">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 4. Evidence Dialog Overlay Modal */}
      <EvidencePanel
        evidenceMemory={evidenceMemory}
        evidenceData={evidenceData}
        evidenceLoading={evidenceLoading}
        handleClose={handleCloseEvidence}
      />
    </div>
  );
}
