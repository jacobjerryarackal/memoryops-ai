import React from "react";

interface NavbarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  systemVersion: string;
  connectionStatus: "checking" | "connected" | "disconnected";
}

export function Navbar({
  sidebarOpen,
  setSidebarOpen,
  systemVersion,
  connectionStatus,
}: NavbarProps) {
  return (
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
  );
}
