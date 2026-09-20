export type AgentProposal = {
  id: string;
  summary?: string;
  diff?: string;
  artifactKind?: string;
  artifactId?: string;
  marketScope?: string;
};

export type AgentResult = {
  reply?: string;
  notice?: string;
  mode?: string;
  engine?: string;
  adapter?: string;
  proposal?: AgentProposal | null;
};

export type AgentJob = {
  id: string;
  kind?: string;
  label?: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress?: number;
  message?: string;
  error?: string;
  createdAt?: string;
  updatedAt?: string;
  finishedAt?: string;
  result?: AgentResult & {
    date?: string;
    artifactId?: string;
    reportId?: string;
    artifactType?: string;
    title?: string;
  };
  generationMode?: string;
  adapter?: string;
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  notice?: string;
  pending?: boolean;
  attachments?: string[];
  proposal?: AgentProposal | null;
  proposalStatus?: string;
  runState?: "pending" | "done" | "error" | "still-running";
  runTitle?: string;
  runMeta?: string;
  // 폴링이 시간 안에 끝나지 않았을 때만 남는다. 사용자가 같은 작업을 다시 확인할 수 있게 한다.
  jobId?: string;
  createdAt?: string;
  /** 안내 문구는 대화 기록이 아니다. 저장·이관에서 제외한다. */
  variant?: "welcome";
};

export type Attachment = {
  name: string;
  size: number;
  content: string;
  /** base64 image bytes; the server writes them to a scratch file for the CLI to open. */
  imageData?: string;
};

export type AgentModelChoice = {
  value: string;
  label: string;
};

export type AgentAdapterSettings = {
  id: string;
  label?: string;
  model?: string;
  modelChoices?: AgentModelChoice[];
  // 노력 단계는 CLI마다, 같은 CLI 안에서도 모델마다 실제로 받는 값·이름이 다르다
  // (Codex는 low를 "Light"로 부르고 ultra까지, Claude는 "Low"로 부르고 대개 max까지).
  // 서버(features/llm_settings/reasoning.py)가 계산한 값을 그대로 쓴다 — 화면에서
  // 다시 매핑을 지어내면 실제로 그 CLI가 안 받는 값을 보낼 수 있다.
  reasoningChoices?: AgentModelChoice[];
  reasoningByModel?: Record<string, AgentModelChoice[]>;
  bridgeSupported?: boolean;
  supportsWebSearch?: boolean;
};

export type AgentSettings = {
  provider?: string;
  selectedAdapter?: string;
  adapters?: AgentAdapterSettings[];
  message?: string;
};

export type RecentReport = {
  title?: string;
  type?: string;
  date?: string;
  view?: string;
  marketScope?: string;
  scope?: string;
};

export type DashboardPayload = {
  briefings?: RecentReport[];
};

export type InvestmentReviewPayload = {
  recentReports?: RecentReport[];
};

export type ConsultationSearchMeta = {
  requestedPolicy: string;
  toolEnabled: boolean;
  toolUsed: string;
  sourceRefs: { url: string; tier: string; label: string }[];
};

export type ConsultationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  status?: string;
  engine?: string;
  // Agent Dock Stage D/E: absent on most existing messages (only present when
  // the turn actually resolved a search policy other than "off").
  search?: ConsultationSearchMeta;
};

export type ConsultationSession = {
  id: string;
  title: string;
  scope: { kind: string; id?: string; marketScope?: string; tickers?: string[]; intent?: "challenge"; revision?: number };
  status: "active" | "archived";
  revision: number;
  messages?: ConsultationMessage[];
  messageCount?: number;
  continuationOf?: string;
  continuedBy?: string;
  updatedAt?: string;
  layer: "hypothesis";
  sourceLayer: "user_consultation";
  reuseAsEvidence: false;
};

