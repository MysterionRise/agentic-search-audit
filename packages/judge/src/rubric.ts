/**
 * LLM judge rubric and prompt construction
 */

import { getJudgeSchemaForPrompt } from "./schema";

export type JudgeInput = {
  site: string;
  query: string;
  results: Array<{
    rank: number;
    title?: string;
    url?: string;
    snippet?: string;
    price?: string;
  }>;
  pageSnapshot?: string; // Truncated HTML/text for context
};

/**
 * Build the system prompt for the LLM judge
 */
export function buildSystemPrompt(customPrompt?: string): string {
  if (customPrompt) {
    return customPrompt;
  }

  return `You are a careful search quality judge evaluating on-site search results.

Your task is to assess the quality of search results for a specific query on a website.

You will receive:
- The query text
- Top-K search results (rank, title, URL, snippet, price if available)
- A page snapshot (truncated HTML/text) for additional context

Evaluate the results on these dimensions (0-5 scale):

1. **Relevance** (0-5): How well do results match the search intent?
   - 5: Perfect matches, highly relevant
   - 3: Partially relevant, some mismatches
   - 0: Completely irrelevant

2. **Diversity** (0-5): Variety in brands, categories, price points
   - 5: Excellent variety
   - 3: Some variety but limited
   - 0: All results are very similar or duplicate

3. **Result Quality** (0-5): Clarity, no duplication, valid links
   - 5: Clean, clear, no issues
   - 3: Some clarity issues or minor problems
   - 0: Many broken links, duplicates, or unclear results

4. **Navigability** (0-5): Presence of filters, sorting, navigation aids
   - 5: Excellent filtering and navigation options
   - 3: Basic filtering available
   - 0: No filters or navigation aids

5. **Overall** (0-5): User satisfaction (NOT an average of other scores)
   - Consider: Would a user find what they're looking for?
   - Penalize heavily if results are mostly ads or dead ends

Important guidelines:
- Base judgments ONLY on the provided results and snapshot
- Do not use external knowledge about products or sites
- Cite specific results by rank number in your evidence
- If results appear to be ads or low quality, penalize accordingly
- Output ONLY valid JSON matching the schema - no extra text

The schema version should be "1.0".`;
}

/**
 * Build the user prompt with the actual query and results
 */
export function buildUserPrompt(input: JudgeInput): string {
  const resultsText = input.results
    .map((r) => {
      const parts = [`Rank ${r.rank}`];
      if (r.title) parts.push(`Title: ${r.title}`);
      if (r.url) parts.push(`URL: ${r.url}`);
      if (r.snippet) parts.push(`Snippet: ${r.snippet}`);
      if (r.price) parts.push(`Price: ${r.price}`);
      return parts.join("\n");
    })
    .join("\n\n");

  const schema = JSON.stringify(getJudgeSchemaForPrompt(), null, 2);

  return `Site: ${input.site}
Query: "${input.query}"

Search Results:
${resultsText}

${input.pageSnapshot ? `Page Context (truncated):\n${input.pageSnapshot.substring(0, 1000)}\n\n` : ""}

Please evaluate these search results and output ONLY a JSON object matching this schema:

${schema}

Remember:
- Use the evidence array to cite specific results
- Be strict but fair
- Output only the JSON object, nothing else`;
}
