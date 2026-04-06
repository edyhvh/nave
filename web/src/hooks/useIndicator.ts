import { useState, useEffect, useCallback, useRef } from "react";
import { apiClient, APIClientError } from "@/lib/api";
import {
  type UseIndicatorResult,
  type IndicatorResponse,
  type APIError,
} from "@/types/api";

/**
 * Hook for fetching a single indicator with loading/error states
 */
export function useIndicator<T extends () => Promise<IndicatorResponse>>(
  fetchFn: T,
  options: {
    autoRefresh?: boolean;
    refreshInterval?: number;
    retryOnError?: boolean;
    maxRetries?: number;
  } = {},
): UseIndicatorResult {
  const {
    autoRefresh = false,
    refreshInterval = 5 * 60 * 1000, // 5 minutes
    retryOnError = true,
    maxRetries = 3,
  } = options;

  const [data, setData] = useState<IndicatorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | null>(null);
  const intervalRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(
    async (showLoading = true) => {
      if (showLoading) setLoading(true);
      setError(null);

      try {
        const result = await fetchFn();
        if (mountedRef.current) {
          setData(result);
          setError(null);
        }
      } catch (err: unknown) {
        if (mountedRef.current) {
          let message = "Unknown error";
          let status: number | undefined = undefined;
          let details: any = err;
          if (err instanceof APIClientError) {
            message = err.message;
            status = err.status;
            details = err.details;
          }
          const apiError: APIError = {
            message,
            status,
            details,
          };
          setError(apiError);
          // Don't clear data on error - keep stale data visible
        }
      } finally {
        if (mountedRef.current && showLoading) {
          setLoading(false);
        }
      }
    },
    [fetchFn],
  );

  const refetch = useCallback(async () => {
    await fetchData(true);
  }, [fetchData]);

  // Initial fetch - only run once on mount
  const initialFetchDone = useRef(false);
  useEffect(() => {
    if (!initialFetchDone.current) {
      initialFetchDone.current = true;
      fetchData(true);
    }
  }, [fetchData]);

  // Auto-refresh setup
  useEffect(() => {
    if (autoRefresh && refreshInterval > 0) {
      intervalRef.current = setInterval(() => {
        fetchData(false); // Don't show loading for auto-refresh
      }, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [autoRefresh, refreshInterval, fetchData]);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return {
    data,
    loading,
    error,
    refetch,
  };
}
