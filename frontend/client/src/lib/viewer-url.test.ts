import { describe, expect, it } from "vitest";
import { normalizeViewerAssetUrl } from "@/lib/viewer-url";

describe("normalizeViewerAssetUrl", () => {
  it("keeps http urls untouched", () => {
    expect(normalizeViewerAssetUrl("https://signed.example.com/image.nii.gz")).toBe(
      "https://signed.example.com/image.nii.gz",
    );
  });

  it("rewrites local file urls to frontend proxy endpoint", () => {
    expect(
      normalizeViewerAssetUrl("file:///tmp/vizier-med/results/demo/image.nii.gz"),
    ).toContain("/__vizier/local-file?path=%2Ftmp%2Fvizier-med%2Fresults%2Fdemo%2Fimage.nii.gz");
  });
});
