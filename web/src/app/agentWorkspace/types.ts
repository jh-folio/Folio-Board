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

export type ConsultationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  status?: string;
  engine?: string;
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

