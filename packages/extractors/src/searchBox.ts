/**
 * Search box finder with fallback strategies
 */

import { MCPBrowserClient, DOMElement } from "@search-audit/mcp";

export type SearchConfig = {
  inputSelectors: string[];
  submitStrategy: "enter" | "clickSelector";
  submitSelector?: string;
};

/**
 * Find the search input box on the page
 */
export async function findSearchBox(
  client: MCPBrowserClient,
  config: SearchConfig
): Promise<string | null> {
  // Try configured selectors first
  for (const selector of config.inputSelectors) {
    const elements = await client.queryAll(selector);
    if (elements.length > 0) {
      // Return the first visible element
      for (const el of elements) {
        if (isLikelyVisible(el)) {
          return buildSelector(el);
        }
      }
    }
  }

  // Fallback: look for any input that might be a search box
  const fallbackSelectors = [
    'input[type="search"]',
    'input[role="search"]',
    'input[aria-label*="search" i]',
    'input[placeholder*="search" i]',
    'input[name*="search" i]',
    'input[id*="search" i]',
    '[role="search"] input',
  ];

  for (const selector of fallbackSelectors) {
    const elements = await client.queryAll(selector);
    if (elements.length > 0) {
      for (const el of elements) {
        if (isLikelyVisible(el)) {
          return buildSelector(el);
        }
      }
    }
  }

  return null;
}

/**
 * Submit a search query
 */
export async function submitSearch(
  client: MCPBrowserClient,
  searchBoxSelector: string,
  query: string,
  config: SearchConfig
): Promise<void> {
  // Type the query
  await client.type(searchBoxSelector, query);

  // Wait a bit for any autocomplete to appear
  await new Promise((resolve) => setTimeout(resolve, 300));

  // Submit based on strategy
  if (config.submitStrategy === "enter") {
    await client.press("Enter");
  } else if (config.submitStrategy === "clickSelector" && config.submitSelector) {
    await client.click(config.submitSelector);
  } else {
    // Fallback: press Enter
    await client.press("Enter");
  }
}

function isLikelyVisible(element: DOMElement): boolean {
  const style = element.attributes.style || "";
  const className = element.attributes.class || "";

  // Check for common hidden patterns
  if (
    style.includes("display: none") ||
    style.includes("display:none") ||
    style.includes("visibility: hidden") ||
    style.includes("visibility:hidden") ||
    className.includes("hidden") ||
    className.includes("invisible")
  ) {
    return false;
  }

  return true;
}

function buildSelector(element: DOMElement): string {
  if (element.attributes.id) {
    return `#${element.attributes.id}`;
  }

  if (element.attributes.name) {
    return `input[name="${element.attributes.name}"]`;
  }

  if (element.attributes.class) {
    const classes = element.attributes.class.split(" ").filter(Boolean).slice(0, 2);
    if (classes.length > 0) {
      return `input.${classes.join(".")}`;
    }
  }

  return element.tagName.toLowerCase();
}
