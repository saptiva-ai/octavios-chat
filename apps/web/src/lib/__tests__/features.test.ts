/**
 * Tests for features/feature flags utility functions
 */

import { getToolsFeatures, isFilesV1Enabled } from "../features";

// Mock global fetch
global.fetch = jest.fn();

describe("features", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    (global.fetch as jest.Mock).mockClear();
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe("getToolsFeatures", () => {
    it("should fetch features from API successfully", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: true },
          addFiles: { enabled: false },
          documentReview: { enabled: true },
          deepResearch: { enabled: false },
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const features = await getToolsFeatures();

      expect(features).toEqual(mockFeatures.tools);
      expect(global.fetch).toHaveBeenCalledWith("/api/features/tools", {
        cache: "no-store",
      });
    });

    it("should return defaults when API returns non-ok response", async () => {
      const consoleWarnSpy = jest.spyOn(console, "warn").mockImplementation();

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const features = await getToolsFeatures();

      expect(features).toHaveProperty("files");
      expect(features).toHaveProperty("addFiles");
      expect(features).toHaveProperty("documentReview");
      expect(features).toHaveProperty("deepResearch");
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        "Failed to fetch feature flags, using defaults",
      );

      consoleWarnSpy.mockRestore();
    });

    it("should return defaults when fetch throws error", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error("Network error"),
      );

      const features = await getToolsFeatures();

      expect(features).toHaveProperty("files");
      expect(features).toHaveProperty("deepResearch");
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "Error fetching feature flags:",
        expect.any(Error),
      );

      consoleErrorSpy.mockRestore();
    });

    it("should use default features from environment variables", async () => {
      process.env.NEXT_PUBLIC_TOOL_FILES = "true";
      process.env.NEXT_PUBLIC_TOOL_ADD_FILES = "false";
      process.env.NEXT_PUBLIC_TOOL_DOCUMENT_REVIEW = "true";

      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error("Fetch failed"),
      );

      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();
      const features = await getToolsFeatures();
      consoleErrorSpy.mockRestore();

      expect(features.files?.enabled).toBe(true);
      expect(features.addFiles?.enabled).toBe(false);
      expect(features.documentReview?.enabled).toBe(true);
      expect(features.deepResearch?.enabled).toBe(false); // Kill switch active by default
    });

    it("should handle missing tools property in API response", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}), // No tools property
      });

      const features = await getToolsFeatures();

      expect(features).toHaveProperty("files");
      expect(features).toHaveProperty("deepResearch");
    });

    it("should handle malformed API response", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => null,
      });

      const features = await getToolsFeatures();

      expect(features).toBeDefined();
      expect(features).toHaveProperty("deepResearch");
    });
  });

  describe("isFilesV1Enabled", () => {
    it("should return true when files feature is enabled", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: true },
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(true);
    });

    it("should return false when files feature is disabled", async () => {
      const mockFeatures = {
        tools: {
          files: { enabled: false },
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });

    it("should return false when files feature is missing", async () => {
      const mockFeatures = {
        tools: {},
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockFeatures,
      });

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);
    });

    it("should return false when API fails", async () => {
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("API error"));

      const isEnabled = await isFilesV1Enabled();

      expect(isEnabled).toBe(false);

      consoleErrorSpy.mockRestore();
    });
  });
});
