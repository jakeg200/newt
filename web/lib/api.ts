export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Role = "mentor" | "manager" | "admin";

export interface DevUser {
  id: string;
  name: string;
  role: Role;
  email: string;
  org: string;
  synthetic: boolean;
}

export interface SourceDoc {
  id: string;
  filename: string;
  doc_index: number;
  mime: string;
  size_bytes: number;
  passages: number;
  uploaded_at: string;
}

export interface UploadResult {
  filename: string;
  id?: string;
  doc_index?: number;
  passages?: number;
  duplicate?: boolean;
  error?: string;
}

export interface Passage {
  label: string;
  document: string;
  document_id: string | null;
  page: number | null;
  text: string;
}

export interface Question {
  key: string;
  question: string;
  group: string;
  label: string;
  answer: string;
  answered_at: string | null;
}

interface Cited {
  id: string;
  sources: string[];
}

export interface Procedure extends Cited { title: string; steps: string[] }
export interface DecisionRule extends Cited { text: string; applies_to: string }
export interface Escalation extends Cited { text: string }
export interface GlossaryEntry extends Cited { term: string; definition: string }
export interface AccessScope extends Cited { system: string; access: "none" | "read" | "draft" | "write"; reason: string }
export interface EscalationContact extends Cited { contact: string; when: string }

export interface HandbookContent {
  purpose: { text: string; sources: string[] };
  procedures: Procedure[];
  decision_rules: DecisionRule[];
  always_escalate: Escalation[];
  glossary: GlossaryEntry[];
  access_scopes: AccessScope[];
  escalation_contacts: EscalationContact[];
  open_questions: string[];
}

export type SectionKey = Exclude<keyof HandbookContent, "purpose" | "open_questions">;

export interface Issue {
  section: string;
  id: string;
  problem: string;
}

