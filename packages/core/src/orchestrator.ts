/**
 * Core orchestrator for running search audits
 */

import * as fs from "fs";
import * as path from "path";
import { MCPBrowserClient } from "@search-audit/mcp";
import { dismissModals, findSearchBox, submitSearch, extractResults } from "@search-audit/extractors";
import { createLLMClient, JudgeInput } from "@search-audit/judge";
import { AuditConfig, AuditPlan, AuditRecord, AuditResult, Query, PageArtifacts, JudgeScore } from "./types";
import { RateLimiter, delay } from "./policies";

/**
 * Main orchestrator class
 */
export class SearchAuditOrchestrator {
  private config: AuditConfig;
  private client: MCPBrowserClient;
  private rateLimiter: RateLimiter;
  private runDir: string;

  constructor(config: AuditConfig, runId: string) {
    this.config = config;
    this.client = new MCPBrowserClient();
    this.rateLimiter = new RateLimiter(config.run.throttleRPS);
    this.runDir = path.join(config.report.outDir, runId);

    // Create run directory
    if (!fs.existsSync(this.runDir)) {
      fs.mkdirSync(this.runDir, { recursive: true });
    }
  }

  /**
   * Run the complete audit
   */
  async runAudit(queries: Query[]): Promise<AuditResult> {
    const plan: AuditPlan = {
      config: this.config,
      queries,
      runId: path.basename(this.runDir),
      startTime: new Date(),
    };

    console.log(`Starting audit for ${this.config.site.url}`);
    console.log(`Run ID: ${plan.runId}`);
    console.log(`Queries: ${queries.length}`);

    const records: AuditRecord[] = [];
    let successful = 0;
    let failed = 0;

    try {
      // Connect to MCP browser
      console.log("\nConnecting to Chrome via MCP...");
      await this.client.connect();

      // Set viewport
      await this.client.setViewport(this.config.run.viewport);

      // Navigate to site
      console.log(`Navigating to ${this.config.site.url}...`);
      await this.client.navigate(this.config.site.url);
      await delay(1000);

      // Dismiss modals
      console.log("Dismissing modals...");
      const modalsClicked = await dismissModals(this.client, this.config.site.modals);
      console.log(`Dismissed ${modalsClicked} modal(s)`);

      // Process each query
      for (let i = 0; i < queries.length; i++) {
        const query = queries[i];
        console.log(`\n[${i + 1}/${queries.length}] Processing query: "${query.text}"`);

        try {
          await this.rateLimiter.wait();
          const record = await this.processQuery(query, plan.runId);
          records.push(record);
          successful++;
          console.log(`✓ Score: ${record.judge.overall.toFixed(1)}/5.0`);
        } catch (error) {
          console.error(`✗ Failed: ${error}`);
          failed++;
        }
      }
    } finally {
      // Disconnect from MCP
      await this.client.disconnect();
      console.log("\nDisconnected from browser");
    }

    // Calculate summary
    const summary = {
      totalQueries: queries.length,
      successful,
      failed,
      averageScore: successful > 0 ? records.reduce((sum, r) => sum + r.judge.overall, 0) / successful : 0,
    };

    const result: AuditResult = {
      plan,
      records,
      endTime: new Date(),
      summary,
    };

    // Write JSONL output
    this.writeJSONL(records);

    console.log(`\n=== Audit Complete ===`);
    console.log(`Total: ${summary.totalQueries} | Success: ${successful} | Failed: ${failed}`);
    console.log(`Average Score: ${summary.averageScore.toFixed(2)}/5.0`);

    return result;
  }

  /**
   * Process a single query
   */
  private async processQuery(query: Query, runId: string): Promise<AuditRecord> {
    // Find search box
    const searchBoxSelector = await findSearchBox(this.client, this.config.site.search);
    if (!searchBoxSelector) {
      throw new Error("Could not find search box");
    }

    // Submit search
    await submitSearch(this.client, searchBoxSelector, query.text, this.config.site.search);

    // Wait for results
    await delay(this.config.run.waitFor.postSubmitMs);
    await this.client.waitForNetworkIdle(this.config.run.waitFor.networkIdleMs);

    // Extract results
    const items = await extractResults(this.client, this.config.site.results, this.config.run.topK);

    if (items.length === 0) {
      throw new Error("No results found");
    }

    // Capture artifacts
    const artifacts = await this.captureArtifacts(query.id, runId);

    // Get judge evaluation
    const judge = await this.evaluateResults(query, items, artifacts);

    return {
      site: this.config.site.url,
      query,
      items,
      page: artifacts,
      judge,
    };
  }

  /**
   * Capture page artifacts (screenshot, HTML)
   */
  private async captureArtifacts(queryId: string, runId: string): Promise<PageArtifacts> {
    const timestamp = new Date().toISOString();
    const screenshotPath = path.join(this.runDir, `${queryId}-screenshot.png`);
    const htmlPath = path.join(this.runDir, `${queryId}-page.html`);

    // Take screenshot
    await this.client.screenshot({
      path: screenshotPath,
      fullPage: true,
    });

    // Save HTML
    const html = await this.client.getHTML();
    fs.writeFileSync(htmlPath, html, "utf8");

    // Get current URL
    const finalUrl = await this.client.getCurrentURL();

    return {
      url: this.config.site.url,
      finalUrl,
      htmlPath,
      screenshotPath,
      ts: timestamp,
    };
  }

  /**
   * Evaluate results using LLM judge
   */
  private async evaluateResults(
    query: Query,
    items: any[],
    artifacts: PageArtifacts
  ): Promise<JudgeScore> {
    const llmClient = createLLMClient({
      provider: this.config.llm.provider,
      model: this.config.llm.model,
      maxTokens: this.config.llm.maxTokens,
      temperature: this.config.llm.temperature,
      systemPrompt: this.config.llm.systemPrompt,
      seed: this.config.run.seed,
    });

    // Read page snapshot (truncated)
    const pageSnapshot = fs.readFileSync(artifacts.htmlPath, "utf8").substring(0, 2000);

    const input: JudgeInput = {
      site: this.config.site.url,
      query: query.text,
      results: items.map((item) => ({
        rank: item.rank,
        title: item.title,
        url: item.url,
        snippet: item.snippet,
        price: item.price,
      })),
      pageSnapshot,
    };

    return await llmClient.evaluate(input);
  }

  /**
   * Write records to JSONL file
   */
  private writeJSONL(records: AuditRecord[]): void {
    const jsonlPath = path.join(this.runDir, "audit.jsonl");
    const lines = records.map((r) => JSON.stringify(r)).join("\n");
    fs.writeFileSync(jsonlPath, lines, "utf8");
    console.log(`\nWrote ${records.length} records to ${jsonlPath}`);
  }

  /**
   * Get the run directory path
   */
  getRunDir(): string {
    return this.runDir;
  }
}
