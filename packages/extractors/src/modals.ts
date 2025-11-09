/**
 * Modal handler for dismissing consent/cookie banners and popups
 */

import { MCPBrowserClient, DOMElement } from "@search-audit/mcp";

export type ModalsConfig = {
  closeTextMatches: string[];
  maxAutoClicks: number;
};

/**
 * Attempt to dismiss common modals (cookie consent, region selection, etc.)
 */
export async function dismissModals(
  client: MCPBrowserClient,
  config: ModalsConfig
): Promise<number> {
  let clickCount = 0;

  for (let i = 0; i < config.maxAutoClicks; i++) {
    const dismissed = await tryDismissModal(client, config.closeTextMatches);
    if (!dismissed) {
      break;
    }
    clickCount++;
    // Wait a bit for any animations
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  return clickCount;
}

async function tryDismissModal(
  client: MCPBrowserClient,
  closeTextMatches: string[]
): Promise<boolean> {
  // Look for buttons and links that might close modals
  const selectors = [
    "button",
    'a[role="button"]',
    '[role="button"]',
    ".button",
    ".btn",
    '[class*="close"]',
    '[class*="dismiss"]',
    '[class*="accept"]',
  ];

  for (const selector of selectors) {
    const elements = await client.queryAll(selector);

    for (const element of elements) {
      const text = element.innerText.toLowerCase().trim();
      const ariaLabel = element.attributes["aria-label"]?.toLowerCase() || "";

      // Check if the text matches any of our close patterns
      for (const pattern of closeTextMatches) {
        if (text.includes(pattern.toLowerCase()) || ariaLabel.includes(pattern.toLowerCase())) {
          // Try to click this element
          try {
            // Find a unique selector for this element
            const uniqueSelector = findUniqueSelector(element, elements);
            if (uniqueSelector) {
              await client.click(uniqueSelector);
              return true;
            }
          } catch (error) {
            // Continue trying other elements
            continue;
          }
        }
      }
    }
  }

  return false;
}

function findUniqueSelector(target: DOMElement, allElements: DOMElement[]): string | null {
  // Try to find a unique selector based on ID
  if (target.attributes.id) {
    return `#${target.attributes.id}`;
  }

  // Try to find a unique selector based on class + text content
  if (target.attributes.class) {
    const classes = target.attributes.class.split(" ").filter(Boolean);
    if (classes.length > 0) {
      const selector = `${target.tagName}.${classes.join(".")}`;
      // Check if this is unique enough
      const matches = allElements.filter((el) => {
        const elClasses = el.attributes.class?.split(" ").filter(Boolean) || [];
        return (
          el.tagName === target.tagName &&
          classes.every((c) => elClasses.includes(c)) &&
          el.innerText === target.innerText
        );
      });

      if (matches.length === 1) {
        return selector;
      }
    }
  }

  // Fallback: use tag name and exact text match
  const escapedText = target.innerText.replace(/'/g, "\\'");
  return `${target.tagName.toLowerCase()}:has-text("${escapedText.substring(0, 30)}")`;
}
