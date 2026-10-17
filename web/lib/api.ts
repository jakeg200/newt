export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Role = "mentor" | "manager" | "admin";

export interface DevUser {
  id: string;
  name: string;
  role: Role;
  email: string;
  org: string;
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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let currentUserId: string | null = null;

export function setApiUser(id: string | null) {
  currentUserId = id;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (currentUserId) headers.set("X-Dev-User", currentUserId);
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
};
