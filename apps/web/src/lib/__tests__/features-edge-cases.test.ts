/**
 * Additional edge case tests for features.ts
 * Target: Increase branch coverage from 68.18% → 80%+
 */

import { getToolsFeatures, isFilesV1Enabled } from "../features";

// Mock global fetch
global.fetch = jest.fn();

describe("features - additional edge cases", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    (global.fetch as jest.Mock).mockClear();
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe("getToolsFeatures - comprehensive scenarios", () => {
    it("should handle all flags enabled from API", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: true },
          addFiles: { enabled: true },
          documentReview: { enabled: true },
          deepResearch: { enabled: true }, // This is important - test when enabled
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const features = await getToolsFeatures();

      expect(features.files?.enabled).toBe(true);
      expect(features.addFiles?.enabled).toBe(true);
      expect(features.documentReview?.enabled).toBe(true);
      expect(features.deepResearch?.enabled).toBe(true);
    });

    it("should handle partial tools object with some properties missing", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: true },
          // Missing: addFiles, documentReview, deepResearch
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const features = await getToolsFeatures();

      expect(features.files?.enabled).toBe(true);
      // Other properties should be undefined (not from defaults)
      expect(features.addFiles).toBeUndefined();
      expect(features.documentReview).toBeUndefined();
      expect(features.deepResearch).toBeUndefined();
    });

    it("should handle response.json() throwing error after ok=true", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new Error("JSON parse error");
        },
      });

      const features = await getToolsFeatures();

      // Should fallback to defaults
      expect(features).toHaveProperty("files");
      expect(features).toHaveProperty("deepResearch");
      expect(features.deepResearch?.enabled).toBe(false); // Default kill switch

      consoleErrorSpy.mockRestore();
    });

    it('should handle environment variables with non-"true" values', async () => {
      process.env.NEXT_PUBLIC_TOOL_FILES = "false";
      process.env.NEXT_PUBLIC_TOOL_ADD_FILES = ""; // Empty string
      process.env.NEXT_PUBLIC_TOOL_DOCUMENT_REVIEW = "yes"; // Not "true"
      // NEXT_PUBLIC_TOOL_DEEP_RESEARCH is undefined

      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error("Network error"),
      );

      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();
      const features = await getToolsFeatures();
      consoleErrorSpy.mockRestore();

      // Only exact string "true" should enable features
      expect(features.files?.enabled).toBe(false);
      expect(features.addFiles?.enabled).toBe(false);
      expect(features.documentReview?.enabled).toBe(false);
      expect(features.deepResearch?.enabled).toBe(false);
    });

    it("should handle 404 response from API", async () => {
      const consoleWarnSpy = jest.spyOn(console, "warn").mockImplementation();

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      const features = await getToolsFeatures();

      expect(features).toHaveProperty("deepResearch");
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        "Failed to fetch feature flags, using defaults",
      );

      consoleWarnSpy.mockRestore();
    });

    it("should handle 401 Unauthorized response from API", async () => {
      const consoleWarnSpy = jest.spyOn(console, "warn").mockImplementation();

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      const features = await getToolsFeatures();

      expect(features).toHaveProperty("files");
      expect(features.deepResearch?.enabled).toBe(false);

      consoleWarnSpy.mockRestore();
    });

    it("should handle response with null tools property", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ tools: null }),
      });

      const features = await getToolsFeatures();

      // Should fallback to defaults when tools is null
      expect(features).toHaveProperty("files");
      expect(features).toHaveProperty("deepResearch");
    });

    it("should handle response with tools as array instead of object", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ tools: [] }), // Malformed: array instead of object
      });

      const features = await getToolsFeatures();

      // Current implementation returns the array itself (documents actual behavior)
      // In production, this would be a malformed API response
      expect(Array.isArray(features)).toBe(true);
      expect(features).toEqual([]);
    });

    it("should handle environment variable override when deepResearch is true", async () => {
      process.env.NEXT_PUBLIC_TOOL_DEEP_RESEARCH = "true";

      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("API down"));

      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();
      const features = await getToolsFeatures();
      consoleErrorSpy.mockRestore();

      // Note: The current implementation doesn't have an env var for deepResearch
      // It always defaults to false. This test documents current behavior.
      expect(features.deepResearch?.enabled).toBe(false);
    });
  });

  describe("isFilesV1Enabled - additional edge cases", () => {
    it("should return false when files object exists but enabled property is missing", async () => {
      const mockFeatures = {
        tools: {
          files: {} as any, // Missing enabled property
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      // Should use nullish coalescing to return false
      expect(isEnabled).toBe(false);
    });

    it("should return false when files object is null", async () => {
      const mockFeatures = {
        tools: {
          files: null,
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });

    it("should return false when files.enabled is explicitly null", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: null },
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });

    it("should return false when files.enabled is undefined", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: undefined },
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });

    it("should return string value when files.enabled is a non-boolean truthy value", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: "true" as any }, // String instead of boolean
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      // Nullish coalescing returns the actual value (string 'true')
      // TypeScript types would catch this, but at runtime it returns the string
      expect(isEnabled).toBe("true" as any);
    });

    it("should return false when entire response is empty object", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });
  });

  describe("fetch error scenarios", () => {
    it("should handle fetch throwing TypeError (network offline)", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new TypeError("Failed to fetch"),
      );

      const features = await getToolsFeatures();

      expect(features).toBeDefined();
      expect(features.deepResearch?.enabled).toBe(false);

      consoleErrorSpy.mockRestore();
    });

    it("should handle fetch aborting (AbortError)", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      const abortError = new Error("The operation was aborted");
      abortError.name = "AbortError";

      (global.fetch as jest.Mock).mockRejectedValueOnce(abortError);

      const features = await getToolsFeatures();

      expect(features).toBeDefined();
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "Error fetching feature flags:",
        abortError,
      );

      consoleErrorSpy.mockRestore();
    });

    it("should handle fetch timeout", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      const timeoutError = new Error("Request timeout");
      timeoutError.name = "TimeoutError";

      (global.fetch as jest.Mock).mockRejectedValueOnce(timeoutError);

      const features = await getToolsFeatures();

      expect(features).toBeDefined();
      expect(features).toHaveProperty("files");

      consoleErrorSpy.mockRestore();
    });
  });
});
