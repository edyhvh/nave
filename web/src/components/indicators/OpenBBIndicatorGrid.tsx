import { useIndicators } from "@/hooks/useIndicators";
import { formatCurrency, formatPercentage, safeGet } from "@/lib/utils";
import { type OpenBBIndicatorData } from "@/types/api";
import IndicatorCard from "./IndicatorCard";

const INDICATOR_LABELS: Record<string, string> = {
  tga: "Treasury General Account",
  rrp: "Reverse Repo Facility",
  fed_funds: "Federal Funds Rate",
  cpi: "Consumer Price Index",
  pce: "Personal Consumption Expenditures",
  unrate: "Unemployment Rate",
  payems: "Non-farm Payrolls",
  dgs10: "10-Year Treasury Rate",
  yield_curve_10y_2y: "10Y-2Y Yield Spread",
};

const INDICATOR_FORMATTERS: Record<string, (value: number) => string> = {
  tga: formatCurrency,
  rrp: formatCurrency,
  fed_funds: (value) => formatPercentage(value),
  cpi: (value) => value.toFixed(2),
  pce: (value) => value.toFixed(2),
  unrate: (value) => formatPercentage(value),
  payems: (value) => value.toLocaleString(),
  dgs10: (value) => `${value.toFixed(2)}%`,
  yield_curve_10y_2y: (value) => `${value.toFixed(2)}%`,
};

const INDICATOR_COLORS: Record<string, string> = {
  tga: "text-blue-600",
  rrp: "text-green-600",
  fed_funds: "text-red-600",
  cpi: "text-purple-600",
  pce: "text-indigo-600",
  unrate: "text-orange-600",
  payems: "text-teal-600",
  dgs10: "text-pink-600",
  yield_curve_10y_2y: "text-cyan-600",
};

interface OpenBBIndicatorCardProps {
  slug: string;
  data: OpenBBIndicatorData | undefined;
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  key?: string;
}

function OpenBBIndicatorCard({
  slug,
  data,
  loading,
  error,
  onRefresh,
}: OpenBBIndicatorCardProps) {
  const label = INDICATOR_LABELS[slug] || slug;
  const formatter =
    INDICATOR_FORMATTERS[slug] || ((value: number) => value.toString());
  const colorClass = INDICATOR_COLORS[slug] || "text-gray-600";

  const value = safeGet(data, "value", null);
  const date = safeGet(data, "date", null);

  // Show loading skeleton when loading and no data yet
  const showLoading = loading && value === null;

  return (
    <IndicatorCard
      title={label}
      indicator={null}
      loading={showLoading}
      error={error}
      onRefresh={onRefresh}
      className="h-full"
    >
      {value !== null ? (
        <div className="text-center">
          <div className={`text-2xl font-bold ${colorClass} mb-1`}>
            {formatter(value)}
          </div>
          {date && (
            <div className="text-xs text-gray-500">
              {new Date(date).toLocaleDateString()}
            </div>
          )}
        </div>
      ) : !showLoading && !error ? (
        <div className="text-center text-gray-500 text-sm">Loading...</div>
      ) : null}
    </IndicatorCard>
  );
}

export default function OpenBBIndicatorGrid() {
  const { indicators, loading, errors, refetch } = useIndicators();

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-ink">Economic Indicators</h2>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Object.entries(INDICATOR_LABELS).map(([slug, label]) => {
          const indicator = indicators[slug];
          const error = errors[slug];
          const data = indicator?.data as OpenBBIndicatorData | undefined;

          return (
            <OpenBBIndicatorCard
              key={slug}
              slug={slug}
              data={data}
              loading={loading && !indicator && !error}
              error={error?.message || null}
              onRefresh={() => refetch(slug)}
            />
          );
        })}
      </div>

      {loading && Object.keys(indicators).length === 0 && (
        <div className="text-center text-gray-500 py-8">
          Loading economic indicators...
        </div>
      )}
    </div>
  );
}
