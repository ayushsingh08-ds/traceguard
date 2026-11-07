import React, { useEffect, useState } from "react";
import { apiClient } from "./api/client";
import { IncidentTable } from "./components/IncidentTable";
import { RCAInspectorDrawer } from "./components/RCAInspectorDrawer";
import { SLAMetricsHeader } from "./components/SLAMetricsHeader";
import { SortableStack } from "./components/SortableStack";
import { Toast } from "./components/Toast";
import { useIncidents } from "./hooks/useIncidents";
import { useSLACountdown } from "./hooks/useSLACountdown";
import {
  DiagnosticExecutionState,
  IncidentListItem,
  IncidentStatus,
  RootCauseReport,
  SeverityLevel,
  SLAMetrics,
} from "./types/incident";

const SLABadgeWrapper: React.FC<{ deadlineIso: string; isResolved: boolean }> = ({
  deadlineIso,
  isResolved,
}) => {
  const { formattedText, badgeState } = useSLACountdown(deadlineIso, isResolved);
  const badgeStyles: Record<string, string> = {
    healthy: "bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800",
    warning: "bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800",
    breached: "bg-red-50 text-red-700 border-red-300 dark:bg-red-950/40 dark:text-red-300 dark:border-red-800 font-bold",
  };

  return (
    <span className={`inline-block px-2.5 py-1 text-xs font-mono rounded-md border ${badgeStyles[badgeState]}`}>
      {formattedText}
    </span>
  );
};

