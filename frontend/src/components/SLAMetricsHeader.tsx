import React from "react";
import { SLAMetrics } from "../types/incident";

interface SLAMetricsHeaderProps {
  metrics: SLAMetrics | null;
  isLoading: boolean;
}

export const SLAMetricsHeader: React.FC<SLAMetricsHeaderProps> = ({ metrics, isLoading }) => {
  const formatDuration = (seconds: number) => {
    if (seconds <= 0) return "0s";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  const cards = [
    {
      label: "MTTA (Mean Time to Acknowledge)",
      value: isLoading ? "..." : formatDuration(metrics?.mean_time_to_acknowledge_seconds || 0),
      subtitle: "Target: < 5m",
      highlight: false,
    },
    {
      label: "MTTR (Mean Time to Resolve)",
      value: isLoading ? "..." : formatDuration(metrics?.mean_time_to_resolve_seconds || 0),
      subtitle: "Target: < 30m",
      highlight: false,
    },
    {
      label: "Active Sev-1 Breaches",
      value: isLoading ? "..." : (metrics?.active_sev1_breach_count || 0).toString(),
      subtitle: (metrics?.active_sev1_breach_count || 0) > 0 ? "Immediate attention required" : "Zero breaches",
      highlight: (metrics?.active_sev1_breach_count || 0) > 0,
      danger: (metrics?.active_sev1_breach_count || 0) > 0,
    },
    {
      label: "SLA Compliance Rate",
      value: isLoading ? "..." : `${metrics?.sla_compliance_rate || 100}%`,
      subtitle: `${metrics?.total_active_incidents || 0} active incidents`,
      highlight: true,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {cards.map((card, idx) => (
        <div
          key={idx}
          className={`solid-card p-5 relative overflow-hidden transition-transform duration-150 hover:-translate-y-0.5 ${
            card.danger
              ? "border-red-500/50 bg-red-50/20 dark:bg-red-950/20"
              : card.highlight
              ? "border-brand-500/50"
              : ""
          }`}
        >
          <div className="text-xs font-semibold tracking-wider text-gray-500 dark:text-gray-400 uppercase">
            {card.label}
          </div>
          <div
            className={`text-2xl font-bold mt-2 ${
              card.danger
                ? "text-red-600 dark:text-red-400"
                : card.highlight
                ? "text-brand-600 dark:text-brand-500"
                : "text-gray-900 dark:text-gray-100"
            }`}
          >
            {card.value}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{card.subtitle}</div>
        </div>
      ))}
    </div>
  );
};

