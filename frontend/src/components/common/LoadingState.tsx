import React from "react";

export function LoadingState({ count = 3, height = "h-24" }: { count?: number; height?: string }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, idx) => (
        <div key={idx} className={`glass-panel p-4 ${height} shimmer rounded-lg border border-white/5`}></div>
      ))}
    </div>
  );
}