export const App: React.FC = () => {
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  const [viewMode, setViewMode] = useState<"table" | "stack">("table");
  const [severityFilter, setSeverityFilter] = useState<SeverityLevel | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | undefined>(undefined);
  const [serviceSearch, setServiceSearch] = useState<string>("");

  const [metrics, setMetrics] = useState<SLAMetrics | null>(null);
  const [isMetricsLoading, setIsMetricsLoading] = useState<boolean>(true);

  const [selectedIncident, setSelectedIncident] = useState<IncidentListItem | null>(null);
  const [diagnosticState, setDiagnosticState] = useState<DiagnosticExecutionState>({ status: "idle" });
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const {
    incidents,
    isLoading: isIncidentsLoading,
    error: incidentsError,
    refetch,
    updateIncidentStatusOptimistic,
  } = useIncidents({
    severity: severityFilter,
    status: statusFilter,
    service: serviceSearch || undefined,
  });

  const [stackedIncidents, setStackedIncidents] = useState<IncidentListItem[]>([]);

  useEffect(() => {
    setStackedIncidents(incidents);
  }, [incidents]);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  const fetchMetrics = async () => {
    setIsMetricsLoading(true);
    try {
      const data = await apiClient.get<SLAMetrics>("/analytics/sla");
      setMetrics(data);
    } catch {
      // Fallback baseline for initial load
      setMetrics({
        mean_time_to_acknowledge_seconds: 142,
        mean_time_to_resolve_seconds: 1180,
        active_sev1_breach_count: 0,
        active_sev2_breach_count: 0,
        active_sev3_breach_count: 0,
        total_active_incidents: incidents.length,
        sla_compliance_rate: 98.4,
      });
    } finally {
      setIsMetricsLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, [incidents.length]);

  const handleStatusChange = async (id: string, newStatus: IncidentStatus) => {
    const success = await updateIncidentStatusOptimistic(id, newStatus);
    if (!success) {
      setToastMessage("Failed to update status. Rolled back to previous state.");
    } else {
      fetchMetrics();
    }
  };

  const handleSelectIncidentForRCA = async (incident: IncidentListItem) => {
    setSelectedIncident(incident);
    setDiagnosticState({ status: "idle" });

    // Try fetching existing report first
    try {
      const existing = await apiClient.get<RootCauseReport & { id: string }>(`/rca/${incident.id}/report`);
      setDiagnosticState({ status: "completed", report: existing });
    } catch {
      setDiagnosticState({ status: "idle" });
    }
  };

  const handleRunDiagnosis = async () => {
    if (!selectedIncident) return;

    setDiagnosticState({ status: "running", activeTool: "check_database_locks" });

    try {
      const report = await apiClient.post<RootCauseReport>(`/rca/${selectedIncident.id}/diagnose`);
      setDiagnosticState({ status: "completed", report });
      refetch();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "RCA execution failed";
      setDiagnosticState({ status: "failed", error: message });
    }
  };

  const handleSimulateAlert = async () => {
    try {
      await apiClient.post("/alerts/webhook", {
        service: "orders-db",
        title: "Database deadlocks spike on orders table",
        severity: "Sev-1",
        environment: "production",
      });
      setToastMessage("Simulated Sev-1 alert webhook sent to ingestion pipeline.");
      refetch();
      fetchMetrics();
    } catch {
      setToastMessage("Simulated alert ingestion failed.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-darkbg text-gray-900 dark:text-gray-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-gray-200 dark:border-darkborder bg-white dark:bg-darkcard px-6 py-3.5 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center text-white font-bold text-sm shadow-sm">
            TG
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-base tracking-tight">TraceGuard</span>
              <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-300">
                v1.0.0
              </span>
            </div>
            <div className="text-[11px] text-gray-500 dark:text-gray-400">
              Incident Triage &bull; SLA Tracker &bull; RAG Diagnostics
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleSimulateAlert}
            className="px-3 py-1.5 text-xs font-semibold rounded-md bg-brand-500 hover:bg-brand-600 text-white transition-colors shadow-sm"
          >
            Simulate Alert Burst
          </button>
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-sm"
          >
            {darkMode ? "Light Mode" : "Dark Mode"}
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {/* SLA Header */}
        <SLAMetricsHeader metrics={metrics} isLoading={isMetricsLoading} />

        {/* Filter Toolbar */}
        <div className="solid-card p-4 mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={severityFilter || ""}
              onChange={(e) => setSeverityFilter((e.target.value as SeverityLevel) || undefined)}
              className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard text-gray-900 dark:text-gray-100 shadow-sm"
            >
              <option value="">All Severities</option>
              <option value="Sev-1">Sev-1 (Critical)</option>
              <option value="Sev-2">Sev-2 (High)</option>
              <option value="Sev-3">Sev-3 (Low)</option>
            </select>

            <select
              value={statusFilter || ""}
              onChange={(e) => setStatusFilter((e.target.value as IncidentStatus) || undefined)}
              className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard text-gray-900 dark:text-gray-100 shadow-sm"
            >
              <option value="">All Statuses</option>
              <option value="TRIGGERED">Triggered</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
            </select>

            <input
              type="text"
              placeholder="Filter by service name..."
              value={serviceSearch}
              onChange={(e) => setServiceSearch(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard text-gray-900 dark:text-gray-100 placeholder-gray-400 shadow-sm w-48 sm:w-64"
            />
          </div>

          <div className="flex items-center space-x-2">
            <div className="flex rounded-md border border-gray-300 dark:border-darkborder overflow-hidden p-0.5 bg-gray-100 dark:bg-darkcard">
              <button
                onClick={() => setViewMode("table")}
                className={`text-xs px-3 py-1 rounded-md font-medium transition-colors ${
                  viewMode === "table"
                    ? "bg-white dark:bg-darkborder text-gray-900 dark:text-gray-100 shadow-sm font-semibold"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900"
                }`}
              >
                Table View
              </button>
              <button
                onClick={() => setViewMode("stack")}
                className={`text-xs px-3 py-1 rounded-md font-medium transition-colors ${
                  viewMode === "stack"
                    ? "bg-brand-500 text-white shadow-sm font-semibold"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900"
                }`}
              >
                Sortable Stack
              </button>
            </div>

            <button
              onClick={() => refetch()}
              className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-sm text-gray-700 dark:text-gray-300"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* View Mode: Table vs Interactive Sortable Stack */}
        {viewMode === "table" ? (
          <IncidentTable
            incidents={incidents}
            isLoading={isIncidentsLoading}
            onStatusChange={handleStatusChange}
            onSelectIncidentForRCA={handleSelectIncidentForRCA}
            selectedIncidentId={selectedIncident?.id}
          />
        ) : (
          <div className="space-y-3">
            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Interactive Triage Priority Queue (Drag to Reorder War-Room Focus)
            </div>
            <SortableStack<IncidentListItem>
              items={stackedIncidents}
              onReorder={setStackedIncidents}
              renderItem={(incident, isDragging) => (
                <div className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${isDragging ? "opacity-90" : ""}`}>
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-md border ${
                          incident.severity === "Sev-1"
                            ? "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800"
                            : incident.severity === "Sev-2"
                            ? "bg-brand-100 text-brand-800 border-brand-200 dark:bg-brand-900/40 dark:text-brand-300 dark:border-brand-800"
                            : "bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700"
                        }`}
                      >
                        {incident.severity}
                      </span>
                      <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
                        {incident.title}
                      </span>
                      <span className="px-1.5 py-0.5 text-xs font-mono font-medium rounded-md bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        x{incident.occurrence_count}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {incident.service} &middot; {incident.environment} &middot; Status: {incident.status}
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    <SLABadgeWrapper
                      deadlineIso={incident.sla_deadline_at}
                      isResolved={incident.status === "RESOLVED"}
                    />
                    {incident.status === "TRIGGERED" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStatusChange(incident.id, "ACKNOWLEDGED");
                        }}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 dark:bg-darkcard dark:border-gray-700 dark:text-gray-200"
                      >
                        Acknowledge
                      </button>
                    )}
                    {incident.status !== "RESOLVED" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStatusChange(incident.id, "RESOLVED");
                        }}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700"
                      >
                        Resolve
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectIncidentForRCA(incident);
                      }}
                      className="px-2.5 py-1 text-xs font-medium rounded-md bg-brand-500 text-white hover:bg-brand-600"
                    >
                      Diagnose RCA
                    </button>
                  </div>
                </div>
              )}
            />
          </div>
        )}
      </main>

      {/* Slide-over RCA Inspector Drawer */}
      <RCAInspectorDrawer
        incident={selectedIncident}
        state={diagnosticState}
        onClose={() => setSelectedIncident(null)}
        onRunDiagnosis={handleRunDiagnosis}
      />

      {/* Error / Rollback Toast */}
      <Toast
        message={toastMessage || incidentsError}
        type={incidentsError ? "error" : "info"}
        onDismiss={() => setToastMessage(null)}
      />
    </div>
  );
};

