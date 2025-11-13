import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { loadConfig, loadQueries } from "./config";
import * as fs from "fs";
import * as path from "path";
import { tmpdir } from "os";

describe("config", () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(tmpdir(), "config-test-"));
  });

  afterEach(() => {
    // Cleanup temp directory
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  describe("loadConfig", () => {
    it("should return default config when no path provided", () => {
      const config = loadConfig();

      expect(config).toBeDefined();
      expect(config.site).toBeDefined();
      expect(config.run).toBeDefined();
      expect(config.llm).toBeDefined();
      expect(config.report).toBeDefined();
    });

    it("should load config from YAML file", () => {
      const configPath = path.join(tempDir, "test-config.yaml");
      const yamlContent = `
site:
  url: "https://test.com"
  locale: "en-US"
run:
  topK: 20
  seed: 123
llm:
  provider: "openai"
  model: "gpt-4"
report:
  format: ["md"]
`;
      fs.writeFileSync(configPath, yamlContent);

      const config = loadConfig(configPath);

      expect(config.site.url).toBe("https://test.com");
      expect(config.run.topK).toBe(20);
      expect(config.run.seed).toBe(123);
      expect(config.llm.model).toBe("gpt-4");
      expect(config.report.format).toContain("md");
    });

    it("should merge partial config with defaults", () => {
      const configPath = path.join(tempDir, "partial-config.yaml");
      const yamlContent = `
site:
  url: "https://test.com"
run:
  topK: 15
`;
      fs.writeFileSync(configPath, yamlContent);

      const config = loadConfig(configPath);

      // Custom values
      expect(config.site.url).toBe("https://test.com");
      expect(config.run.topK).toBe(15);

      // Default values
      expect(config.run.headless).toBeDefined();
      expect(config.llm.provider).toBeDefined();
      expect(config.report.format).toBeDefined();
    });

    it("should have sensible defaults", () => {
      const config = loadConfig();

      expect(config.run.topK).toBe(10);
      expect(config.run.headless).toBe(true);
      expect(config.llm.provider).toBe("openai");
      expect(config.llm.model).toBe("gpt-4o-mini");
      expect(config.report.format).toContain("md");
      expect(config.report.format).toContain("html");
    });

    it("should include default selectors", () => {
      const config = loadConfig();

      expect(config.site.search.inputSelectors).toContain('input[type="search"]');
      expect(config.site.modals.closeTextMatches).toContain("accept");
      expect(config.site.modals.closeTextMatches).toContain("close");
    });
  });

  describe("loadQueries", () => {
    it("should load queries from JSON file", () => {
      const queriesPath = path.join(tempDir, "queries.json");
      const queries = [
        { id: "q1", text: "test query 1", origin: "predefined" },
        { id: "q2", text: "test query 2", origin: "generated" },
      ];
      fs.writeFileSync(queriesPath, JSON.stringify(queries));

      const loaded = loadQueries(queriesPath);

      expect(loaded).toEqual(queries);
      expect(loaded).toHaveLength(2);
    });

    it("should throw error for invalid JSON", () => {
      const queriesPath = path.join(tempDir, "invalid.json");
      fs.writeFileSync(queriesPath, "invalid json {");

      expect(() => loadQueries(queriesPath)).toThrow();
    });

    it("should throw error for non-existent file", () => {
      const queriesPath = path.join(tempDir, "nonexistent.json");

      expect(() => loadQueries(queriesPath)).toThrow();
    });
  });
});
