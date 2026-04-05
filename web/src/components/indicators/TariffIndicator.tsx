/// <reference path="../../types/shims.d.ts" />

import { useIndicator } from "@/hooks/useIndicator";
import { apiClient } from "@/lib/api";
import { formatCurrency, safeGet } from "@/lib/utils";
import IndicatorCard from "./IndicatorCard";

const fetchTariff = () => apiClient.getTariff();

export default function TariffIndicator() {
  const { data, loading, error, refetch } = useIndicator(fetchTariff, {
    autoRefresh: false,
  });

  const tariffData = data?.data as Record<string, unknown> | undefined;

  return (
    <IndicatorCard
      title="Tariff Revenue"
      indicator={data}
      loading={loading}
      error={error?.message || null}
      onRefresh={refetch}
    >
      {tariffData && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {formatCurrency(safeGet(tariffData, "revenue", 0))}
              </div>
              <div className="text-sm text-gray-600">Revenue</div>
            </div>
            <div className="text-center">
              <div
                className={`text-2xl font-bold ${
                  (safeGet(tariffData, "change_pct", 0) as number) >= 0
                    ? "text-green-600"
                    : "text-red-600"
                }`}
              >
                {(safeGet(tariffData, "change_pct", 0) as number).toFixed(1)}%
              </div>
              <div className="text-sm text-gray-600">Change</div>
            </div>
          </div>
        </div>
      )}
    </IndicatorCard>
  );
}
