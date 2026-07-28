"use client";

import { useEffect, useState, FormEvent } from "react";
import {
  api,
  AuditEvent,
  CandidateMemory,
  MemoryRecord,
  TenantMetrics,
  UsedMemory,
} from "../lib/api";

export default function Home() {
  // Scoping Coordinates
  const [tenantId, setTenantId] = useState("tenant_demo");
  const [userId, setUserId] = useState("user_demo");
  
  // Chat States
  const [message, setMessage] = useState("");
  const [temporaryChat, setTemporaryChat] = useState(false);
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

  // Governance States
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<TenantMetrics | null>(null);
  
  // Filters & Tabs
  const [activeTab, setActiveTab] = useState<"memories" | "audit" | "metrics">("memories");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // UI Flow States
  const [connectionStatus, setConnectionStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [systemVersion, setSystemVersion] = useState("1.0.0");
  const [chatLoading, setChatLoading] = useState(false);
  const [govLoading, setGovLoading] = useState(false);
  const [editMemory, setEditMemory] = useState<MemoryRecord | null>(null);
  const [editContent, setEditContent] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load all dashboard statistics & memory items
  const loadDashboardData = async (tId = tenantId, uId = userId) => {
    setGovLoading(true);
    setActionError(null);
    try {
      // 1. Verify backend health using the documented healthz endpoint
      const health = await api.checkHealth();
      setConnectionStatus("connected");
      if (health && health.version) {
        setSystemVersion(health.version);
      }

      // 2. Fetch metrics
      const fetchedMetrics = await api.getMetrics(tId);
      setMetrics(fetchedMetrics);

      // 3. Fetch memories based on filters
      const fetchedMems = await api.listMemories(
        tId,
        uId,
        statusFilter || undefined,
        typeFilter || undefined
      );
      setMemories(fetchedMems);

      // 4. Fetch audit logs (last 50)
      const fetchedAudits = await api.listAudit(tId, undefined, undefined, 50);
      setAuditLogs(fetchedAudits);
    } catch (err: any) {
      console.error(err);
      setConnectionStatus("disconnected");
      setActionError(err.message || "Failed to contact MemoryOps API backend.");
    } finally {
      setGovLoading(false);
    }
  };

  // Trigger load on state mounts or scopes change
  useEffect(() => {
    loadDashboardData();
  }, [tenantId, userId, statusFilter, typeFilter]);

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
      const resp = await api.chat(tenantId, userId, userPrompt, temporaryChat);
      
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
    } catch (err: any) {
      console.error(err);
      setChatHistory((prev) => [
        ...prev,
        {
          sender: "assistant",
          text: `[SYSTEM ERROR]: ${err.message || "Failed to communicate with write path."}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Perform memory status transition (PATCH)
  const handleTransitionStatus = async (memoryId: string, nextStatus: string) => {
    setActionError(null);
    try {
      await api.patchMemory(memoryId, {
        tenant_id: tenantId,
        user_id: userId,
        status: nextStatus,
      });
      await loadDashboardData();
    } catch (err: any) {
      setActionError(err.message);
    }
  };

  // Perform content edit update (PATCH)
  const handleEditContentSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editMemory) return;
    setActionError(null);
    try {
      await api.patchMemory(editMemory.id, {
        tenant_id: tenantId,
        user_id: userId,
        content: editContent,
      });
      setEditMemory(null);
      setEditContent("");
      await loadDashboardData();
    } catch (err: any) {
      setActionError(err.message);
    }
  };

  // Perform memory logical deletion (DELETE)
  const handleDeleteMemory = async (memoryId: string) => {
    if (!confirm("Are you sure you want to logically delete this memory record?")) return;
    setActionError(null);
    try {
      await api.deleteMemory(memoryId, tenantId, userId);
      await loadDashboardData();
    } catch (err: any) {
      setActionError(err.message);
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

  // Local filter for search queries
  const filteredMemories = memories.filter((m) =>
    m.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (m.identity_slot && m.identity_slot.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="flex-1 flex flex-col lg:flex-row h-screen min-h-screen bg-[#090a0f] text-[#e4e7eb] font-sans antialiased overflow-hidden">
      
      {/* 1. Left Collapsible Sidebar */}
      <aside
        className={`bg-[#0d0f16] border-r border-white/5 flex flex-col transition-all duration-300 ease-in-out z-20 ${
          sidebarOpen ? "w-full lg:w-72" : "w-0 lg:w-0 overflow-hidden border-none"
        }`}
        aria-label="Configuration Settings"
      >
        <div className="p-5 flex items-center justify-between border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <div className="h-2 w-2 rounded-full bg-[#00f0ff] animate-pulse"></div>
            <span className="font-bold text-sm tracking-wide uppercase text-white">MemoryOps Control</span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-gray-400 hover:text-white focus:outline-none"
            aria-label="Close Sidebar"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Coordinates section */}
          <div className="space-y-4">
            <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Scope Coordinates</h3>
            <div className="space-y-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-gray-400" htmlFor="tenant-input">Tenant ID</label>
                <input
                  id="tenant-input"
                  type="text"
                  className="glass-input focus-ring w-full text-xs font-mono"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-gray-400" htmlFor="user-input">User ID</label>
                <input
                  id="user-input"
                  type="text"
                  className="glass-input focus-ring w-full text-xs font-mono"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Quick Prompts shortcuts */}
          <div className="space-y-3">
            <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Quick Seed Prompts</h3>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => loadPromptShortcut("Remember that I prefer python for backend systems.")}
                className="text-left text-xs bg-white/3 border border-white/5 hover:border-[#00f0ff]/20 p-2.5 rounded-md hover:bg-white/5 transition focus-ring text-gray-300"
              >
                "Remember that I prefer python for backend systems."
              </button>
              <button
                onClick={() => loadPromptShortcut("Remember that I prefer rust for system code.")}
                className="text-left text-xs bg-white/3 border border-white/5 hover:border-[#00f0ff]/20 p-2.5 rounded-md hover:bg-white/5 transition focus-ring text-gray-300"
              >
                "Remember that I prefer rust for system code."
              </button>
              <button
                onClick={() => loadPromptShortcut("My OpenAI API key is sk-proj-123456789012345678901234")}
                className="text-left text-xs bg-red-500/5 border border-red-500/10 hover:border-red-500/30 p-2.5 rounded-md hover:bg-red-500/10 transition focus-ring text-red-300/80"
              >
                "My API Key is sk-proj-..." (Safety Block Test)
              </button>
            </div>
          </div>

          {/* System Health checklist */}
          <div className="space-y-3 pt-2">
            <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Readiness status</h3>
            <div className="bg-black/20 rounded-md p-3.5 border border-white/5 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Database Engine</span>
                <span className="text-emerald-400 font-mono">Ready</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Policy Rules</span>
                <span className="text-emerald-400 font-mono">Enforced</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Embedding Engine</span>
                <span className="text-emerald-400 font-mono">Connected</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer info */}
        <div className="p-5 border-t border-white/5 text-[10px] text-gray-500 font-mono flex flex-col gap-1">
          <div>Workspace: jacobjerryarackal</div>
          <div>Branch: frozen-mvp</div>
        </div>
      </aside>

      {/* 2. Main Workspace */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        
        {/* Top bar panel */}
        <header className="h-14 px-6 border-b border-white/5 flex items-center justify-between bg-[#0d0f16]/40 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-gray-400 hover:text-white mr-1 focus:outline-none focus:ring-1 focus:ring-[#00f0ff] p-1 rounded"
                aria-label="Open Configuration Sidebar"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            )}
            <h1 className="text-sm font-semibold tracking-tight text-white flex items-center gap-2">
              MemoryOps AI Dashboard
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-gray-400 border border-white/5">
                v{systemVersion}
              </span>
            </h1>
          </div>

          <div className="flex items-center gap-4">
            {/* Status indicators */}
            <div className="flex items-center gap-2.5">
              {connectionStatus === "checking" && (
                <span className="text-[11px] font-mono text-amber-400 animate-pulse">Syncing...</span>
              )}
              {connectionStatus === "connected" && (
                <div className="flex items-center gap-1.5 bg-emerald-500/5 border border-emerald-500/10 rounded-full px-2.5 py-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                  <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-wider">Online</span>
                </div>
              )}
              {connectionStatus === "disconnected" && (
                <div className="flex items-center gap-1.5 bg-red-500/5 border border-red-500/10 rounded-full px-2.5 py-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-ping"></span>
                  <span className="text-[10px] font-mono text-red-500 uppercase tracking-wider">Offline</span>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Invariance error banners */}
        {actionError && (
          <div
            className="bg-red-500/8 border-b border-red-500/20 text-red-300 text-xs px-6 py-3 flex items-center justify-between gap-4 animate-fade-in"
            role="alert"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm">⚠️</span>
              <span><strong>Policy Violation:</strong> {actionError}</span>
            </div>
            <button
              onClick={() => setActionError(null)}
              className="text-red-300 hover:text-white font-bold p-1 focus:outline-none"
              aria-label="Dismiss Error"
            >
              ✖
            </button>
          </div>
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
                                    <p className="text-gray-300">"{m.content}"</p>
                                    
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
                                      <span className="text-gray-300 font-medium leading-relaxed">"{cm.content}"</span>
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

                  {/* Skeletons or list items */}
                  {govLoading ? (
                    <div className="space-y-3">
                      {[1, 2, 3].map((n) => (
                        <div key={n} className="glass-panel p-4 h-24 shimmer rounded-lg border border-white/5"></div>
                      ))}
                    </div>
                  ) : filteredMemories.length === 0 ? (
                    <div className="text-center py-10 bg-white/2 rounded-lg border border-white/5 text-xs text-gray-500">
                      No records matched the selected query or scopes.
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {filteredMemories.map((m) => (
                        <div key={m.id} className="glass-panel p-4 flex flex-col md:flex-row items-start justify-between gap-4">
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
                              "{m.content}"
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
                                  onClick={() => {
                                    setEditMemory(m);
                                    setEditContent(m.content);
                                  }}
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
                              <button
                                onClick={() => handleDeleteMemory(m.id)}
                                className="btn-secondary text-[10px] py-1 px-2.5 text-red-500/80 border-red-500/10 hover:bg-red-500/5 focus-ring"
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Audit Logs */}
              {activeTab === "audit" && (
                <div className="space-y-4">
                  {govLoading ? (
                    <div className="space-y-3">
                      {[1, 2].map((n) => (
                        <div key={n} className="glass-panel p-4 h-20 shimmer rounded-lg border border-white/5"></div>
                      ))}
                    </div>
                  ) : auditLogs.length === 0 ? (
                    <div className="text-center py-10 bg-white/2 rounded-lg border border-white/5 text-xs text-gray-500">
                      No audited history log events detected.
                    </div>
                  ) : (
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
                  ) : !metrics ? (
                    <div className="text-center py-10 bg-white/2 rounded-lg border border-white/5 text-xs text-gray-500">
                      Failed to fetch statistics.
                    </div>
                  ) : (
                    <div className="space-y-5">
                      <div className="grid grid-cols-3 gap-4">
                        <div className="glass-panel p-4 text-center">
                          <div className="text-xl font-bold text-white">{metrics.total_memories}</div>
                          <div className="text-[9px] uppercase tracking-wider font-semibold text-gray-400 mt-1">Total Seeded</div>
                        </div>
                        <div className="glass-panel p-4 text-center">
                          <div className="text-xl font-bold text-emerald-400">{metrics.by_status.active}</div>
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
    </div>
  );
}
