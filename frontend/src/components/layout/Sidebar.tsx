import React from "react";

interface SidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  tenantId: string;
  setTenantId: (id: string) => void;
  userId: string;
  setUserId: (id: string) => void;
  loadPromptShortcut: (text: string) => void;
}

export function Sidebar({
  sidebarOpen,
  setSidebarOpen,
  tenantId,
  setTenantId,
  userId,
  setUserId,
  loadPromptShortcut,
}: SidebarProps) {
  return (
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
              &quot;Remember that I prefer python for backend systems.&quot;
            </button>
            <button
              onClick={() => loadPromptShortcut("Remember that I prefer rust for system code.")}
              className="text-left text-xs bg-white/3 border border-white/5 hover:border-[#00f0ff]/20 p-2.5 rounded-md hover:bg-white/5 transition focus-ring text-gray-300"
            >
              &quot;Remember that I prefer rust for system code.&quot;
            </button>
            <button
              onClick={() => loadPromptShortcut("My OpenAI API key is sk-proj-123456789012345678901234")}
              className="text-left text-xs bg-red-500/5 border border-red-500/10 hover:border-red-500/30 p-2.5 rounded-md hover:bg-red-500/10 transition focus-ring text-red-300/80"
            >
              &quot;My API Key is sk-proj-...&quot; (Safety Block Test)
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
  );
}
