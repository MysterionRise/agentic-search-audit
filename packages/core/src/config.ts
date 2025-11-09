import * as yaml from "js-yaml";
import * as fs from "fs";
import * as path from "path";
import { AuditConfig, SiteConfig, RunConfig, LLMConfig, ReportConfig } from "./types";

/**
 * Default configuration values
 */
const DEFAULT_CONFIG: AuditConfig = {
  site: {
    url: "",
    locale: "en-US",
    search: {
      inputSelectors: [
        'input[type="search"]',
        'input[aria-label*="Search" i]',
        'input[name="q"]',
        'input[placeholder*="Search" i]',
      ],
      submitStrategy: "enter",
    },
    results: {
      itemSelectors: ['a[href*="/"]', "article", ".product-card", '[data-test*="product"]'],
      titleSelectors: ["h1", "h2", "h3", ".title", "[title]", "a"],
      urlAttr: "href",
      snippetSelectors: [".description", ".snippet", "p", ".subtitle"],
    },
    modals: {
      closeTextMatches: ["accept", "agree", "continue", "got it", "close", "ok", "dismiss"],
      maxAutoClicks: 3,
    },
  },
  run: {
    topK: 10,
    viewport: { width: 1366, height: 900 },
    waitFor: { networkIdleMs: 1200, postSubmitMs: 800 },
    headless: true,
    throttleRPS: 0.5,
    seed: 42,
  },
  llm: {
    provider: "openai",
    model: "gpt-4o-mini",
    maxTokens: 800,
    temperature: 0.2,
    systemPrompt: "You are a careful search quality judge...",
  },
  report: {
    format: ["md", "html"],
    outDir: "./runs",
  },
};

/**
 * Load configuration from YAML file and merge with defaults
 */
export function loadConfig(configPath?: string): AuditConfig {
  if (!configPath) {
    return DEFAULT_CONFIG;
  }

  const rawConfig = yaml.load(fs.readFileSync(configPath, "utf8")) as Partial<AuditConfig>;

  // Deep merge with defaults
  return {
    site: { ...DEFAULT_CONFIG.site, ...(rawConfig.site || {}) },
    run: { ...DEFAULT_CONFIG.run, ...(rawConfig.run || {}) },
    llm: { ...DEFAULT_CONFIG.llm, ...(rawConfig.llm || {}) },
    report: { ...DEFAULT_CONFIG.report, ...(rawConfig.report || {}) },
  } as AuditConfig;
}

/**
 * Load queries from JSON file
 */
export function loadQueries(queriesPath: string) {
  const rawQueries = JSON.parse(fs.readFileSync(queriesPath, "utf8"));
  return rawQueries;
}
