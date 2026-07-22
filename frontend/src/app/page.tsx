"use client";

import { useEffect, useState } from "react";
import {
  api,
  AuditEvent,
  CandidateMemory,
  ChatResponse,
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

  // UI Flow States
  const [connectionStatus, setConnectionStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [chatLoading, setChatLoading] = useState(false);
  const [govLoading, setGovLoading] = useState(false);
  const [editMemory, setEditMemory] = useState<MemoryRecord | null>(null);
  const [editContent, setEditContent] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  // Load all dashboard statistics & memory items
  const loadDashboardData = async (tId = tenantId, uId = userId) => {
    setGovLoading(true);
    setActionError(null);
    try {
      // 1. Fetch metrics
      const fetchedMetrics = await api.getMetrics(tId);
      setMetrics(fetchedMetrics);
      setConnectionStatus("connected");

      // 2. Fetch memories based on filters
      const fetchedMems = await api.listMemories(
        tId,
        uId,
        statusFilter || undefined,
        typeFilter || undefined
      );
      setMemories(fetchedMems);

      // 3. Fetch audit logs (last 50)
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
  const handleSendChat = async (e?: React.FormEvent) => {
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
  const handleEditContentSubmit = async (e: React.FormEvent) => {
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

  return (
    <div className="flex-1 flex flex-col h-screen min-h-screen">
      {/* Top Header Panel */}
      <header className="px-6 py-4 flex items-center justify-between border-b border-[rgba(255,255,255,0.08)] bg-[rgba(10,14,23,0.7)] backdrop-blur-md z-10">
        <div className="flex items-center gap-3">
          <div className="h-3 w-3 rounded-full bg-[#00f0ff] animate-pulse"></div>
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-[#00f0ff] to-[#8b5cf6] bg-clip-text text-transparent">
            MemoryOps AI <span className="text-sm font-semibold text-[rgba(255,255,255,0.5)]">v0.5.0 Control Panel</span>
          </h1>
        </div>

        {/* Backend Connection Indicator & Scope Configuration */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[rgba(255,255,255,0.4)]">Backend:</span>
            {connectionStatus === "checking" && (
              <span className="text-xs font-semibold text-amber-400">Checking...</span>
            )}
            {connectionStatus === "connected" && (
              <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Connected
              </span>
            )}
            {connectionStatus === "disconnected" && (
              <span className="text-xs font-semibold text-rose-500 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500"></span> Disconnected
              </span>
            )}
          </div>

          {/* Tenant and User Scope select */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-[rgba(255,255,255,0.4)]" htmlFor="tenant-input">Tenant:</label>
            <input
              id="tenant-input"
              type="text"
              className="glass-input text-xs py-1.5 px-3 max-w-[120px]"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-[rgba(255,255,255,0.4)]" htmlFor="user-input">User:</label>
            <input
              id="user-input"
              type="text"
              className="glass-input text-xs py-1.5 px-3 max-w-[120px]"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            />
          </div>
        </div>
      </header>

      {/* Error Overlay banner */}
      {actionError && (
        <div className="bg-rose-500/15 border-b border-rose-500/30 text-rose-300 text-xs px-6 py-2.5 flex items-center justify-between">
          <span><strong>Invariance/Policy Alert:</strong> {actionError}</span>
          <button onClick={() => setActionError(null)} className="text-rose-300 hover:text-white font-bold">✖</button>
        </div>
      )}

      {/* Main Workspace Layout */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Side Column: Chat interface */}
        <section className="w-[40%] border-r border-[rgba(255,255,255,0.08)] flex flex-col bg-[rgba(8,11,16,0.5)]">
          {/* Scrollable messages space */}
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
            {chatHistory.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8 opacity-60">
                <span className="text-4xl mb-4">🧠</span>
                <h3 className="text-sm font-semibold mb-2">Initialize Cognitive Stream</h3>
                <p className="text-xs max-w-xs text-[rgba(255,255,255,0.5)]">
                  Start messaging to extract and retrieve scoped memories. Try using the shortcut prompts below:
                </p>
                <div className="flex flex-col gap-2 mt-4 w-full max-w-xs">
                  <button
                    onClick={() => loadPromptShortcut("Remember that I prefer python for backend systems.")}
                    className="text-left text-xs bg-white/5 border border-white/5 hover:border-[#00f0ff]/20 p-2.5 rounded-lg hover:bg-white/10 transition"
                  >
                    "Remember that I prefer python for backend systems."
                  </button>
                  <button
                    onClick={() => loadPromptShortcut("My OpenAI API key is sk-proj-123456789012345678901234")}
                    className="text-left text-xs bg-white/5 border border-white/5 hover:border-red-500/20 p-2.5 rounded-lg hover:bg-white/10 transition"
                  >
                    "My API Key is sk-proj-123456789012345678901234" (Safety Block Test)
                  </button>
                  <button
                    onClick={() => loadPromptShortcut("Remember that I prefer rust for system code.")}
                    className="text-left text-xs bg-white/5 border border-white/5 hover:border-amber-500/20 p-2.5 rounded-lg hover:bg-white/10 transition"
                  >
                    "Remember that I prefer rust for system code."
                  </button>
                </div>
              </div>
            ) : (
              chatHistory.map((item, index) => (
                <div
                  key={index}
                  className={`flex flex-col gap-2 animate-fade-in ${
                    item.sender === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <div className="text-[10px] text-[rgba(255,255,255,0.4)] px-1">
                    {item.sender === "user" ? "User Scope" : "Cognitive Assistant"}
                  </div>
                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                      item.sender === "user"
                        ? "bg-[#8b5cf6]/20 border border-[#8b5cf6]/40 text-[#f3f5f9]"
                        : "bg-[rgba(20,26,38,0.7)] border border-[rgba(255,255,255,0.08)] text-[#f3f5f9]"
                    }`}
                  >
                    {item.text}
                  </div>

                  {/* Explainability metadata blocks */}
                  {item.sender === "assistant" && (item.usedMemories?.length || item.candidateMemories?.length) && (
                    <div className="w-full max-w-[90%] mt-2 p-3 bg-black/25 border border-white/5 rounded-lg flex flex-col gap-3">
                      
                      {/* Read Path: Used Memories */}
                      {item.usedMemories && item.usedMemories.length > 0 && (
                        <div>
                          <div className="text-[10px] font-bold tracking-wider uppercase text-emerald-400 mb-1.5">
                            Read Path: Used Memories ({item.usedMemories.length})
                          </div>
                          <div className="flex flex-col gap-2">
                            {item.usedMemories.map((m, mIdx) => (
                              <div key={mIdx} className="bg-white/5 p-2 rounded border border-white/5 text-[11px]">
                                <div className="flex items-center justify-between font-mono text-[10px] mb-1">
                                  <span className="text-[rgba(255,255,255,0.4)]">ID: {m.memory_id.substring(0, 8)}...</span>
                                  <span className="text-[#00f0ff]">Match Score: {(m.score * 100).toFixed(0)}%</span>
                                </div>
                                <p className="text-white mb-1">"{m.content}"</p>
                                {/* Score breakdown bars */}
                                <div className="grid grid-cols-3 gap-x-2 gap-y-1 font-mono text-[9px] text-[rgba(255,255,255,0.4)] border-t border-white/5 pt-1 mt-1">
                                  <div>Sem: {m.score_breakdown.semantic_score.toFixed(2)}</div>
                                  <div>Key: {m.score_breakdown.keyword_score.toFixed(2)}</div>
                                  <div>Imp: {m.score_breakdown.importance_score.toFixed(2)}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Write Path: Candidate Memories */}
                      {item.candidateMemories && item.candidateMemories.length > 0 && (
                        <div>
                          <div className="text-[10px] font-bold tracking-wider uppercase text-[#8b5cf6] mb-1.5">
                            Write Path: Extracted Candidate Decisions
                          </div>
                          <div className="flex flex-col gap-2">
                            {item.candidateMemories.map((cm, cmIdx) => (
                              <div key={cmIdx} className="bg-white/5 p-2 rounded border border-white/5 text-[11px]">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-semibold text-white">"{cm.content}"</span>
                                  <span
                                    className={`badge ${
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
                                <div className="font-mono text-[9px] text-[rgba(255,255,255,0.5)]">
                                  Reason: {cm.reason}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {item.traceId && (
                        <div className="text-[9px] font-mono text-[rgba(255,255,255,0.3)] text-right">
                          Trace ID: {item.traceId}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Message input console */}
          <form onSubmit={handleSendChat} className="p-4 border-t border-[rgba(255,255,255,0.08)] bg-[rgba(10,14,23,0.9)] flex flex-col gap-3">
            {/* Temporary chat switch */}
            <div className="flex items-center justify-between">
              <label htmlFor="temp-chat-toggle" className="flex items-center gap-2 cursor-pointer">
                <input
                  id="temp-chat-toggle"
                  type="checkbox"
                  className="rounded border-[rgba(255,255,255,0.15)] bg-black/40 text-[#00f0ff] focus:ring-0 focus:ring-offset-0"
                  checked={temporaryChat}
                  onChange={(e) => setTemporaryChat(e.target.checked)}
                />
                <span className="text-[11px] text-[rgba(255,255,255,0.5)] font-mono">
                  Temporary Chat (Bypass Persistent Storage Write/Read)
                </span>
              </label>
            </div>

            <div className="flex items-center gap-2">
              <input
                id="chat-input"
                type="text"
                className="flex-1 glass-input"
                placeholder="Talk to MemoryOps AI..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={chatLoading}
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={chatLoading || !message.trim()}
              >
                {chatLoading ? "Processing..." : "Send"}
              </button>
            </div>
          </form>
        </section>

        {/* Right Side Column: Governance and Dashboard Control Plane */}
        <section className="w-[60%] flex flex-col bg-[rgba(6,9,14,0.4)]">
          {/* Tab Navigation */}
          <div className="border-b border-[rgba(255,255,255,0.08)] flex justify-between items-center px-6">
            <nav className="flex gap-4">
              <button
                onClick={() => setActiveTab("memories")}
                className={`py-4 px-1 text-sm font-semibold border-b-2 transition-all ${
                  activeTab === "memories"
                    ? "border-[#00f0ff] text-[#00f0ff] glow-text"
                    : "border-transparent text-[rgba(255,255,255,0.5)] hover:text-white"
                }`}
              >
                Memories Registry
              </button>
              <button
                onClick={() => setActiveTab("audit")}
                className={`py-4 px-1 text-sm font-semibold border-b-2 transition-all ${
                  activeTab === "audit"
                    ? "border-[#00f0ff] text-[#00f0ff] glow-text"
                    : "border-transparent text-[rgba(255,255,255,0.5)] hover:text-white"
                }`}
              >
                Audit Stream
              </button>
              <button
                onClick={() => setActiveTab("metrics")}
                className={`py-4 px-1 text-sm font-semibold border-b-2 transition-all ${
                  activeTab === "metrics"
                    ? "border-[#00f0ff] text-[#00f0ff] glow-text"
                    : "border-transparent text-[rgba(255,255,255,0.5)] hover:text-white"
                }`}
              >
                System Analytics
              </button>
            </nav>

            <button
              onClick={() => loadDashboardData()}
              className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"
              disabled={govLoading}
            >
              {govLoading ? "Syncing..." : "Sync Dashboard"}
            </button>
          </div>

          {/* Scrollable Tab Views container */}
          <div className="flex-1 overflow-y-auto p-6">
            
            {/* View 1: Memories List & Actions */}
            {activeTab === "memories" && (
              <div className="space-y-6">
                
                {/* Filters */}
                <div className="glass-panel p-4 flex gap-4 items-center">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-[rgba(255,255,255,0.5)]" htmlFor="status-select">Status:</label>
                    <select
                      id="status-select"
                      className="glass-input text-xs py-1.5"
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                    >
                      <option value="">All Scopes (Active/Pending/Arch/Rej)</option>
                      <option value="active">Active only</option>
                      <option value="pending">Pending review</option>
                      <option value="archived">Archived</option>
                      <option value="rejected">Rejected</option>
                      <option value="deleted">Deleted (Exclusion Check)</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-2">
                    <label className="text-xs text-[rgba(255,255,255,0.5)]" htmlFor="type-select">Type:</label>
                    <select
                      id="type-select"
                      className="glass-input text-xs py-1.5"
                      value={typeFilter}
                      onChange={(e) => setTypeFilter(e.target.value)}
                    >
                      <option value="">All Types</option>
                      <option value="semantic">Semantic (Facts)</option>
                      <option value="procedural">Procedural (Preferences)</option>
                      <option value="episodic">Episodic (Events)</option>
                    </select>
                  </div>
                </div>

                {/* Listing */}
                <div className="space-y-3">
                  {memories.length === 0 ? (
                    <div className="text-center p-8 bg-[rgba(255,255,255,0.02)] border border-white/5 rounded-lg text-xs text-[rgba(255,255,255,0.4)]">
                      No memories match the current filters or user scopes.
                    </div>
                  ) : (
                    memories.map((m) => (
                      <div key={m.id} className="glass-panel p-4 flex items-start justify-between gap-4">
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-[10px] text-white/50 bg-white/5 px-1.5 py-0.5 rounded">
                              {m.memory_type}
                            </span>
                            {m.identity_slot && (
                              <span className="font-mono text-[10px] text-[#00f0ff] bg-[#00f0ff]/10 px-1.5 py-0.5 rounded">
                                Slot: {m.identity_slot}
                              </span>
                            )}
                            <span className={`badge badge-${m.status}`}>{m.status}</span>
                            <span className="text-[10px] text-[rgba(255,255,255,0.4)] font-mono">
                              Imp: {m.importance} | Conf: {m.confidence.toFixed(2)}
                            </span>
                          </div>
                          <p className="text-sm font-semibold text-white">"{m.content}"</p>
                          <div className="text-[10px] text-[rgba(255,255,255,0.3)] font-mono">
                            Created: {new Date(m.created_at).toLocaleString()}
                          </div>
                        </div>

                        {/* Action buttons mapping */}
                        <div className="flex items-center gap-2">
                          {m.status === "pending" && (
                            <>
                              <button
                                onClick={() => handleTransitionStatus(m.id, "active")}
                                className="btn-secondary text-[11px] py-1 px-2.5 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/10"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => handleTransitionStatus(m.id, "rejected")}
                                className="btn-secondary text-[11px] py-1 px-2.5 text-rose-400 border-rose-500/20 hover:bg-rose-500/10"
                              >
                                Reject
                              </button>
                            </>
                          )}
                          {m.status === "active" && (
                            <>
                              <button
                                onClick={() => handleTransitionStatus(m.id, "archived")}
                                className="btn-secondary text-[11px] py-1 px-2.5 text-amber-400 border-amber-500/20 hover:bg-amber-500/10"
                              >
                                Archive
                              </button>
                              <button
                                onClick={() => {
                                  setEditMemory(m);
                                  setEditContent(m.content);
                                }}
                                className="btn-secondary text-[11px] py-1 px-2.5"
                              >
                                Edit
                              </button>
                            </>
                          )}
                          {m.status === "archived" && (
                            <button
                              onClick={() => handleTransitionStatus(m.id, "active")}
                              className="btn-secondary text-[11px] py-1 px-2.5 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/10"
                            >
                              Restore
                            </button>
                          )}
                          {m.status !== "deleted" && (
                            <button
                              onClick={() => handleDeleteMemory(m.id)}
                              className="btn-secondary text-[11px] py-1 px-2.5 text-rose-500 border-rose-500/20 hover:bg-rose-500/10"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* View 2: Live Audit Log Stream */}
            {activeTab === "audit" && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold uppercase tracking-wider text-[rgba(255,255,255,0.4)] px-1">
                  Governance Audit Trail (Append-Only Log)
                </h3>
                
                {auditLogs.length === 0 ? (
                  <div className="text-center p-8 bg-[rgba(255,255,255,0.02)] border border-white/5 rounded-lg text-xs text-[rgba(255,255,255,0.4)]">
                    No governance actions have been audited yet for this tenant.
                  </div>
                ) : (
                  auditLogs.map((log) => (
                    <div key={log.id} className="glass-panel p-4 flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold text-[#00f0ff] uppercase">
                          {log.action.replace("memory_", "")}
                        </span>
                        <span className="font-mono text-[9px] text-[rgba(255,255,255,0.4)]">
                          {new Date(log.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-xs text-white">Reason: {log.reason}</p>
                      
                      <div className="flex justify-between items-center border-t border-white/5 pt-2 mt-1 text-[9px] font-mono text-[rgba(255,255,255,0.4)]">
                        <span>Event ID: {log.id}</span>
                        {log.trace_id && <span>Trace ID: {log.trace_id}</span>}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* View 3: Metrics Dashboard */}
            {activeTab === "metrics" && metrics && (
              <div className="space-y-6">
                {/* Counters Grid */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass-panel p-4 text-center">
                    <div className="text-2xl font-black text-white">{metrics.total_memories}</div>
                    <div className="text-[10px] uppercase font-bold text-[rgba(255,255,255,0.4)] mt-1">Total Stored</div>
                  </div>
                  <div className="glass-panel p-4 text-center">
                    <div className="text-2xl font-black text-emerald-400">{metrics.by_status.active}</div>
                    <div className="text-[10px] uppercase font-bold text-[rgba(255,255,255,0.4)] mt-1">Active Status</div>
                  </div>
                  <div className="glass-panel p-4 text-center">
                    <div className="text-2xl font-black text-[#8b5cf6]">{metrics.audit_events}</div>
                    <div className="text-[10px] uppercase font-bold text-[rgba(255,255,255,0.4)] mt-1">Audit Entries</div>
                  </div>
                </div>

                {/* Status Breakdown list */}
                <div className="glass-panel p-5 space-y-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-white">Status Breakdown</h4>
                  <div className="space-y-3">
                    {Object.entries(metrics.by_status).map(([key, val]) => {
                      const percentage = metrics.total_memories > 0 ? (val / metrics.total_memories) * 100 : 0;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono">
                            <span className="capitalize">{key}</span>
                            <span>{val} ({percentage.toFixed(0)}%)</span>
                          </div>
                          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                key === "active"
                                  ? "bg-emerald-400"
                                  : key === "pending"
                                  ? "bg-amber-400"
                                  : key === "rejected"
                                  ? "bg-rose-500"
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

                {/* Action Counts list */}
                <div className="glass-panel p-5 space-y-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-white">Core Action Events</h4>
                  <div className="space-y-3">
                    {Object.entries(metrics.by_action).map(([key, val]) => {
                      const percentage = metrics.audit_events > 0 ? (val / metrics.audit_events) * 100 : 0;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono">
                            <span className="capitalize">{key.replace("memory_", "")}</span>
                            <span>{val} ({percentage.toFixed(0)}%)</span>
                          </div>
                          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
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
        </section>
      </main>

      {/* Edit content Modal Dialog */}
      {editMemory && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">Edit Memory Record</h3>
            
            <form onSubmit={handleEditContentSubmit} className="space-y-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-[rgba(255,255,255,0.4)]" htmlFor="edit-text-area">Content Payload:</label>
                <textarea
                  id="edit-text-area"
                  rows={4}
                  className="glass-input resize-none w-full"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditMemory(null);
                    setEditContent("");
                  }}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
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
