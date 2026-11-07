export type SeverityLevel = "Sev-1" | "Sev-2" | "Sev-3";

export type IncidentStatus = "TRIGGERED" | "ACKNOWLEDGED" | "RESOLVED";

export interface ToolExecutionRecord {
  tool_name: string;
  parameters: Record<string, unknown>;
  result: Record<string, unknown>;
  execution_time_ms: number;
}

export interface RunbookCitation {
  runbook_id: string;
  chunk_index: number;
  title: string;
  similarity_score: number;
}

export interface RootCauseReport {
  hypothesis: string;
  supporting_evidence: string[];
  confidence_score: number;
  recommended_runbook_steps: string[];
  tools_executed: ToolExecutionRecord[];
  retrieved_chunks: RunbookCitation[];
  model_name: string;
  tokens_used: number;
  execution_time_ms: number;
}

export interface IncidentListItem {
  id: string;
  fingerprint: string;
  title: string;
  service: string;
  environment: string;
  severity: SeverityLevel;
  status: IncidentStatus;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  sla_deadline_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  acknowledged_by?: string | null;
  resolved_by?: string | null;
}

export interface IncidentAuditLog {
  id: string;
  incident_id: string;
  action: string;
  actor: string;
  previous_status?: string | null;
  new_status?: string | null;
  note?: string | null;
  created_at: string;
}

export interface IncidentDetail extends IncidentListItem {
  raw_payload: Record<string, unknown>;
  audit_logs: IncidentAuditLog[];
  rca_reports: (RootCauseReport & { id: string; incident_id: string; created_at: string })[];
}

export interface SLAMetrics {
  mean_time_to_acknowledge_seconds: number;
  mean_time_to_resolve_seconds: number;
  active_sev1_breach_count: number;
  active_sev2_breach_count: number;
  active_sev3_breach_count: number;
  total_active_incidents: number;
  sla_compliance_rate: number;
}

// Discriminated union enforces impossible state prevention at compile time.
// The UI can never render an RCA report while 'status' is 'running'.
export type DiagnosticExecutionState =
  | { status: "idle" }
  | { status: "running"; activeTool: string }
  | { status: "completed"; report: RootCauseReport }
  | { status: "failed"; error: string };

export type SLABadgeState = "healthy" | "warning" | "breached";
