import React, { useState } from "react";
import { DiagnosticExecutionState, IncidentListItem } from "../types/incident";
import { SortableStack } from "./SortableStack";

interface RCAInspectorDrawerProps {
  incident: IncidentListItem | null;
  state: DiagnosticExecutionState;
  onClose: () => void;
  onRunDiagnosis: () => void;
}

interface RemediationStepItem {
  id: string;
  step: string;
}

export const RCAInspectorDrawer: React.FC<RCAInspectorDrawerProps> = ({
  incident,
  state,
  onClose,
  onRunDiagnosis,
}) => {
  const [reorderedSteps, setReorderedSteps] = useState<RemediationStepItem[]>([]);

  // Sync steps when diagnosis completes
  React.useEffect(() => {
    if (state.status === "completed") {
      setReorderedSteps(
        state.report.recommended_runbook_steps.map((step, idx) => ({
          id: `step-${idx}-${step.slice(0, 15)}`,
          step,
        }))
      );
    }
  }, [state]);

  if (!incident) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-white dark:bg-darkcard border-l border-gray-200 dark:border-darkborder shadow-2xl z-50 flex flex-col transition-transform duration-200">
      {/* Header */}
      <div className="p-5 border-b border-gray-200 dark:border-darkborder flex items-center justify-between bg-gray-50/50 dark:bg-darkcard">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-500">
            AI Diagnostic Engine
          </div>
          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 truncate mt-0.5">
            {incident.title}
          </h2>
          <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
            {incident.service} &middot; {incident.severity} &middot; x{incident.occurrence_count} occurrences
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Close drawer"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {state.status === "idle" && (
          <div className="solid-card p-8 text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-full bg-brand-50 dark:bg-brand-950/40 border border-brand-200 dark:border-brand-800 flex items-center justify-center text-brand-600 dark:text-brand-400 font-bold">
              AI
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Ready to Diagnose</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-xs mx-auto">
                TraceGuard will search semantic runbooks via pgvector and invoke deterministic diagnostic tools to isolate root cause.
              </p>
            </div>
            <button
              onClick={onRunDiagnosis}
              className="px-4 py-2 text-sm font-medium rounded-md bg-brand-500 text-white hover:bg-brand-600 transition-colors shadow-sm"
            >
              Run Diagnostic Agent
            </button>
          </div>
        )}

        {state.status === "running" && (
          <div className="solid-card p-8 text-center space-y-4">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-brand-500 border-t-transparent"></div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Analyzing System Telemetry</h3>
              <p className="text-xs text-brand-600 dark:text-brand-400 font-mono mt-1">
                Executing: {state.activeTool}...
              </p>
            </div>
          </div>
        )}

        {state.status === "failed" && (
          <div className="solid-card p-6 border-red-500/40 bg-red-50/20 dark:bg-red-950/20 space-y-3">
            <div className="text-sm font-semibold text-red-600 dark:text-red-400">Diagnostic Pipeline Failed</div>
            <p className="text-xs text-gray-600 dark:text-gray-300 font-mono">{state.error}</p>
            <button
              onClick={onRunDiagnosis}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-white border border-gray-300 dark:bg-darkcard dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50"
            >
              Retry Analysis
            </button>
          </div>
        )}

        {state.status === "completed" && (
          <>
            {/* Hypothesis Card */}
            <div className="solid-card p-5 border-brand-500/40 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">
                  Root Cause Hypothesis
                </span>
                <span className="px-2 py-0.5 text-xs font-mono font-bold rounded bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-300">
                  {Math.round(state.report.confidence_score * 100)}% Confidence
                </span>
              </div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 leading-relaxed">
                {state.report.hypothesis}
              </p>
              <div className="text-xs text-gray-400 dark:text-gray-500 font-mono pt-1 border-t border-gray-100 dark:border-darkborder flex justify-between">
                <span>Model: {state.report.model_name}</span>
                <span>Latency: {state.report.execution_time_ms}ms</span>
              </div>
            </div>

            {/* Supporting Evidence */}
            <div className="solid-card p-5 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Supporting Evidence
              </div>
              <ul className="space-y-2">
                {state.report.supporting_evidence.map((item, idx) => (
                  <li key={idx} className="text-xs text-gray-700 dark:text-gray-300 flex items-start space-x-2">
                    <span className="text-brand-500 font-bold mt-0.5">&bull;</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Recommended Runbook Actions with Interactive Sortable Stack */}
            <div className="solid-card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Interactive Remediation Checklist (Drag to Prioritize)
                </div>
                <span className="text-[11px] font-mono text-gray-400 dark:text-gray-500">
                  {reorderedSteps.length} steps
                </span>
              </div>
              <SortableStack<RemediationStepItem>
                items={reorderedSteps}
                onReorder={setReorderedSteps}
                renderItem={(item, isDragging) => (
                  <div className="text-xs text-gray-800 dark:text-gray-200 flex items-start space-x-2">
                    <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                      {reorderedSteps.findIndex((s) => s.id === item.id) + 1}.
                    </span>
                    <span className={isDragging ? "font-medium text-brand-600 dark:text-brand-400" : ""}>
                      {item.step}
                    </span>
                  </div>
                )}
              />
            </div>

            {/* Executed Tools Telemetry */}
            <div className="solid-card p-5 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Executed Diagnostic Tools ({state.report.tools_executed.length})
              </div>
              <div className="space-y-2">
                {state.report.tools_executed.map((tool, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-gray-50 dark:bg-darkborder/40 rounded-md border border-gray-200 dark:border-darkborder text-xs"
                  >
                    <div className="flex justify-between font-mono font-semibold text-gray-900 dark:text-gray-100">
                      <span>{tool.tool_name}()</span>
                      <span className="text-gray-400">{tool.execution_time_ms}ms</span>
                    </div>
                    <pre className="mt-2 p-2 bg-white dark:bg-darkcard rounded border border-gray-100 dark:border-darkborder overflow-x-auto text-[11px] font-mono text-gray-700 dark:text-gray-300">
                      {JSON.stringify(tool.result, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>

            {/* pgvector Runbook Citations */}
            {state.report.retrieved_chunks.length > 0 && (
              <div className="solid-card p-5 space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Retrieved pgvector Runbook Citations
                </div>
                <div className="space-y-2">
                  {state.report.retrieved_chunks.map((chunk, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-gray-50 dark:bg-darkborder/40 rounded-md border border-gray-200 dark:border-darkborder text-xs flex justify-between items-center"
                    >
                      <div>
                        <div className="font-semibold text-gray-900 dark:text-gray-100">{chunk.title}</div>
                        <div className="text-gray-500 dark:text-gray-400 font-mono text-[11px]">
                          ID: {chunk.runbook_id} (chunk #{chunk.chunk_index})
                        </div>
                      </div>
                      <span className="px-2 py-0.5 text-xs font-mono font-medium rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                        {Math.round(chunk.similarity_score * 100)}% match
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