export interface Handbook {
  id: string;
  team: string;
  version: number;
  status: "draft" | "approved" | "superseded";
  content: HandbookContent;
  meta: {
    provider?: string;
    model?: string;
    cost_usd?: number;
    duration_s?: number;
    input_tokens?: number;
    output_tokens?: number;
    issues?: Issue[];
    revised_from?: number;
  };
  created_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface TaskTypeInfo {
  id: string;
  name: string;
  team: string;
  status: string;
  inputs: string[];
  decision: string[];
  intern_name: string;
}

export type Provider = "email_upload" | "gmail" | "csv" | "rest";

export interface RunStats {
  items_received: number;
  cases_created: number;
  duplicate_items: number;
  actions_received: number;
  duplicate_actions: number;
  actions_matched: number;
  actions_unmatched: number;
  actions_without_decision: number;
  earlier_actions_matched: number;
  match_rate: number | null;
  errors: string[];
  error_count: number;
  redactions: Record<string, number>;
  [method: `matched_${string}`]: number;
}

export interface CaptureRun {
  id: string;
  connection_id: string;
  started_at: string;
  finished_at: string | null;
  stats: RunStats;
}

export interface ConnectionInfo {
  id: string;
  name: string;
  provider: Provider;
  task_type_id: string;
  status: "pending" | "active" | "paused";
  filter: { label?: string };
  mentor_addresses: string[];
  body_input: string | null;
  created_at: string;
  cases: number;
  decided: number;
  last_run: { id: string; started_at: string; stats: RunStats } | null;
  push_token?: string;
  push_url?: string;
}

export interface NewConnection {
  name: string;
  provider: Provider;
  task_type_id: string;
  mentor_addresses?: string[];
  body_input?: string;
  label?: string;
  columns?: Record<string, unknown>;
  consent?: boolean;
}

export interface Unmatched {
  id: string;
  acted_at: string;
  reason: string;
  summary: { kind: string; subject: string; refs: string[] };
}

export interface CaseSummary {
  id: string;
  connection_id: string;
  source_ref: string;
  received_at: string;
  status: "open" | "decided";
  is_backtest: boolean;
  subject: string;
  decision: string | null;
  match_method: string | null;
  action_count: number;
}

export interface CaseDetail extends CaseSummary {
  snapshot: {
    subject: string;
    from: string | null;
    inputs: Record<string, string>;
    attachments: string[];
    history: { at: string; from: string | null; text: string }[];
  };
  actions: {
    id: string;
    type: string;
    acted_at: string;
    match_method: string | null;
    payload: {
      decision: string | null;
      fields?: Record<string, unknown>;
      text_outputs?: Record<string, string>;
      note?: string;
      subject?: string;
      recipients?: string[];
    };
  }[];
}

export interface AgentInfo {
  id: string;
  kind: "built_in" | "external";
  name: string;
  endpoint: string | null;
  model: string;
  version: string;
  created_at: string;
  runs_with: { kind: string; model: string; samples: number; effort?: string; billed_here: boolean };
  signing_secret?: string;
}

export interface Estimate {
  cases_available: number;
  cases: number;
  model: string;
  samples: number;
  billed_here: boolean;
  est_cost_usd: number;
  est_minutes: number | null;
  calls?: number;
}

export interface BacktestStats {
  cases: number;
  predicted: number;
  handed_back: number;
  agreement: number;
  agreement_rate: number | null;
  decision_accuracy: number | null;
  confusion: Record<string, Record<string, number>>;
  decisions: string[];
  fields: Record<string, { cases: number; accuracy: number }>;
  confidence_buckets: { from: number; to: number; cases: number; agreement: number | null }[];
  errors: Record<string, number>;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number;
  duration_s: number;
  no_handbook: boolean;
  text_outputs_pending: number;
}

export interface BacktestRun {
  id: string;
  task_type_id: string;
  agent_id: string;
  agent_name: string | null;
  status: "queued" | "running" | "done" | "failed";
  params: { limit: number; samples: number };
  model: string;
  agent_version: string;
  handbook_version: number | null;
  progress: { done?: number; total?: number };
  stats: BacktestStats | Record<string, never>;
  cost_usd: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface BacktestCase {
  case_id: string;
  received_at: string;
  subject: string;
  mentor: { decision: string | null; fields: Record<string, unknown>; text_outputs: Record<string, string> };
  agent: { decision?: string; rationale?: string; fields?: Record<string, unknown>; text_outputs?: Record<string, string> } | null;
  confidence: number | null;
  error: string | null;
  agreement: boolean | null;
  field_scores: Record<string, { mentor: unknown; agent: unknown; match: boolean; critical: boolean }>;
}

export type Attribution = "intern_wrong" | "both_fine" | "mentor_changed" | "couldnt_know";

export interface TextJudgement {
  status?: "pending" | "judged" | "skipped";
  judge?: string;
  acceptable?: boolean;
  outputs?: Record<string, { verdict: string; reasons: string[] }>;
  reason?: string;
}

export interface TeachingCard {
  prediction_id: string;
  kind: "disagreement" | "unsure" | "spot_check";
  case: { id: string; received_at: string; subject: string; from: string | null; inputs: Record<string, string> };
  mentor: { decision: string | null; fields: Record<string, unknown>; text_outputs: Record<string, string>; note?: string | null };
  agent: { decision?: string; fields?: Record<string, unknown>; text_outputs?: Record<string, string>; rationale?: string; missing_info?: string[] };
  confidence: number | null;
  comparison: {
    decision_match: boolean;
    field_scores: Record<string, { mentor: unknown; agent: unknown; match: boolean; critical: boolean }>;
    text_judgement: TextJudgement;
  };
}

export interface TeachingQueue {
  run_id: string | null;
  total: number;
  by_kind: Record<string, number>;
  cards: TeachingCard[];
}

export interface TeachingSummary {
  run_id: string | null;
  predicted: number;
  agreement: number | null;
  excluded?: number;
  lessons: number;
  by_attribution: Record<string, number>;
  queue: number;
  judge: { compared: number; agree: number; rate: number | null; judge?: string | null; trusted: boolean; trust_bar: { rate: number; min_lessons: number } };
  rules: { proposed: number; active: number; retired: number };
  latest_repredict: { id: string; status: string; reason: string; changed: number | null; compared: number | null; created_at: string } | null;
}

export interface LessonResult {
  lesson_id: string;
  effect: string;
  remaining: number;
  reply_ok: boolean | null;
  repredict_run_id: string | null;
  elapsed_ms: number;
}

export interface RuleInfo {
  id: string;
  text: string;
  decision: string | null;
  source: "inferred" | "mentor";
  status: "proposed" | "active" | "retired";
  version: number;
  examples: number;
  stats: { support?: number; matches?: number; precision?: number; method?: string };
  evidence_until: string | null;
  created_at: string;
  updated_at: string;
  repredict_run_id?: string | null;
}

export interface RuleExample {
  case_id: string;
  received_at: string;
  subject: string;
  inputs: Record<string, string>;
  decision: string | null;
}

export interface RepredictRun {
  id: string;
  status: BacktestRun["status"];
  error: string | null;
  params: { reason?: string; case_ids?: string[] };
  stats: { changed?: number; compared_with_previous?: number; changes?: { case_id: string; subject: string; before: string | null; after: string | null }[] };
}

export type Stage = "shadow" | "supervised" | "autonomous" | "demoted";

export interface Check {
  name: "bound" | "cases" | "live" | "coverage";
  ok: boolean;
  detail: string;
}

export interface EvalExample {
  case_id: string;
  subject: string;
  agent: string;
  mentor: string | null;
  confidence: number;
  live: boolean;
}

export interface Evaluation {
  task_type_id: string;
  status: Stage;
  alpha: number;
  min_cases: number;
  cases: number;
  live_cases: number;
  backtest_cases: number;
  agreement_rate: number | null;
  tau: number | null;
  n_above: number;
  errors_above: number;
  live_above: number;
  ucb: number;
  coverage: number;
  hand_back_rate: number | null;
  cases_needed: number;
  more_clean_cases_needed: number;
  checks: Check[];
  eligible: boolean;
  agreements?: EvalExample[];
  disagreements?: EvalExample[];
  hand_backs?: EvalExample[];
  criteria: Record<string, string[]>;
}

export interface BoardRow {
  id: string;
  name: string;
  status: Stage;
  tau: number | null;
  evaluation: Pick<Evaluation, "cases" | "live_cases" | "agreement_rate" | "tau" | "n_above" | "errors_above" | "ucb" | "alpha" |
    "coverage" | "min_cases" | "cases_needed" | "more_clean_cases_needed" | "live_above" | "eligible" | "checks">;
  supervised_cases: number;
  supervised_needed: number;
  untouched: { cases: number; untouched: number; rate: number | null };
  audits: { passed: number; failed: number; pending: number };
  last_drift: { checked_at: string; drifted: boolean } | null;
  graduated_at: string | null;
}

export interface TrackRecord {
  task_type: { name: string; definition: string; decisions: string[]; alpha: number };
  status: Stage;
  mentor: string | null;
  team: string;
  cases: { backtest: number | null; live: number | null };
  agreement_rate: number | null;
  error_upper_bound_95: number | null;
  tau: number | null;
  coverage: number | null;
  hand_back_rate: number | null;
  audits: { passed: number; total: number };
  last_drift_check: { date: string; drifted: boolean } | null;
  versions: { agent: string; model: string; agent_version: string; handbook: number | null; rules: number; config_hash: string };
  signoffs: Record<string, { name: string | null; date: string | null }>;
  history: { date: string | null; from: string; to: string; by: string | null; note: string | null }[];
}

export interface DraftCard {
  prediction_id: string;
  case: { id: string; received_at: string; subject: string; from: string | null; inputs: Record<string, string> };
  agent: { decision: string; fields: Record<string, unknown>; text_outputs: Record<string, string>; rationale?: string };
  confidence: number | null;
  actions: { id: string; action: string; payload: Record<string, unknown>; status: string; policy: { ok: boolean; reasons: string[] } }[];
}

export interface HandbackCard {
  prediction_id: string;
  case: { id: string; received_at: string; subject: string; inputs: Record<string, string> };
  reasons: string[];
  agent_decision: string | null;
  confidence: number | null;
}

export interface AuditCard {
  audit_id: string;
  case: { id: string; received_at: string; subject: string; from: string | null; inputs: Record<string, string> };
}

export interface Digest {
  status: Stage;
  cases_handled: number;
  actions_executed: number;
  actions_blocked: number;
  handbacks: number | null;
  audits_pending: number;
  recent?: { case_id: string; subject: string; action: string; status: string; payload: Record<string, unknown>; reasons: string[]; at: string }[];
}

export interface ManagerSettings {
  currency: string;
  usd_rate: number;
  hourly_cost: number | null;
  minutes_per_case: number | null;
  intern_name: string;
}

export interface ManagerTeam {
  team: string;
  handbook: { version: number; approved_at: string } | null;
  stages: Record<Stage, number>;
  task_types: {
    id: string;
    name: string;
    status: Stage;
    handled: { autonomous: number; supervised: number; total: number };
    coverage: number;
    error_upper_bound: number;
    alpha: number;
    hand_back_rate: number | null;
    audits: { passed: number; failed: number; pending: number };
    time_to_decision_minutes: number | null;
  }[];
  cases_handled: number;
  hours_returned: number | null;
  value_of_hours: number | null;
  running_cost: number;
  running_cost_usd: { live: number; evaluation: number };
  net: number | null;
  settings: ManagerSettings;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let currentUserId: string | null = null;
let accessToken: string | null = null;

/** Development: act as a seeded user. */
export function setApiUser(id: string | null) {
  currentUserId = id;
}

/** Production: the Supabase session's access token. */
export function setApiToken(token: string | null) {
  accessToken = token;
}

function authHeaders(headers: Headers) {
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  else if (currentUserId) headers.set("X-Dev-User", currentUserId);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  authHeaders(headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const q = (team: string) => `team=${encodeURIComponent(team)}`;

export const api = {
  devUsers: () => request<DevUser[]>("/dev/users"),
  me: () => request<{ id: string; name: string; role: Role; email: string; org: string; synthetic: boolean }>("/me"),
  teams: () => request<string[]>("/orientation/teams"),
  sources: (team: string) => request<SourceDoc[]>(`/orientation/sources?${q(team)}`),
  upload: (team: string, files: File[]) => {
    const form = new FormData();
    form.set("team", team);
    files.forEach((f) => form.append("files", f));
    return request<UploadResult[]>("/orientation/sources", { method: "POST", body: form });
  },
  deleteSource: (id: string) => request<void>(`/orientation/sources/${id}`, { method: "DELETE" }),
  passages: (team: string) => request<Passage[]>(`/orientation/passages?${q(team)}`),
  questionnaire: (team: string) => request<Question[]>(`/orientation/questionnaire?${q(team)}`),
  saveAnswers: (team: string, answers: Record<string, string>) =>
    request<{ saved: number }>(`/orientation/questionnaire?${q(team)}`, { method: "PUT", body: JSON.stringify({ answers }) }),
  handbooks: (team: string) => request<Handbook[]>(`/orientation/handbook?${q(team)}`),
  draft: (team: string) => request<Handbook>("/orientation/handbook/draft", { method: "POST", body: JSON.stringify({ team }) }),
  updateHandbook: (id: string, content: HandbookContent) =>
    request<Handbook>(`/orientation/handbook/${id}`, { method: "PATCH", body: JSON.stringify({ content }) }),
  approve: (id: string) => request<Handbook>(`/orientation/handbook/${id}/approve`, { method: "POST" }),
  revise: (id: string) => request<Handbook>(`/orientation/handbook/${id}/revise`, { method: "POST" }),

  taskTypes: () => request<TaskTypeInfo[]>("/task-types"),
  connections: (taskTypeId: string) => request<ConnectionInfo[]>(`/connections?task_type_id=${taskTypeId}`),
  createConnection: (body: NewConnection) => request<ConnectionInfo>("/connections", { method: "POST", body: JSON.stringify(body) }),
  updateConnection: (id: string, body: { name?: string; status?: "active" | "paused" }) =>
    request<ConnectionInfo>(`/connections/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteConnection: (id: string) => request<void>(`/connections/${id}`, { method: "DELETE" }),
  importFiles: (id: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<CaptureRun>(`/connections/${id}/import`, { method: "POST", body: form });
  },
  sync: (id: string) => request<CaptureRun>(`/connections/${id}/sync`, { method: "POST" }),
  oauthStart: (id: string) => request<{ url: string }>(`/connections/${id}/oauth/start`),
  unmatched: (id: string) => request<Unmatched[]>(`/connections/${id}/unmatched`),
  cases: (taskTypeId: string, offset = 0, limit = 50) =>
    request<{ total: number; items: CaseSummary[] }>(`/cases?task_type_id=${taskTypeId}&limit=${limit}&offset=${offset}`),
  caseDetail: (id: string) => request<CaseDetail>(`/cases/${id}`),

  agents: () => request<AgentInfo[]>("/agents"),
  createAgent: (body: { name: string; endpoint: string; version: string; model?: string }) =>
    request<AgentInfo>("/agents", { method: "POST", body: JSON.stringify(body) }),
  estimate: (taskTypeId: string, agentId: string | null, limit: number) =>
    request<Estimate>(`/backtests/estimate?task_type_id=${taskTypeId}&limit=${limit}${agentId ? `&agent_id=${agentId}` : ""}`),
  startBacktest: (body: { task_type_id: string; agent_id?: string | null; limit: number }) =>
    request<BacktestRun>("/backtests", { method: "POST", body: JSON.stringify(body) }),
  backtests: (taskTypeId: string) => request<BacktestRun[]>(`/backtests?task_type_id=${taskTypeId}`),
  backtestCases: (id: string, only: "disagreements" | "handed_back" | "all") =>
    request<{ items: BacktestCase[] }>(`/backtests/${id}/cases?only=${only}&limit=100`),
  run: (id: string) => request<RepredictRun>(`/backtests/${id}`),

  teachingQueue: (taskTypeId: string, limit = 10) => request<TeachingQueue>(`/teaching/queue?task_type_id=${taskTypeId}&limit=${limit}`),
  teachingSummary: (taskTypeId: string) => request<TeachingSummary>(`/teaching/summary?task_type_id=${taskTypeId}`),
  lesson: (body: { prediction_id: string; attribution: Attribution; note?: string; reply_ok?: boolean | null; rule_text?: string }) =>
    request<LessonResult>("/lessons", { method: "POST", body: JSON.stringify(body) }),
  rules: (taskTypeId: string) => request<RuleInfo[]>(`/rules?task_type_id=${taskTypeId}`),
  inferRules: (taskTypeId: string) => request<RuleInfo[]>("/rules/infer", { method: "POST", body: JSON.stringify({ task_type_id: taskTypeId }) }),
  createRule: (taskTypeId: string, text: string) =>
    request<RuleInfo>("/rules", { method: "POST", body: JSON.stringify({ task_type_id: taskTypeId, text }) }),
  updateRule: (id: string, body: { text?: string; status?: RuleInfo["status"] }) =>
    request<RuleInfo>(`/rules/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  ruleExamples: (id: string) => request<RuleExample[]>(`/rules/${id}/examples`),

  board: () => request<BoardRow[]>("/board"),
  evaluation: (taskTypeId: string) => request<Evaluation>(`/task-types/${taskTypeId}/evaluation`),
  graduate: (taskTypeId: string, to: "supervised" | "autonomous") =>
    request<{ status: Stage; tau: number | null }>(`/task-types/${taskTypeId}/graduate`, { method: "POST", body: JSON.stringify({ to }) }),
  trackRecord: (taskTypeId: string) => request<TrackRecord>(`/task-types/${taskTypeId}/track-record`),
  trackRecordPdf: async (taskTypeId: string) => {
    const headers = new Headers();
    authHeaders(headers);
    const res = await fetch(`${API_URL}/task-types/${taskTypeId}/track-record.pdf`, { headers });
    if (!res.ok) throw new ApiError(res.status, "Couldn't export the PDF");
    return res.blob();
  },
  driftCheck: (taskTypeId: string) =>
    request<{ drifted: boolean; result: Record<string, number>; status: Stage }>(`/task-types/${taskTypeId}/drift-check`, { method: "POST" }),
  swapModel: (agentId: string, model: string, version: string) =>
    request<{ model: string; version: string; reprobation_runs: string[] }>(`/agents/${agentId}/swap`, { method: "POST", body: JSON.stringify({ model, version }) }),
  supervised: (taskTypeId: string) => request<DraftCard[]>(`/supervised?task_type_id=${taskTypeId}`),
  approveDraft: (predictionId: string, edits: { decision?: string; text_outputs?: Record<string, string> } = {}) =>
    request<{ status: string; untouched: boolean }>(`/supervised/${predictionId}/approve`, { method: "POST", body: JSON.stringify(edits) }),
  rejectDraft: (predictionId: string, decision: string, note?: string) =>
    request<{ status: string }>(`/supervised/${predictionId}/reject`, { method: "POST", body: JSON.stringify({ decision, note }) }),
  handbacks: (taskTypeId: string) => request<HandbackCard[]>(`/handbacks?task_type_id=${taskTypeId}`),
  audits: (taskTypeId: string) => request<AuditCard[]>(`/audits?task_type_id=${taskTypeId}`),
  submitAudit: (auditId: string, decision: string) =>
    request<{ result: "pass" | "fail"; agent_decision: string | null; review: { demoted_to?: string } | null }>(`/audits/${auditId}`, {
      method: "POST", body: JSON.stringify({ decision }) }),
  digest: (taskTypeId: string) => request<Digest>(`/autonomy/digest?task_type_id=${taskTypeId}`),

  managerDashboard: () => request<{ period_days: number; teams: ManagerTeam[] }>("/manager/dashboard"),
  managerSettings: (team: string, body: Partial<ManagerSettings>) =>
    request<ManagerSettings>(`/manager/settings/${encodeURIComponent(team)}`, { method: "PATCH", body: JSON.stringify(body) }),

  thread: (taskTypeId: string) => request<{ intern_name: string; messages: ChatMessage[] }>(`/messages?task_type_id=${taskTypeId}`),
  say: (taskTypeId: string, text: string) =>
    request<ChatMessage[]>("/messages", { method: "POST", body: JSON.stringify({ task_type_id: taskTypeId, text }) }),
  replyTo: (messageId: string, action: ReplyAction, value?: string, note?: string) =>
    request<ChatMessage[]>(`/messages/${messageId}/reply`, { method: "POST", body: JSON.stringify({ action, value, note }) }),
  preferences: () => request<ContactPrefs>("/me/preferences"),
  setPreferences: (body: Partial<ContactPrefs>) => request<ContactPrefs>("/me/preferences", { method: "PATCH", body: JSON.stringify(body) }),
};

export type ReplyAction = "decide" | "approve" | "reject" | "lesson" | "answer" | "sign" | "feedback" | "dismiss";

export interface ChatMessage {
  id: string;
  direction: "newt" | "person";
  kind: "standup" | "question" | "delivery" | "handback" | "draft" | "promotion" | "ack" | "chat";
  body: string;
  payload: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any -- shape depends on kind
  status: "open" | "answered" | "done" | "dismissed";
  urgency: "low" | "normal" | "urgent";
  at: string;
  answered_at: string | null;
}

export interface ContactPrefs {
  timezone: string;
  start: string;
  end: string;
  workdays: number[];
  questions_per_day: number;
  urgent_out_of_hours: boolean;
  calls: boolean;
  channel: "app" | "email" | "slack" | "teams";
}
