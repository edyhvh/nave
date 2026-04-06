/// <reference path="../../types/shims.d.ts" />

import { useIndicator } from "@/hooks/useIndicator";
import { apiClient } from "@/lib/api";
import { safeGet } from "@/lib/utils";
import IndicatorCard from "./IndicatorCard";

const fetchCBDC = () => apiClient.getCBDC();

export default function CBDCIndicator() {
  const { data, loading, error, refetch } = useIndicator(fetchCBDC, {
    autoRefresh: false,
  });

  const cbdcData = data?.data as Record<string, unknown> | undefined;

  return (
    <IndicatorCard
      title="CBDC Tracker"
      indicator={data}
      loading={loading}
      error={error?.message || null}
      onRefresh={refetch}
    >
      {cbdcData && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {safeGet(cbdcData, "active_projects", 0)}
              </div>
              <div className="text-sm text-gray-600">Active Projects</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {safeGet(cbdcData, "adopted_countries", 0)}
              </div>
              <div className="text-sm text-gray-600">Adopted Countries</div>
            </div>
          </div>
          <div className="text-center text-sm text-gray-500">
            Status:{" "}
            <span className="font-medium capitalize">
              {safeGet(cbdcData, "global_status", "—")}
            </span>
          </div>
        </div>
      )}
    </IndicatorCard>
  );
}
