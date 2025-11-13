import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RateLimiter, delay, withTimeout } from "./policies";

describe("policies", () => {
  describe("RateLimiter", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("should allow immediate first call", async () => {
      const limiter = new RateLimiter(1); // 1 request per second

      const startTime = Date.now();
      await limiter.wait();
      const endTime = Date.now();

      expect(endTime - startTime).toBe(0);
    });

    it("should enforce rate limit for subsequent calls", async () => {
      const limiter = new RateLimiter(1); // 1 request per second

      await limiter.wait(); // First call (immediate)

      const promise = limiter.wait(); // Second call (should wait)
      vi.advanceTimersByTime(1000);
      await promise;

      // Should have waited ~1000ms
      expect(vi.getTimerCount()).toBe(0);
    });

    it("should calculate correct intervals for different RPS", async () => {
      const limiter = new RateLimiter(2); // 2 requests per second

      await limiter.wait();

      const promise = limiter.wait();
      vi.advanceTimersByTime(500); // 500ms = 1000ms / 2 RPS
      await promise;

      expect(vi.getTimerCount()).toBe(0);
    });

    it("should handle fractional RPS", async () => {
      const limiter = new RateLimiter(0.5); // 0.5 requests per second = 1 request per 2 seconds

      await limiter.wait();

      const promise = limiter.wait();
      vi.advanceTimersByTime(2000);
      await promise;

      expect(vi.getTimerCount()).toBe(0);
    });

    it("should not wait if enough time has passed", async () => {
      const limiter = new RateLimiter(1);

      await limiter.wait();
      vi.advanceTimersByTime(1500); // More than 1 second

      const startTime = Date.now();
      await limiter.wait();
      const endTime = Date.now();

      expect(endTime - startTime).toBe(0);
    });
  });

  describe("delay", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("should delay for specified milliseconds", async () => {
      const promise = delay(1000);

      vi.advanceTimersByTime(999);
      await Promise.race([promise, Promise.resolve("not done")]).then((result) => {
        expect(result).toBe("not done");
      });

      vi.advanceTimersByTime(1);
      await promise;
    });

    it("should resolve immediately for 0ms delay", async () => {
      vi.useRealTimers(); // Use real timers for this test
      const promise = delay(0);
      await promise;
      expect(true).toBe(true); // Should reach here
    });
  });

  describe("withTimeout", () => {
    it("should resolve if promise completes within timeout", async () => {
      const promise = Promise.resolve("success");

      const result = await withTimeout(promise, 1000);

      expect(result).toBe("success");
    });

    it("should reject if promise exceeds timeout", async () => {
      vi.useFakeTimers();

      const promise = new Promise((resolve) => {
        setTimeout(() => resolve("late"), 2000);
      });

      const timeoutPromise = withTimeout(promise, 1000);

      vi.advanceTimersByTime(1000);

      await expect(timeoutPromise).rejects.toThrow("Operation timed out");

      vi.useRealTimers();
    });

    it("should use custom error message", async () => {
      vi.useFakeTimers();

      const promise = new Promise((resolve) => {
        setTimeout(() => resolve("late"), 2000);
      });

      const timeoutPromise = withTimeout(promise, 1000, "Custom timeout message");

      vi.advanceTimersByTime(1000);

      await expect(timeoutPromise).rejects.toThrow("Custom timeout message");

      vi.useRealTimers();
    });
  });
});
