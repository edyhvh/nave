import { useState, useEffect, useCallback, useRef } from "react";
import { apiClient, APIClientError } from "@/lib/api";
import { OPENBB_INDICATORS, type OpenBBIndicatorSlug } from "@/lib/config";
import {
  type UseIndicatorsResult,
  type IndicatorResponse,
  type APIError,
} from "@/types/api";

/**
 * Hook for fetching multiple indicators concurrently
 */
export function useIndicators(
  slugs: OpenBBIndicatorSlug[] = [...OPENBB_INDICATORS],
  options: {
    autoRefresh?: boolean;
    refreshInterval?: number;
  } = {},
): UseIndicatorsResult {
  const { autoRefresh = false, refreshInterval = 5 * 60 * 1000 } = options;

  const [indicators, setIndicators] = useState<
    Record<string, IndicatorResponse>
  >({});
  const [loading, setLoading] = useState(true); // Start as loading
  const [errors, setErrors] = useState<Record<string, APIError>>({});
  const intervalRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const fetchAllIndicators = useCallback(
    async (showLoading = true) => {
      if (showLoading) setLoading(true);
      setErrors({});

      try {
        const results = await apiClient.getMultipleIndicators(slugs);
        if (mountedRef.current) {
          setIndicators(results);
          setErrors({});
        }
      } catch (err: unknown) {
        if (mountedRef.current) {
          if (
            err instanceof APIClientError &&
            err.details &&
            typeof err.details === "object"
          ) {
            // Handle partial failures - some indicators failed
            const errorDetails = err.details as Record<string, APIClientError>;
            setErrors(errorDetails);
            // Don't clear indicators - keep stale data
          } else {
            // Complete failure - set errors but don't clear indicators
            const apiError: APIError = {
              message:
                err instanceof APIClientError ? err.message : "Unknown error",
              status: err instanceof APIClientError ? err.status : undefined,
              details: err instanceof APIClientError ? err.details : err,
            };

            const newErrors: Record<string, APIError> = {};
            slugs.forEach((slug) => {
              newErrors[slug] = apiError;
            });
            setErrors(newErrors);
            // Don't clear indicators - keep stale data visible
          }
        }
      } finally {
        if (mountedRef.current && showLoading) {
          setLoading(false);
        }
      }
    },
    [slugs],
  );

  const refetch = useCallback(
    async (indicator?: string) => {
      if (indicator) {
        // Refetch single indicator
        try {
          const result = await apiClient.getOpenBBIndicator(
            indicator as OpenBBIndicatorSlug,
          );
          if (mountedRef.current) {
            setIndicators((prev: Record<string, IndicatorResponse>) => ({
              ...prev,
              [indicator]: result,
            }));
            setErrors((prev: Record<string, APIError>) => {
              const newErrors = { ...prev };
              delete newErrors[indicator];
              return newErrors;
            });
          }
        } catch (err) {
          if (mountedRef.current) {
            const apiError: APIError = {
              message:
                err instanceof APIClientError ? err.message : "Unknown error",
              status: err instanceof APIClientError ? err.status : undefined,
              details: err instanceof APIClientError ? err.details : err,
            };
            setErrors((prev: Record<string, APIError>) => ({
              ...prev,
              [indicator]: apiError,
            }));
          }
        }
      } else {
        await fetchAllIndicators(true);
      }
    },
    [fetchAllIndicators],
  );

  const refetchAll = useCallback(async () => {
    await fetchAllIndicators(true);
  }, [fetchAllIndicators]);

  // Initial fetch - only run once on mount
  const initialFetchDone = useRef(false);
  useEffect(() => {
    if (!initialFetchDone.current) {
      initialFetchDone.current = true;
      fetchAllIndicators(true);
    }
  }, [fetchAllIndicators]);

  // Auto-refresh setup
  useEffect(() => {
    if (autoRefresh && refreshInterval > 0) {
      intervalRef.current = setInterval(() => {
        fetchAllIndicators(false); // Don't show loading for auto-refresh
      }, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [autoRefresh, refreshInterval, fetchAllIndicators]);

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
    indicators,
    loading,
    errors,
    refetch,
    refetchAll,
  };
}
