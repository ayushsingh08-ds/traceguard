import React from "react";
import { useSLACountdown } from "../hooks/useSLACountdown";
import { IncidentListItem, IncidentStatus, SeverityLevel } from "../types/incident";

interface IncidentTableProps {
  incidents: IncidentListItem[];
  isLoading: boolean;
  onStatusChange: (id: string, newStatus: IncidentStatus) => void;
  onSelectIncidentForRCA: (incident: IncidentListItem) => void;
  selectedIncidentId?: string;
}

const SLACountdownBadge: React.FC<{ deadlineIso: string; isResolved: boolean }> = ({
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
    <span
      className={`inline-block px-2.5 py-1 text-xs font-mono rounded-md border ${
        badgeStyles[badgeState]
      }`}
    >
      {formattedText}
    </span>
  );
};

export const IncidentTable: React.FC<IncidentTableProps> = ({
  incidents,
  isLoading,
  onStatusChange,
  onSelectIncidentForRCA,
  selectedIncidentId,
}) => {
  const severityBadgeClass = (severity: SeverityLevel) => {
    switch (severity) {
      case "Sev-1":
        return "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800";
      case "Sev-2":
        return "bg-brand-100 text-brand-800 border-brand-200 dark:bg-brand-900/40 dark:text-brand-300 dark:border-brand-800";
      case "Sev-3":
        return "bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700";
    }
  };

  if (isLoading && incidents.length === 0) {
    return (
      <div className="solid-card p-12 text-center text-gray-500 dark:text-gray-400">
        Loading active incidents...
      </div>
    );
  }

  if (incidents.length === 0) {
    return (
      <div className="solid-card p-12 text-center text-gray-500 dark:text-gray-400">
        No active incidents matching the selected criteria.
      </div>
    );
  }

  return (
    <div className="solid-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-gray-200 dark:border-darkborder bg-gray-50/70 dark:bg-darkcard text-xs font-semibold uppercase tracking-wider text-gray-600 dark:text-gray-400">
              <th className="py-3.5 px-4">Severity</th>
              <th className="py-3.5 px-4">Incident & Service</th>
              <th className="py-3.5 px-4">Status</th>
              <th className="py-3.5 px-4">SLA Countdown</th>
              <th className="py-3.5 px-4">Volume</th>
              <th className="py-3.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-darkborder text-sm">
            {incidents.map((incident) => {
              const isSelected = incident.id === selectedIncidentId;
              const isResolved = incident.status === "RESOLVED";

              return (
                <tr
                  key={incident.id}
                  className={`transition-colors hover:bg-orange-50/30 dark:hover:bg-brand-950/20 ${
                    isSelected ? "bg-orange-50/60 dark:bg-brand-950/30" : ""
                  }`}
                >
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span
                      className={`inline-block px-2.5 py-0.5 text-xs font-semibold rounded-md border ${severityBadgeClass(
                        incident.severity
                      )}`}
                    >
                      {incident.severity}
                    </span>
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="font-semibold text-gray-900 dark:text-gray-100">
                      {incident.title}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5">
                      {incident.service} &middot; {incident.environment}
                    </div>
                  </td>
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span
                      className={`inline-block px-2 py-0.5 text-xs rounded font-medium ${
                        incident.status === "TRIGGERED"
                          ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400"
                          : incident.status === "ACKNOWLEDGED"
                          ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                          : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                      }`}
                    >
                      {incident.status}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <SLACountdownBadge
                      deadlineIso={incident.sla_deadline_at}
                      isResolved={isResolved}
                    />
                  </td>
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span className="inline-block px-2 py-0.5 text-xs font-mono font-medium rounded-md bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                      x{incident.occurrence_count}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-right whitespace-nowrap space-x-2">
                    {incident.status === "TRIGGERED" && (
                      <button
                        onClick={() => onStatusChange(incident.id, "ACKNOWLEDGED")}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 dark:bg-darkcard dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800 transition-colors shadow-sm"
                      >
                        Acknowledge
                      </button>
                    )}
                    {incident.status !== "RESOLVED" && (
                      <button
                        onClick={() => onStatusChange(incident.id, "RESOLVED")}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700 transition-colors shadow-sm"
                      >
                        Resolve
                      </button>
                    )}
                    <button
                      onClick={() => onSelectIncidentForRCA(incident)}
                      className="px-2.5 py-1 text-xs font-medium rounded-md bg-brand-500 text-white hover:bg-brand-600 transition-colors shadow-sm"
                    >
                      Diagnose RCA
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
