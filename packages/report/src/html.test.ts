import { describe, it, expect } from "vitest";
import { generateHTMLReport } from "./html";
import { ReportData } from "./markdown";

describe("html report", () => {
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
            snippet: "Test snippet",
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
          rationale: "Good results",
          issues: ["Some issue"],
          improvements: ["Some improvement"],
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

  describe("generateHTMLReport", () => {
    it("should generate valid HTML", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("<!DOCTYPE html>");
      expect(html).toContain("<html");
      expect(html).toContain("</html>");
      expect(html).toContain("<head>");
      expect(html).toContain("<body>");
    });

    it("should include page title", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("<title>");
      expect(html).toContain("Search Quality Audit");
      expect(html).toContain("example.com");
    });

    it("should include CSS styles", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("<style>");
      expect(html).toContain("</style>");
      expect(html).toContain("font-family");
    });

    it("should escape HTML in user content", () => {
      const xssData = {
        ...mockReportData,
        records: [
          {
            ...mockReportData.records[0],
            items: [
              {
                rank: 1,
                title: "<script>alert('xss')</script>",
                snippet: 'Test <img src="x" onerror="alert(1)">',
              },
            ],
          },
        ],
      };

      const html = generateHTMLReport(xssData);

      expect(html).not.toContain("<script>alert");
      expect(html).toContain("&lt;script&gt;");
      expect(html).not.toContain('onerror="alert');
    });

    it("should include summary cards", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("Total Queries");
      expect(html).toContain("Successful");
      expect(html).toContain("Average Score");
      expect(html).toContain(">1<"); // Total count
      expect(html).toContain(">4.50<"); // Average score
    });

    it("should include query results", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("test query");
      expect(html).toContain("Result 1");
      expect(html).toContain("Good results");
    });

    it("should include scores", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("4.5");
      expect(html).toContain("4.0");
      expect(html).toContain("3.5");
      expect(html).toContain("Overall");
      expect(html).toContain("Relevance");
    });

    it("should include artifacts section", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain("Artifacts");
      expect(html).toContain("q1-screenshot.png");
      expect(html).toContain("q1-page.html");
    });

    it("should create clickable links", () => {
      const html = generateHTMLReport(mockReportData);

      expect(html).toContain('<a href="https://example.com/1"');
      expect(html).toContain('target="_blank"');
    });

    it("should handle missing optional fields gracefully", () => {
      const minimalData = {
        ...mockReportData,
        records: [
          {
            ...mockReportData.records[0],
            items: [
              {
                rank: 1,
                // No title, url, snippet, price
              },
            ],
            judge: {
              ...mockReportData.records[0].judge,
              issues: [],
              improvements: [],
            },
          },
        ],
      };

      const html = generateHTMLReport(minimalData);

      expect(html).toBeDefined();
      expect(html).toContain("<!DOCTYPE html>");
    });
  });
});
