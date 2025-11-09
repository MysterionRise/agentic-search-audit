/**
 * MCP Client types
 */

export type DOMElement = {
  handleId?: string;
  outerHTML: string;
  innerText: string;
  attributes: Record<string, string>;
  tagName: string;
};

export type ViewportSize = {
  width: number;
  height: number;
};

export type NavigationOptions = {
  waitUntil?: "load" | "domcontentloaded" | "networkidle";
  timeout?: number;
};

export type ScreenshotOptions = {
  path: string;
  fullPage?: boolean;
  type?: "png" | "jpeg";
};
