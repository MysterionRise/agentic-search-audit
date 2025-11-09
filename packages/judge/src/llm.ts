/**
 * LLM client abstraction with OpenAI implementation
 */

import OpenAI from "openai";
import { JudgeScore, JudgeScoreSchema } from "./schema";
import { buildSystemPrompt, buildUserPrompt, JudgeInput } from "./rubric";

export type LLMConfig = {
  provider: "openai" | "anthropic" | "openrouter";
  model: string;
  maxTokens: number;
  temperature: number;
  apiKey?: string;
  systemPrompt?: string;
  seed?: number;
};

export interface LLMClient {
  evaluate(input: JudgeInput): Promise<JudgeScore>;
}

/**
 * OpenAI implementation of LLM judge
 */
export class OpenAIJudge implements LLMClient {
  private client: OpenAI;
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
    this.client = new OpenAI({
      apiKey: config.apiKey || process.env.OPENAI_API_KEY,
    });
  }

  async evaluate(input: JudgeInput): Promise<JudgeScore> {
    const systemPrompt = buildSystemPrompt(this.config.systemPrompt);
    const userPrompt = buildUserPrompt(input);

    // Try up to 2 times to get valid JSON
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const response = await this.client.chat.completions.create({
          model: this.config.model,
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userPrompt },
          ],
          max_tokens: this.config.maxTokens,
          temperature: this.config.temperature,
          seed: this.config.seed,
          response_format: { type: "json_object" },
        });

        const content = response.choices[0]?.message?.content;
        if (!content) {
          throw new Error("Empty response from LLM");
        }

        // Parse and validate JSON
        const parsed = JSON.parse(content);
        const validated = JudgeScoreSchema.parse(parsed);

        return validated;
      } catch (error) {
        if (attempt === 1) {
          // Last attempt failed
          throw new Error(`Failed to get valid judge response: ${error}`);
        }
        // Continue to retry
        console.warn(`Judge attempt ${attempt + 1} failed, retrying...`, error);
      }
    }

    throw new Error("Failed to get valid judge response after retries");
  }
}

/**
 * Factory function to create the appropriate LLM client
 */
export function createLLMClient(config: LLMConfig): LLMClient {
  switch (config.provider) {
    case "openai":
      return new OpenAIJudge(config);
    case "anthropic":
      throw new Error("Anthropic provider not yet implemented (P1)");
    case "openrouter":
      throw new Error("OpenRouter provider not yet implemented (P1)");
    default:
      throw new Error(`Unknown LLM provider: ${config.provider}`);
  }
}
