import React from "react";

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-10 bg-white/2 rounded-lg border border-white/5 text-xs text-gray-500">
      {message}
    </div>
  );
}
