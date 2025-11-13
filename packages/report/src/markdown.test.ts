import { describe, it, expect } from "vitest";
import { generateMarkdownReport, ReportData } from "./markdown";

describe("markdown report", () => {
  const mockReportData: ReportData = {
    site: "https://www.example.com",
    runId: "2025-01-01-120000",
    timestamp: "2025-01-01T12:00:00Z",
    config: {
      topK: 10,
      model: "gpt-4o-mini",
      seed: 42,
    },
    records: [
      {
        site: "https://www.example.com",
        query: {
          id: "q1",
          text: "test query",
          origin: "predefined" as const,
        },
        items: [
          {
            rank: 1,
            title: "Result 1",
            url: "https://example.com/1",
            snippet: "Test snippet 1",
            price: "$99.99",
          },
          {
            rank: 2,
            title: "Result 2",
            url: "https://example.com/2",
            snippet: "Test snippet 2",
          },
        ],
        page: {
          url: "https://www.example.com",
          finalUrl: "https://www.example.com/search?q=test",
          screenshotPath: "/runs/test/q1-screenshot.png",
          htmlPath: "/runs/test/q1-page.html",
          ts: "2025-01-01T12:00:00Z",
        },
        judge: {
          overall: 4.5,
          relevance: 4.0,
          diversity: 3.5,
          resultQuality: 5.0,
          navigability: 3.0,
          rationale: "Good results with relevant content",
          issues: ["Some duplicates found"],
          improvements: ["Add more category filters"],
        },
      },
    ],
    summary: {
      totalQueries: 1,
      successful: 1,
      failed: 0,
      averageScore: 4.5,
    },
  };

  describe("generateMarkdownReport", () => {
    it("should generate a valid markdown report", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toBeDefined();
      expect(markdown).toContain("# Search Quality Audit Report");
    });

    it("should include site and configuration info", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("https://www.example.com");
      expect(markdown).toContain("gpt-4o-mini");
      expect(markdown).toContain("Top-K:** 10");
      expect(markdown).toContain("Seed:** 42");
    });

    it("should include summary statistics", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("Total Queries: 1");
      expect(markdown).toContain("Successful: 1");
      expect(markdown).toContain("Failed: 0");
      expect(markdown).toContain("Average Score: 4.50");
    });

    it("should include query details", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain('Query: "test query"');
      expect(markdown).toContain("q1");
      expect(markdown).toContain("predefined");
    });

    it("should include scores with stars", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("Overall");
      expect(markdown).toContain("4.5");
      expect(markdown).toContain("★"); // Stars for scores
    });

    it("should include rationale and issues", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("Good results with relevant content");
      expect(markdown).toContain("Some duplicates found");
      expect(markdown).toContain("Add more category filters");
    });

    it("should include results table", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("Result 1");
      expect(markdown).toContain("Result 2");
      expect(markdown).toContain("$99.99");
      expect(markdown).toContain("Test snippet 1");
    });

    it("should include artifact paths", () => {
      const markdown = generateMarkdownReport(mockReportData);

      expect(markdown).toContain("q1-screenshot.png");
      expect(markdown).toContain("q1-page.html");
    });

    it("should handle multiple queries", () => {
      const multiQueryData = {
        ...mockReportData,
        records: [
          mockReportData.records[0],
          {
            ...mockReportData.records[0],
            query: { id: "q2", text: "another query", origin: "generated" as const },
          },
        ],
        summary: {
          totalQueries: 2,
          successful: 2,
          failed: 0,
          averageScore: 4.25,
        },
      };

      const markdown = generateMarkdownReport(multiQueryData);

      expect(markdown).toContain("test query");
      expect(markdown).toContain("another query");
      expect(markdown).toContain("Total Queries: 2");
    });

    it("should truncate long titles and snippets", () => {
      const longTitleData = {
        ...mockReportData,
        records: [
          {
            ...mockReportData.records[0],
            items: [
              {
                rank: 1,
                title: "A".repeat(100),
                snippet: "B".repeat(100),
              },
            ],
          },
        ],
      };

      const markdown = generateMarkdownReport(longTitleData);

      // Should contain ellipsis for truncated content
      expect(markdown).toContain("...");
    });
  });
});
