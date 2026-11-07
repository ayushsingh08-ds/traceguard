import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "../api/client";
import { IncidentListItem, IncidentStatus, SeverityLevel } from "../types/incident";

interface UseIncidentsFilter {
  status?: IncidentStatus;
  severity?: SeverityLevel;
  service?: string;
}

interface UseIncidentsReturn {
  incidents: IncidentListItem[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateIncidentStatusOptimistic: (
    incidentId: string,
    newStatus: IncidentStatus,
    actor?: string
  ) => Promise<boolean>;
}

export function useIncidents(filters: UseIncidentsFilter = {}): UseIncidentsReturn {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIncidents = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      setError(null);
      try {
        const params: Record<string, string | undefined> = {
          status: filters.status,
          severity: filters.severity,
          service: filters.service,
        };
        const data = await apiClient.get<IncidentListItem[]>("/incidents", {
          params,
          signal,
        });
        setIncidents(data);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // Aborted by clean effect cleanup; preserve current data state
          return;
        }
        const message = err instanceof ApiError ? err.message : "Failed to load incidents";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [filters.status, filters.severity, filters.service]
  );

  useEffect(() => {
    // AbortController cancels in-flight fetch on rapid filter switching,
    // eliminating race conditions where an older, slower request overwrites newer data.
    const controller = new AbortController();
    fetchIncidents(controller.signal);

    return () => {
      controller.abort();
    };
  }, [fetchIncidents]);

  const updateIncidentStatusOptimistic = async (
    incidentId: string,
    newStatus: IncidentStatus,
    actor: string = "lead-engineer"
  ): Promise<boolean> => {
    // 1. Snapshot prior state for deterministic rollback
    const previousSnapshot = [...incidents];

    // 2. Immediate local optimistic mutation
    setIncidents((prev) =>
      prev.map((inc) => {
        if (inc.id === incidentId) {
          const nowIso = new Date().toISOString();
          return {
            ...inc,
            status: newStatus,
            acknowledged_at: newStatus === "ACKNOWLEDGED" ? nowIso : inc.acknowledged_at,
            resolved_at: newStatus === "RESOLVED" ? nowIso : inc.resolved_at,
            acknowledged_by: newStatus === "ACKNOWLEDGED" ? actor : inc.acknowledged_by,
            resolved_by: newStatus === "RESOLVED" ? actor : inc.resolved_by,
          };
        }
        return inc;
      })
    );

    // 3. Network mutation with rollback on failure
    try {
      const updated = await apiClient.patch<IncidentListItem>(`/incidents/${incidentId}/status`, {
        status: newStatus,
        actor,
      });
      // Synchronize with server response
      setIncidents((prev) => prev.map((inc) => (inc.id === incidentId ? updated : inc)));
      return true;
    } catch (err: unknown) {
      // Revert state on network error
      setIncidents(previousSnapshot);
      const message = err instanceof ApiError ? err.message : "Failed to update incident status";
      setError(`Rollback applied: ${message}`);
      return false;
    }
  };

  return {
    incidents,
    isLoading,
    error,
    refetch: () => fetchIncidents(),
    updateIncidentStatusOptimistic,
  };
}
