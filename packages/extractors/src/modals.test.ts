import { describe, it, expect, vi, beforeEach } from "vitest";
import { dismissModals, ModalsConfig } from "./modals";
import { MCPBrowserClient } from "@search-audit/mcp";

describe("modals", () => {
  let mockClient: MCPBrowserClient;
  let config: ModalsConfig;

  beforeEach(() => {
    mockClient = {
      queryAll: vi.fn(),
      click: vi.fn(),
    } as any;

    config = {
      closeTextMatches: ["accept", "close", "ok"],
      maxAutoClicks: 3,
    };
  });

  describe("dismissModals", () => {
    it("should find and click modal close buttons", async () => {
      const mockButton = {
        tagName: "button",
        outerHTML: "<button>Accept</button>",
        innerText: "Accept",
        attributes: { id: "accept-btn" },
      };

      mockClient.queryAll.mockResolvedValueOnce([mockButton] as any).mockResolvedValue([]);

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(1);
      expect(mockClient.click).toHaveBeenCalledTimes(1);
    });

    it("should respect maxAutoClicks limit", async () => {
      const mockButton = {
        tagName: "button",
        outerHTML: "<button>Accept</button>",
        innerText: "Accept",
        attributes: { id: "accept-btn" },
      };

      // Always return a button to click
      mockClient.queryAll.mockResolvedValue([mockButton] as any);

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(3); // maxAutoClicks
      expect(mockClient.click).toHaveBeenCalledTimes(3);
    });

    it("should match case-insensitive text", async () => {
      const mockButtons = [
        {
          tagName: "button",
          outerHTML: "<button>ACCEPT</button>",
          innerText: "ACCEPT",
          attributes: { id: "btn1" },
        },
        {
          tagName: "button",
          outerHTML: "<button>Close</button>",
          innerText: "Close",
          attributes: { id: "btn2" },
        },
      ];

      mockClient.queryAll
        .mockResolvedValueOnce([mockButtons[0]] as any)
        .mockResolvedValueOnce([mockButtons[1]] as any)
        .mockResolvedValue([]);

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(2);
    });

    it("should check aria-label for close text", async () => {
      const mockButton = {
        tagName: "button",
        outerHTML: '<button aria-label="Close dialog">X</button>',
        innerText: "X",
        attributes: { "aria-label": "Close dialog" },
      };

      mockClient.queryAll.mockResolvedValueOnce([mockButton] as any).mockResolvedValue([]);

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(1);
    });

    it("should return 0 if no modals found", async () => {
      mockClient.queryAll.mockResolvedValue([]);

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(0);
      expect(mockClient.click).not.toHaveBeenCalled();
    });

    it("should stop early if no more modals found", async () => {
      const mockButton = {
        tagName: "button",
        outerHTML: "<button>Accept</button>",
        innerText: "Accept",
        attributes: { id: "accept-btn" },
      };

      mockClient.queryAll.mockResolvedValueOnce([mockButton] as any).mockResolvedValue([]); // No more modals

      const clickCount = await dismissModals(mockClient, config);

      expect(clickCount).toBe(1);
      expect(mockClient.click).toHaveBeenCalledTimes(1);
    });
  });
});
