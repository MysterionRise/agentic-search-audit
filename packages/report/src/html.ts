/**
 * HTML report generator
 */

import * as fs from "fs";
import { ReportData } from "./markdown";

/**
 * Generate an HTML report from audit results
 */
export function generateHTMLReport(data: ReportData): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Search Quality Audit - ${data.site}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .header {
      background: white;
      padding: 20px;
      border-radius: 8px;
      margin-bottom: 20px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { margin: 0 0 10px 0; color: #333; }
    .meta { color: #666; font-size: 14px; }
    .summary {
      background: white;
      padding: 20px;
      border-radius: 8px;
      margin-bottom: 20px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 15px;
      margin-top: 15px;
    }
    .summary-card {
      background: #f8f9fa;
      padding: 15px;
      border-radius: 6px;
      text-align: center;
    }
    .summary-card .value {
      font-size: 32px;
      font-weight: bold;
      color: #007bff;
    }
    .summary-card .label {
      font-size: 14px;
      color: #666;
      margin-top: 5px;
    }
    .query-result {
      background: white;
      padding: 20px;
      border-radius: 8px;
      margin-bottom: 20px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .query-header {
      border-bottom: 2px solid #007bff;
      padding-bottom: 10px;
      margin-bottom: 15px;
    }
    .scores {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin: 15px 0;
    }
    .score-item {
      background: #f8f9fa;
      padding: 10px;
      border-radius: 4px;
      text-align: center;
    }
    .score-value {
      font-size: 24px;
      font-weight: bold;
      color: #28a745;
    }
    .score-label {
      font-size: 12px;
      color: #666;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 15px 0;
    }
    th, td {
      padding: 10px;
      text-align: left;
      border-bottom: 1px solid #ddd;
    }
    th {
      background: #f8f9fa;
      font-weight: 600;
    }
    .stars {
      color: #ffc107;
    }
    .issues, .improvements {
      margin: 15px 0;
    }
    .issues ul, .improvements ul {
      margin: 5px 0;
      padding-left: 20px;
    }
    .artifacts {
      background: #f8f9fa;
      padding: 10px;
      border-radius: 4px;
      margin-top: 15px;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>🔍 Search Quality Audit Report</h1>
    <div class="meta">
      <strong>Site:</strong> ${escapeHtml(data.site)}<br>
      <strong>Run ID:</strong> ${escapeHtml(data.runId)}<br>
      <strong>Timestamp:</strong> ${escapeHtml(data.timestamp)}<br>
      <strong>Model:</strong> ${escapeHtml(data.config.model)} |
      <strong>Top-K:</strong> ${data.config.topK} |
      <strong>Seed:</strong> ${data.config.seed}
    </div>
  </div>

  <div class="summary">
    <h2>Summary</h2>
    <div class="summary-grid">
      <div class="summary-card">
        <div class="value">${data.summary.totalQueries}</div>
        <div class="label">Total Queries</div>
      </div>
      <div class="summary-card">
        <div class="value">${data.summary.successful}</div>
        <div class="label">Successful</div>
      </div>
      <div class="summary-card">
        <div class="value">${data.summary.failed}</div>
        <div class="label">Failed</div>
      </div>
      <div class="summary-card">
        <div class="value">${data.summary.averageScore.toFixed(2)}</div>
        <div class="label">Average Score</div>
      </div>
    </div>
  </div>

  ${data.records.map((record) => generateQuerySection(record)).join("\n")}

</body>
</html>`;
}

function generateQuerySection(record: any): string {
  return `
  <div class="query-result">
    <div class="query-header">
      <h3>Query: "${escapeHtml(record.query.text)}"</h3>
      <div class="meta">
        <strong>ID:</strong> ${record.query.id} |
        <strong>Origin:</strong> ${record.query.origin}
      </div>
    </div>

    <div class="scores">
      <div class="score-item">
        <div class="score-value">${record.judge.overall.toFixed(1)}</div>
        <div class="score-label">Overall</div>
      </div>
      <div class="score-item">
        <div class="score-value">${record.judge.relevance.toFixed(1)}</div>
        <div class="score-label">Relevance</div>
      </div>
      <div class="score-item">
        <div class="score-value">${record.judge.diversity.toFixed(1)}</div>
        <div class="score-label">Diversity</div>
      </div>
      <div class="score-item">
        <div class="score-value">${record.judge.resultQuality.toFixed(1)}</div>
        <div class="score-label">Result Quality</div>
      </div>
      <div class="score-item">
        <div class="score-value">${record.judge.navigability.toFixed(1)}</div>
        <div class="score-label">Navigability</div>
      </div>
    </div>

    <p><strong>Rationale:</strong> ${escapeHtml(record.judge.rationale)}</p>

    ${
      record.judge.issues.length > 0
        ? `<div class="issues">
        <strong>Issues:</strong>
        <ul>${record.judge.issues.map((i: string) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
      </div>`
        : ""
    }

    ${
      record.judge.improvements.length > 0
        ? `<div class="improvements">
        <strong>Improvements:</strong>
        <ul>${record.judge.improvements.map((i: string) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
      </div>`
        : ""
    }

    <h4>Top Results</h4>
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Title</th>
          <th>URL</th>
          <th>Snippet</th>
          <th>Price</th>
        </tr>
      </thead>
      <tbody>
        ${record.items
          .slice(0, 10)
          .map(
            (item: any) => `
          <tr>
            <td>${item.rank}</td>
            <td>${escapeHtml(item.title || "—")}</td>
            <td>${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank">link</a>` : "—"}</td>
            <td>${escapeHtml(truncate(item.snippet || "—", 80))}</td>
            <td>${escapeHtml(item.price || "—")}</td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>

    <div class="artifacts">
      <strong>Artifacts:</strong><br>
      📸 Screenshot: <code>${escapeHtml(record.page.screenshotPath)}</code><br>
      📄 HTML: <code>${escapeHtml(record.page.htmlPath)}</code><br>
      🔗 Final URL: <a href="${escapeHtml(record.page.finalUrl)}" target="_blank">${escapeHtml(record.page.finalUrl)}</a>
    </div>
  </div>`;
}

/**
 * Write HTML report to file
 */
export function writeHTMLReport(data: ReportData, outputPath: string): void {
  const html = generateHTMLReport(data);
  fs.writeFileSync(outputPath, html, "utf8");
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.substring(0, maxLen - 3) + "...";
}
