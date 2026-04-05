/// <reference path="../../types/shims.d.ts" />

import { type IndicatorResponse } from "@/types/api";

interface IndicatorCardProps {
  title: string;
  indicator: IndicatorResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  children?: React.ReactNode;
}

export default function IndicatorCard({
  title,
  indicator,
  loading,
  error,
  onRefresh,
  children,
}: IndicatorCardProps) {
  return (
    <div className="rounded-2xl border border-border bg-white p-6 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-ink">{title}</h3>
        <div className="flex items-center gap-2">
          {indicator?.cached && (
            <span className="text-xs text-gray-400 italic">cached</span>
          )}
          {indicator?.as_of && (
            <span className="text-xs text-gray-400">
              {new Date(indicator.as_of).toLocaleTimeString()}
            </span>
          )}
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={loading}
              className="text-xs text-blue-500 hover:text-blue-700 disabled:opacity-50 px-2 py-1 rounded border border-blue-200 hover:border-blue-400"
            >
              {loading ? "..." : "↻"}
            </button>
          )}
        </div>
      </div>

      {loading && !indicator && (
        <div className="flex items-center justify-center h-20 text-gray-400">
          <span className="animate-pulse">Loading…</span>
        </div>
      )}

      {error && (
        <div className="text-sm text-red-500 bg-red-50 rounded-lg p-3 mb-3">
          {error}
        </div>
      )}

      {children}
    </div>
  );
}
