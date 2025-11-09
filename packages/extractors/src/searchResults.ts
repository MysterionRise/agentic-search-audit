/**
 * Search results extractor
 */

import { MCPBrowserClient, DOMElement } from "@search-audit/mcp";

export type ResultsConfig = {
  itemSelectors: string[];
  titleSelectors: string[];
  urlAttr: string;
  snippetSelectors: string[];
};

export type ResultItem = {
  rank: number;
  title?: string;
  url?: string;
  snippet?: string;
  price?: string;
  image?: string;
  attributes?: Record<string, string>;
};

/**
 * Extract top K search results from the page
 */
export async function extractResults(
  client: MCPBrowserClient,
  config: ResultsConfig,
  topK: number
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];

  // Try each item selector until we find results
  for (const itemSelector of config.itemSelectors) {
    const items = await client.queryAll(itemSelector);

    if (items.length === 0) {
      continue;
    }

    // Extract data from each item
    for (let i = 0; i < Math.min(items.length, topK); i++) {
      const item = items[i];
      const result = await extractResultItem(client, item, config, i + 1);
      if (result) {
        results.push(result);
      }
    }

    // If we got enough results, stop trying other selectors
    if (results.length >= topK) {
      break;
    }
  }

  return results.slice(0, topK);
}

async function extractResultItem(
  client: MCPBrowserClient,
  element: DOMElement,
  config: ResultsConfig,
  rank: number
): Promise<ResultItem | null> {
  const result: ResultItem = { rank };

  // Extract title
  const title = extractTextFromSelectors(element, config.titleSelectors);
  if (title) {
    result.title = title;
  }

  // Extract URL
  const url = extractUrl(element, config.urlAttr);
  if (url) {
    result.url = normalizeUrl(url);
  }

  // Extract snippet
  const snippet = extractTextFromSelectors(element, config.snippetSelectors);
  if (snippet) {
    result.snippet = snippet;
  }

  // Try to extract price (common in e-commerce)
  const price = extractPrice(element);
  if (price) {
    result.price = price;
  }

  // Try to extract image
  const image = extractImage(element);
  if (image) {
    result.image = image;
  }

  // Only return if we have at least a title or URL
  if (result.title || result.url) {
    return result;
  }

  return null;
}

function extractTextFromSelectors(element: DOMElement, selectors: string[]): string | null {
  // First try to parse the element's HTML to find child elements
  const html = element.outerHTML;

  for (const selector of selectors) {
    // Simple selector matching in the HTML
    const tagMatch = selector.match(/^([a-z0-9]+)/i);
    if (tagMatch) {
      const tag = tagMatch[1];
      const regex = new RegExp(`<${tag}[^>]*>([^<]+)</${tag}>`, "i");
      const match = html.match(regex);
      if (match && match[1]) {
        return match[1].trim();
      }
    }

    // Try class selectors
    const classMatch = selector.match(/\.([a-z0-9_-]+)/i);
    if (classMatch) {
      const className = classMatch[1];
      const regex = new RegExp(`class="[^"]*${className}[^"]*"[^>]*>([^<]+)<`, "i");
      const match = html.match(regex);
      if (match && match[1]) {
        return match[1].trim();
      }
    }
  }

  // Fallback: use the element's text content
  if (element.innerText && element.innerText.trim()) {
    return element.innerText.trim().substring(0, 200);
  }

  return null;
}

function extractUrl(element: DOMElement, urlAttr: string): string | null {
  // Check if the element itself has the URL attribute
  if (element.attributes[urlAttr]) {
    return element.attributes[urlAttr];
  }

  // Look for an anchor tag in the HTML
  const html = element.outerHTML;
  const hrefMatch = html.match(/href="([^"]+)"/);
  if (hrefMatch && hrefMatch[1]) {
    return hrefMatch[1];
  }

  return null;
}

function normalizeUrl(url: string): string {
  // Remove tracking parameters
  try {
    const urlObj = new URL(url, "https://example.com");
    // Remove common tracking params
    const trackingParams = ["utm_source", "utm_medium", "utm_campaign", "ref", "source"];
    trackingParams.forEach((param) => urlObj.searchParams.delete(param));
    return urlObj.toString();
  } catch {
    // If URL parsing fails, return as-is
    return url;
  }
}

function extractPrice(element: DOMElement): string | null {
  const html = element.outerHTML;
  const text = element.innerText;

  // Look for price patterns
  const pricePatterns = [
    /\$\s*(\d+(?:[.,]\d{2})?)/,
    /(\d+(?:[.,]\d{2})?)\s*USD/,
    /price[^>]*>([^<]+)</i,
  ];

  for (const pattern of pricePatterns) {
    const match = (html + text).match(pattern);
    if (match && match[1]) {
      return match[1];
    }
  }

  return null;
}

function extractImage(element: DOMElement): string | null {
  const html = element.outerHTML;

  // Look for img tags
  const imgMatch = html.match(/<img[^>]+src="([^"]+)"/i);
  if (imgMatch && imgMatch[1]) {
    return imgMatch[1];
  }

  return null;
}
