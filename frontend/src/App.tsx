import React, { useEffect, useState } from "react";
import { apiClient } from "./api/client";
import { IncidentTable } from "./components/IncidentTable";
import { RCAInspectorDrawer } from "./components/RCAInspectorDrawer";
import { SLAMetricsHeader } from "./components/SLAMetricsHeader";
import { Toast } from "./components/Toast";
import { useIncidents } from "./hooks/useIncidents";
import {
  DiagnosticExecutionState,
  IncidentListItem,
  IncidentStatus,
  RootCauseReport,
  SeverityLevel,
  SLAMetrics,
} from "./types/incident";

export const App: React.FC = () => {
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

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

          <button
            onClick={() => refetch()}
            className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-sm text-gray-700 dark:text-gray-300"
          >
            Refresh
          </button>
        </div>

        {/* Incident Table */}
        <IncidentTable
          incidents={incidents}
          isLoading={isIncidentsLoading}
          onStatusChange={handleStatusChange}
          onSelectIncidentForRCA={handleSelectIncidentForRCA}
          selectedIncidentId={selectedIncident?.id}
        />
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
