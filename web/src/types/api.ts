import type { OpenBBIndicatorSlug } from "@/lib/config";

export interface IndicatorResponse<T = Record<string, any>> {
  name: string;
  as_of: string | Date;
  source: string;
  data: T;
  cached: boolean;
}

export interface APIError {
  message: string;
  status?: number;
  details?: any;
}

export interface UseIndicatorResult<T = Record<string, any>> {
  data: IndicatorResponse<T> | null;
  loading: boolean;
  error: APIError | null;
  refetch: () => Promise<void>;
}

export interface UseIndicatorsResult {
  indicators: Record<string, IndicatorResponse>;
  loading: boolean;
  errors: Record<string, APIError>;
  refetch: (indicator?: OpenBBIndicatorSlug | string) => Promise<void>;
  refetchAll?: () => Promise<void>;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  version?: string;
  services?: Record<string, boolean>;
}

export type AAIIData = {
  sentiment: "bullish" | "bearish" | "neutral";
  value: number;
  date: string;
  [key: string]: any;
};

export type OpenBBIndicatorData = IndicatorResponse;
export type CBDCData = any;
export type TariffData = any;
