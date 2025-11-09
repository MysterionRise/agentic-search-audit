/**
 * Core type definitions for the search audit system
 */

export type Query = {
  id: string;
  text: string;
  lang?: string;
  origin: "predefined" | "generated";
};

export type ResultItem = {
  rank: number;
  title?: string;
  url?: string;
  snippet?: string;
  price?: string;
  image?: string;
  attributes?: Record<string, string>;
};

export type PageArtifacts = {
  url: string;
  finalUrl: string;
  htmlPath: string;
  screenshotPath: string;
  ts: string;
};

export type JudgeScore = {
  overall: number; // 0..5
  relevance: number;
  diversity: number;
  resultQuality: number;
  navigability: number;
  rationale: string;
  issues: string[];
  improvements: string[];
  evidence: Array<{ rank: number; why: string }>;
  schemaVersion: string;
};

export type AuditRecord = {
  site: string;
  query: Query;
  items: ResultItem[];
  page: PageArtifacts;
  judge: JudgeScore;
};

/**
 * Configuration types
 */

export type SearchConfig = {
  inputSelectors: string[];
  submitStrategy: "enter" | "clickSelector";
  submitSelector?: string;
};

export type ResultsConfig = {
  itemSelectors: string[];
  titleSelectors: string[];
  urlAttr: string;
  snippetSelectors: string[];
};

export type ModalsConfig = {
  closeTextMatches: string[];
  maxAutoClicks: number;
};

export type SiteConfig = {
  url: string;
  locale: string;
  search: SearchConfig;
  results: ResultsConfig;
  modals: ModalsConfig;
};

export type RunConfig = {
  topK: number;
  viewport: { width: number; height: number };
  waitFor: { networkIdleMs: number; postSubmitMs: number };
  headless: boolean;
  throttleRPS: number;
  seed: number;
};

export type LLMConfig = {
  provider: "openai" | "anthropic" | "openrouter";
  model: string;
  maxTokens: number;
  temperature: number;
  systemPrompt: string;
};

export type ReportConfig = {
  format: ("md" | "html")[];
  outDir: string;
};

export type AuditConfig = {
  site: SiteConfig;
  run: RunConfig;
  llm: LLMConfig;
  report: ReportConfig;
};

/**
 * Runtime state types
 */

export type AuditPlan = {
  config: AuditConfig;
  queries: Query[];
  runId: string;
  startTime: Date;
};

export type AuditResult = {
  plan: AuditPlan;
  records: AuditRecord[];
  endTime: Date;
  summary: {
    totalQueries: number;
    successful: number;
    failed: number;
    averageScore: number;
  };
};
