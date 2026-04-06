import type { OpenBBIndicatorSlug } from "@/lib/config";

export interface IndicatorResponse<T = unknown> {
  data: T;
  as_of?: string;
  cached?: boolean;
  source?: string;
}

export interface HealthResponse {
  status: string;
  timestamp?: string;
  service?: string;
}

export interface APIError {
  message: string;
  status?: number;
  details?: unknown;
}

export interface UseIndicatorResult<T = unknown> {
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
  refetchAll: () => Promise<void>;
}

export interface AAIIData {
  bullish: number;
  bearish: number;
  neutral: number;
  total?: number;
  date?: string;
}

export interface OpenBBIndicatorData {
  value: number;
  date?: string;
}