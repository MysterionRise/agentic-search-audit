/**
 * JSON schema for LLM judge responses using Zod
 */

import { z } from "zod";

export const JudgeScoreSchema = z.object({
  overall: z.number().min(0).max(5).describe("Overall search quality score (0-5)"),
  relevance: z.number().min(0).max(5).describe("Relevance of results to query (0-5)"),
  diversity: z
    .number()
    .min(0)
    .max(5)
    .describe("Diversity of results (brands, categories, price points) (0-5)"),
  resultQuality: z
    .number()
    .min(0)
    .max(5)
    .describe("Quality of result presentation (clarity, no duplication, valid links) (0-5)"),
  navigability: z
    .number()
    .min(0)
    .max(5)
    .describe("Presence of filters, sorting, navigation aids (0-5)"),
  rationale: z.string().describe("Brief explanation of the overall score"),
  issues: z.array(z.string()).describe("List of problems found"),
  improvements: z.array(z.string()).describe("Suggested improvements"),
  evidence: z
    .array(
      z.object({
        rank: z.number().describe("Result rank number"),
        why: z.string().describe("1-2 line reason for this result's quality"),
      })
    )
    .describe("Evidence from specific results"),
  schemaVersion: z.string().describe("Schema version (e.g., '1.0')"),
});

export type JudgeScore = z.infer<typeof JudgeScoreSchema>;

/**
 * Get the JSON schema as a plain object for the LLM prompt
 */
export function getJudgeSchemaForPrompt(): object {
  return {
    type: "object",
    properties: {
      overall: { type: "number", minimum: 0, maximum: 5 },
      relevance: { type: "number", minimum: 0, maximum: 5 },
      diversity: { type: "number", minimum: 0, maximum: 5 },
      resultQuality: { type: "number", minimum: 0, maximum: 5 },
      navigability: { type: "number", minimum: 0, maximum: 5 },
      rationale: { type: "string" },
      issues: { type: "array", items: { type: "string" } },
      improvements: { type: "array", items: { type: "string" } },
      evidence: {
        type: "array",
        items: {
          type: "object",
          properties: {
            rank: { type: "number" },
            why: { type: "string" },
          },
          required: ["rank", "why"],
        },
      },
      schemaVersion: { type: "string" },
    },
    required: [
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
    ],
  };
}
