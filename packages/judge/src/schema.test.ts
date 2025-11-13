import { describe, it, expect } from "vitest";
import { JudgeScoreSchema, getJudgeSchemaForPrompt } from "./schema";

describe("schema", () => {
  describe("JudgeScoreSchema", () => {
    it("should validate a correct judge score", () => {
      const validScore = {
        overall: 4.5,
        relevance: 4.0,
        diversity: 3.5,
        resultQuality: 4.5,
        navigability: 3.0,
        rationale: "Good results overall",
        issues: ["Some duplicates"],
        improvements: ["Add more filters"],
        evidence: [
          { rank: 1, why: "Perfect match" },
          { rank: 2, why: "Good alternative" },
        ],
        schemaVersion: "1.0",
      };

      const result = JudgeScoreSchema.safeParse(validScore);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(validScore);
      }
    });

    it("should reject scores outside 0-5 range", () => {
      const invalidScore = {
        overall: 6.0, // Invalid: > 5
        relevance: 4.0,
        diversity: 3.5,
        resultQuality: 4.5,
        navigability: 3.0,
        rationale: "Test",
        issues: [],
        improvements: [],
        evidence: [],
        schemaVersion: "1.0",
      };

      const result = JudgeScoreSchema.safeParse(invalidScore);

      expect(result.success).toBe(false);
    });

    it("should reject negative scores", () => {
      const invalidScore = {
        overall: 4.0,
        relevance: -1.0, // Invalid: < 0
        diversity: 3.5,
        resultQuality: 4.5,
        navigability: 3.0,
        rationale: "Test",
        issues: [],
        improvements: [],
        evidence: [],
        schemaVersion: "1.0",
      };

      const result = JudgeScoreSchema.safeParse(invalidScore);

      expect(result.success).toBe(false);
    });

    it("should require all fields", () => {
      const incompleteScore = {
        overall: 4.0,
        relevance: 4.0,
        // Missing other required fields
      };

      const result = JudgeScoreSchema.safeParse(incompleteScore);

      expect(result.success).toBe(false);
    });

    it("should validate evidence array structure", () => {
      const scoreWithBadEvidence = {
        overall: 4.0,
        relevance: 4.0,
        diversity: 3.5,
        resultQuality: 4.5,
        navigability: 3.0,
        rationale: "Test",
        issues: [],
        improvements: [],
        evidence: [
          { rank: 1 }, // Missing 'why' field
        ],
        schemaVersion: "1.0",
      };

      const result = JudgeScoreSchema.safeParse(scoreWithBadEvidence);

      expect(result.success).toBe(false);
    });
  });

  describe("getJudgeSchemaForPrompt", () => {
    it("should return a valid JSON schema object", () => {
      const schema = getJudgeSchemaForPrompt();

      expect(schema).toBeDefined();
      expect(schema).toHaveProperty("type", "object");
      expect(schema).toHaveProperty("properties");
      expect(schema).toHaveProperty("required");
    });

    it("should include all required fields in schema", () => {
      const schema = getJudgeSchemaForPrompt() as any;

      const requiredFields = [
        "overall",
        "relevance",
        "diversity",
        "resultQuality",
        "navigability",
        "rationale",
        "issues",
        "improvements",
        "evidence",
        "schemaVersion",
      ];

      requiredFields.forEach((field) => {
        expect(schema.properties).toHaveProperty(field);
      });

      expect(schema.required).toEqual(requiredFields);
    });
  });
});
