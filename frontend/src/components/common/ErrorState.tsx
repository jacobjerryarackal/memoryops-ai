import React from "react";

interface ErrorStateProps {
  message: string;
  onDismiss: () => void;
}

export function ErrorState({ message, onDismiss }: ErrorStateProps) {
  return (
    <div
      className="bg-red-500/8 border-b border-red-500/20 text-red-300 text-xs px-6 py-3 flex items-center justify-between gap-4 animate-fade-in"
      role="alert"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm">⚠️</span>
        <span><strong>Policy Violation:</strong> {message}</span>
      </div>
      <button
        onClick={onDismiss}
        className="text-red-300 hover:text-white font-bold p-1 focus:outline-none"
        aria-label="Dismiss Error"
      >
        ✖
      </button>
    </div>
  );
}
