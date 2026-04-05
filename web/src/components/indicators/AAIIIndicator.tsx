/// <reference path="../../types/shims.d.ts" />

import { useIndicator } from "@/hooks/useIndicator";
import { apiClient } from "@/lib/api";
import { formatPercentage, safeGet } from "@/lib/utils";
import { type AAIIData } from "@/types/api";
import IndicatorCard from "./IndicatorCard";

const fetchAAII = () => apiClient.getAAII();

export default function AAIIIndicator() {
  const { data, loading, error, refetch } = useIndicator(fetchAAII, {
    autoRefresh: false,
  });

  const aaiiData = data?.data as AAIIData | undefined;

  return (
    <IndicatorCard
      title="AAII Sentiment Survey"
      indicator={data}
      loading={loading}
      error={error?.message || null}
      onRefresh={refetch}
    >
      {aaiiData && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {formatPercentage(safeGet(aaiiData, "bullish", 0))}
              </div>
              <div className="text-sm text-gray-600">Bullish</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">
                {formatPercentage(safeGet(aaiiData, "bearish", 0))}
              </div>
              <div className="text-sm text-gray-600">Bearish</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-600">
                {formatPercentage(safeGet(aaiiData, "neutral", 0))}
              </div>
              <div className="text-sm text-gray-600">Neutral</div>
            </div>
          </div>

          {aaiiData.total && (
            <div className="text-center text-sm text-gray-500">
              Total responses: {aaiiData.total.toLocaleString()}
            </div>
          )}

          {aaiiData.date && (
            <div className="text-center text-sm text-gray-500">
              Survey date: {new Date(aaiiData.date).toLocaleDateString()}
            </div>
          )}
        </div>
      )}
    </IndicatorCard>
  );
}
