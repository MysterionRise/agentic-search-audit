/**
 * Markdown report generator
 */

import * as fs from "fs";
import * as path from "path";

export type AuditRecord = {
  site: string;
  query: {
    id: string;
    text: string;
    origin: "predefined" | "generated";
  };
  items: Array<{
    rank: number;
    title?: string;
    url?: string;
    snippet?: string;
    price?: string;
  }>;
  page: {
    url: string;
    finalUrl: string;
    screenshotPath: string;
    htmlPath: string;
  };
  judge: {
    overall: number;
    relevance: number;
    diversity: number;
    resultQuality: number;
    navigability: number;
    rationale: string;
    issues: string[];
    improvements: string[];
  };
};

export type AuditSummary = {
  totalQueries: number;
  successful: number;
  failed: number;
  averageScore: number;
};

export type ReportData = {
  site: string;
  runId: string;
  timestamp: string;
  config: {
    topK: number;
    model: string;
    seed: number;
  };
  records: AuditRecord[];
  summary: AuditSummary;
};

/**
 * Generate a Markdown report from audit results
 */
export function generateMarkdownReport(data: ReportData): string {
  const lines: string[] = [];

  // Header
  lines.push(`# Search Quality Audit Report\n`);
  lines.push(`**Site:** ${data.site}`);
  lines.push(`**Run ID:** ${data.runId}`);
  lines.push(`**Timestamp:** ${data.timestamp}`);
  lines.push(`**Model:** ${data.config.model}`);
  lines.push(`**Top-K:** ${data.config.topK}`);
  lines.push(`**Seed:** ${data.config.seed}\n`);

  // Summary
  lines.push(`## Summary\n`);
  lines.push(`- Total Queries: ${data.summary.totalQueries}`);
  lines.push(`- Successful: ${data.summary.successful}`);
  lines.push(`- Failed: ${data.summary.failed}`);
  lines.push(`- Average Score: ${data.summary.averageScore.toFixed(2)}/5.0\n`);

  // Score distribution (ASCII histogram)
  lines.push(`### Score Distribution\n`);
  const scores = data.records.map((r) => r.judge.overall);
  lines.push(generateScoreHistogram(scores));
  lines.push("");

  // Per-query results
  lines.push(`## Query Results\n`);

  for (const record of data.records) {
    lines.push(`### Query: "${record.query.text}"\n`);
    lines.push(`**Query ID:** ${record.query.id} | **Origin:** ${record.query.origin}\n`);

    // Judge scores
    lines.push(`#### Scores\n`);
    lines.push(`| Dimension | Score |`);
    lines.push(`|-----------|-------|`);
    lines.push(`| Overall | ${formatScore(record.judge.overall)} |`);
    lines.push(`| Relevance | ${formatScore(record.judge.relevance)} |`);
    lines.push(`| Diversity | ${formatScore(record.judge.diversity)} |`);
    lines.push(`| Result Quality | ${formatScore(record.judge.resultQuality)} |`);
    lines.push(`| Navigability | ${formatScore(record.judge.navigability)} |\n`);

    lines.push(`**Rationale:** ${record.judge.rationale}\n`);

    if (record.judge.issues.length > 0) {
      lines.push(`**Issues:**`);
      record.judge.issues.forEach((issue) => lines.push(`- ${issue}`));
      lines.push("");
    }

    if (record.judge.improvements.length > 0) {
      lines.push(`**Improvements:**`);
      record.judge.improvements.forEach((imp) => lines.push(`- ${imp}`));
      lines.push("");
    }

    // Top results
    lines.push(`#### Top ${record.items.length} Results\n`);
    lines.push(`| Rank | Title | URL | Snippet | Price |`);
    lines.push(`|------|-------|-----|---------|-------|`);

    for (const item of record.items.slice(0, 10)) {
      const title = truncate(item.title || "—", 40);
      const url = item.url ? `[link](${item.url})` : "—";
      const snippet = truncate(item.snippet || "—", 50);
      const price = item.price || "—";
      lines.push(`| ${item.rank} | ${title} | ${url} | ${snippet} | ${price} |`);
    }
    lines.push("");

    // Artifacts
    lines.push(`#### Artifacts\n`);
    lines.push(`- Screenshot: \`${record.page.screenshotPath}\``);
    lines.push(`- HTML Snapshot: \`${record.page.htmlPath}\``);
    lines.push(`- Final URL: ${record.page.finalUrl}\n`);

    lines.push(`---\n`);
  }

  return lines.join("\n");
}

/**
 * Write Markdown report to file
 */
export function writeMarkdownReport(data: ReportData, outputPath: string): void {
  const markdown = generateMarkdownReport(data);
  fs.writeFileSync(outputPath, markdown, "utf8");
}

function formatScore(score: number): string {
  const stars = "★".repeat(Math.round(score));
  const empty = "☆".repeat(5 - Math.round(score));
  return `${score.toFixed(1)} ${stars}${empty}`;
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.substring(0, maxLen - 3) + "...";
}

function generateScoreHistogram(scores: number[]): string {
  const buckets = [0, 0, 0, 0, 0, 0]; // 0-5

  scores.forEach((score) => {
    const bucket = Math.min(Math.floor(score), 5);
    buckets[bucket]++;
  });

  const lines: string[] = [];
  for (let i = 5; i >= 0; i--) {
    const count = buckets[i];
    const bar = "█".repeat(count);
    lines.push(`${i}: ${bar} (${count})`);
  }

  return "```\n" + lines.join("\n") + "\n```";
}
