import { describe, it, expect } from "vitest";
import { buildSystemPrompt, buildUserPrompt, JudgeInput } from "./rubric";

describe("rubric", () => {
  describe("buildSystemPrompt", () => {
    it("should return default prompt if no custom prompt provided", () => {
      const prompt = buildSystemPrompt();

      expect(prompt).toBeDefined();
      expect(prompt).toContain("search quality judge");
      expect(prompt).toContain("Relevance");
      expect(prompt).toContain("Diversity");
      expect(prompt).toContain("Result Quality");
      expect(prompt).toContain("Navigability");
    });

    it("should return custom prompt if provided", () => {
      const customPrompt = "Custom judge prompt";
      const prompt = buildSystemPrompt(customPrompt);

      expect(prompt).toBe(customPrompt);
    });

    it("should include scoring dimensions in default prompt", () => {
      const prompt = buildSystemPrompt();

      expect(prompt).toContain("0-5");
      expect(prompt.toLowerCase()).toContain("relevance");
      expect(prompt.toLowerCase()).toContain("diversity");
      expect(prompt.toLowerCase()).toContain("navigability");
      expect(prompt.toLowerCase()).toContain("overall");
    });
  });

  describe("buildUserPrompt", () => {
    it("should include query and site information", () => {
      const input: JudgeInput = {
        site: "https://www.example.com",
        query: "test query",
        results: [
          {
            rank: 1,
            title: "Result 1",
            url: "https://example.com/1",
            snippet: "Test snippet",
          },
        ],
      };

      const prompt = buildUserPrompt(input);

      expect(prompt).toContain("example.com");
      expect(prompt).toContain("test query");
    });

    it("should format results correctly", () => {
      const input: JudgeInput = {
        site: "https://www.example.com",
        query: "test",
        results: [
          {
            rank: 1,
            title: "Product 1",
            url: "https://example.com/1",
            snippet: "Great product",
            price: "$99.99",
          },
          {
            rank: 2,
            title: "Product 2",
            url: "https://example.com/2",
          },
        ],
      };

      const prompt = buildUserPrompt(input);

      expect(prompt).toContain("Rank 1");
      expect(prompt).toContain("Product 1");
      expect(prompt).toContain("$99.99");
      expect(prompt).toContain("Rank 2");
      expect(prompt).toContain("Product 2");
    });

    it("should include page snapshot if provided", () => {
      const input: JudgeInput = {
        site: "https://www.example.com",
        query: "test",
        results: [],
        pageSnapshot: "<html>Test page content</html>",
      };

      const prompt = buildUserPrompt(input);

      expect(prompt).toContain("Page Context");
      expect(prompt).toContain("Test page content");
    });

    it("should truncate long page snapshots", () => {
      const longSnapshot = "a".repeat(2000);
      const input: JudgeInput = {
        site: "https://www.example.com",
        query: "test",
        results: [],
        pageSnapshot: longSnapshot,
      };

      const prompt = buildUserPrompt(input);

      // Should only include first 1000 characters
      const snapshotInPrompt = prompt.match(/Page Context.*?\n\n/s)?.[0];
      expect(snapshotInPrompt!.length).toBeLessThan(1100); // 1000 + some overhead
    });

    it("should include JSON schema in prompt", () => {
      const input: JudgeInput = {
        site: "https://www.example.com",
        query: "test",
        results: [],
      };

      const prompt = buildUserPrompt(input);

      expect(prompt).toContain("JSON");
      expect(prompt).toContain("schema");
      expect(prompt).toContain("overall");
      expect(prompt).toContain("relevance");
    });
  });
});
