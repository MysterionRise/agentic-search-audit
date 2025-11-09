#!/usr/bin/env node

/**
 * CLI entry point for search-audit
 */

import { Command } from "commander";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import { loadConfig, loadQueries, SearchAuditOrchestrator } from "@search-audit/core";
import { writeMarkdownReport, writeHTMLReport } from "@search-audit/report";

// Load environment variables
dotenv.config();

const program = new Command();

program
  .name("search-audit")
  .description("AI-powered on-site search quality evaluation")
  .version("0.1.0");

program
  .command("run")
  .description("Run a search audit")
  .requiredOption("--site <url>", "Site URL to audit (e.g., https://www.nike.com)")
  .option("--config <path>", "Path to config YAML file")
  .option("--queries <path>", "Path to queries JSON file")
  .option("--topk <number>", "Number of top results to extract", "10")
  .option("--seed <number>", "Random seed for reproducibility", "42")
  .option("--out <dir>", "Output directory for reports", "./runs")
  .action(async (options) => {
    try {
      console.log("=== Search Quality Audit ===\n");

      // Load configuration
      let config = options.config ? loadConfig(options.config) : loadConfig();

      // Override with CLI options
      if (options.site) {
        config.site.url = options.site;
      }

      if (options.topk) {
        config.run.topK = parseInt(options.topk, 10);
      }

      if (options.seed) {
        config.run.seed = parseInt(options.seed, 10);
      }

      if (options.out) {
        config.report.outDir = options.out;
      }

      // Validate required settings
      if (!config.site.url) {
        throw new Error("Site URL is required (use --site or config file)");
      }

      if (!process.env.OPENAI_API_KEY) {
        throw new Error("OPENAI_API_KEY environment variable is required");
      }

      // Load queries
      let queries;
      if (options.queries) {
        queries = loadQueries(options.queries);
      } else {
        throw new Error("Queries file is required (use --queries)");
      }

      if (!queries || queries.length === 0) {
        throw new Error("No queries found in file");
      }

      // Generate run ID
      const runId = generateRunId();

      // Run audit
      const orchestrator = new SearchAuditOrchestrator(config, runId);
      const result = await orchestrator.runAudit(queries);

      // Generate reports
      console.log("\nGenerating reports...");
      const runDir = orchestrator.getRunDir();

      const reportData = {
        site: config.site.url,
        runId,
        timestamp: result.endTime.toISOString(),
        config: {
          topK: config.run.topK,
          model: config.llm.model,
          seed: config.run.seed,
        },
        records: result.records,
        summary: result.summary,
      };

      // Write Markdown report
      if (config.report.format.includes("md")) {
        const mdPath = path.join(runDir, "report.md");
        writeMarkdownReport(reportData, mdPath);
        console.log(`✓ Markdown report: ${mdPath}`);
      }

      // Write HTML report
      if (config.report.format.includes("html")) {
        const htmlPath = path.join(runDir, "report.html");
        writeHTMLReport(reportData, htmlPath);
        console.log(`✓ HTML report: ${htmlPath}`);
      }

      console.log(`\n=== Success ===`);
      console.log(`Reports saved to: ${runDir}`);
      console.log(`\nTo view the Markdown report:`);
      console.log(`  cat ${path.join(runDir, "report.md")}`);
      console.log(`\nTo view the HTML report:`);
      console.log(`  open ${path.join(runDir, "report.html")}`);

      process.exit(0);
    } catch (error) {
      console.error(`\n❌ Error: ${error}`);
      process.exit(1);
    }
  });

program
  .command("validate")
  .description("Validate a configuration file")
  .requiredOption("--config <path>", "Path to config YAML file")
  .action((options) => {
    try {
      const config = loadConfig(options.config);
      console.log("✓ Configuration is valid");
      console.log(JSON.stringify(config, null, 2));
      process.exit(0);
    } catch (error) {
      console.error(`❌ Invalid configuration: ${error}`);
      process.exit(1);
    }
  });

program.parse(process.argv);

/**
 * Generate a unique run ID
 */
function generateRunId(): string {
  const date = new Date();
  const dateStr = date.toISOString().split("T")[0]; // YYYY-MM-DD
  const timeStr = date.toTimeString().split(" ")[0].replace(/:/g, ""); // HHMMSS
  return `${dateStr}-${timeStr}`;
}
