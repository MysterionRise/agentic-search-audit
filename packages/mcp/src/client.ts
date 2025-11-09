/**
 * MCP Client wrapper for chrome-devtools-mcp
 *
 * This provides high-level browser automation methods that interact with
 * the chrome-devtools-mcp server via the MCP SDK.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { DOMElement, ViewportSize, NavigationOptions, ScreenshotOptions } from "./types";

export class MCPBrowserClient {
  private client: Client;
  private transport: StdioClientTransport | null = null;
  private isConnected = false;

  constructor() {
    this.client = new Client(
      {
        name: "search-audit-mcp-client",
        version: "0.1.0",
      },
      {
        capabilities: {},
      }
    );
  }

  /**
   * Connect to the chrome-devtools-mcp server
   */
  async connect(command = "npx", args = ["chrome-devtools-mcp@latest"]): Promise<void> {
    if (this.isConnected) {
      return;
    }

    this.transport = new StdioClientTransport({
      command,
      args,
    });

    await this.client.connect(this.transport);
    this.isConnected = true;
  }

  /**
   * Disconnect from the MCP server
   */
  async disconnect(): Promise<void> {
    if (this.transport) {
      await this.client.close();
      this.isConnected = false;
      this.transport = null;
    }
  }

  /**
   * Navigate to a URL
   */
  async navigate(url: string, options: NavigationOptions = {}): Promise<void> {
    const result = await this.client.callTool({
      name: "navigate",
      arguments: {
        url,
        waitUntil: options.waitUntil || "networkidle",
      },
    });

    if (result.isError) {
      throw new Error(`Navigation failed: ${result.content}`);
    }
  }

  /**
   * Wait for network to be idle
   */
  async waitForNetworkIdle(ms = 1000): Promise<void> {
    await this.evaluate(`
      new Promise(resolve => {
        let timeout;
        const check = () => {
          clearTimeout(timeout);
          timeout = setTimeout(() => resolve(), ${ms});
        };
        // Listen for network requests
        const observer = new PerformanceObserver(() => check());
        observer.observe({ entryTypes: ['resource'] });
        check();
      })
    `);
  }

  /**
   * Query DOM elements by CSS selector
   */
  async queryAll(selector: string): Promise<DOMElement[]> {
    const result = await this.client.callTool({
      name: "query_selector_all",
      arguments: { selector },
    });

    if (result.isError) {
      return [];
    }

    // Parse the result
    const content = Array.isArray(result.content) ? result.content[0] : result.content;
    const text = typeof content === "object" && "text" in content ? content.text : "";

    try {
      return JSON.parse(text);
    } catch {
      return [];
    }
  }

  /**
   * Click on an element
   */
  async click(selector: string): Promise<void> {
    const result = await this.client.callTool({
      name: "click",
      arguments: { selector },
    });

    if (result.isError) {
      throw new Error(`Click failed: ${result.content}`);
    }
  }

  /**
   * Type text into an element
   */
  async type(selector: string, text: string, options?: { delay?: number }): Promise<void> {
    // First focus the element
    await this.click(selector);

    // Type character by character if delay is specified
    if (options?.delay) {
      for (const char of text) {
        await this.evaluate(`
          document.querySelector('${selector}').value += '${char}';
          document.querySelector('${selector}').dispatchEvent(new Event('input', { bubbles: true }));
        `);
        await new Promise((resolve) => setTimeout(resolve, options.delay));
      }
    } else {
      await this.evaluate(`
        const el = document.querySelector('${selector}');
        el.value = '${text}';
        el.dispatchEvent(new Event('input', { bubbles: true }));
      `);
    }
  }

  /**
   * Press a keyboard key
   */
  async press(key: string): Promise<void> {
    const result = await this.client.callTool({
      name: "keyboard_press",
      arguments: { key },
    });

    if (result.isError) {
      throw new Error(`Key press failed: ${result.content}`);
    }
  }

  /**
   * Take a screenshot
   */
  async screenshot(options: ScreenshotOptions): Promise<string> {
    const result = await this.client.callTool({
      name: "screenshot",
      arguments: {
        path: options.path,
        fullPage: options.fullPage ?? true,
        type: options.type || "png",
      },
    });

    if (result.isError) {
      throw new Error(`Screenshot failed: ${result.content}`);
    }

    return options.path;
  }

  /**
   * Get the full HTML of the page
   */
  async getHTML(): Promise<string> {
    const result = await this.evaluate("document.documentElement.outerHTML");
    return result;
  }

  /**
   * Set viewport size
   */
  async setViewport(size: ViewportSize): Promise<void> {
    const result = await this.client.callTool({
      name: "set_viewport",
      arguments: {
        width: size.width,
        height: size.height,
      },
    });

    if (result.isError) {
      throw new Error(`Set viewport failed: ${result.content}`);
    }
  }

  /**
   * Evaluate JavaScript in the page context
   */
  async evaluate(script: string): Promise<any> {
    const result = await this.client.callTool({
      name: "execute_javascript",
      arguments: { script },
    });

    if (result.isError) {
      throw new Error(`Script evaluation failed: ${result.content}`);
    }

    const content = Array.isArray(result.content) ? result.content[0] : result.content;
    const text = typeof content === "object" && "text" in content ? content.text : "";

    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  /**
   * Wait for a selector to appear
   */
  async waitForSelector(selector: string, timeout = 5000): Promise<boolean> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      const elements = await this.queryAll(selector);
      if (elements.length > 0) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    return false;
  }

  /**
   * Get the current URL
   */
  async getCurrentURL(): Promise<string> {
    return await this.evaluate("window.location.href");
  }
}
