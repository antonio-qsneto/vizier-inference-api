export const LOCAL_FILE_PROXY_PATH = "/__vizier/local-file";

export function normalizeViewerAssetUrl(assetUrl: string) {
  if (!assetUrl.startsWith("file://")) {
    return assetUrl;
  }

  const localPath = assetUrl.replace("file://", "");
  const encodedPath = encodeURIComponent(localPath);
  return `${LOCAL_FILE_PROXY_PATH}?path=${encodedPath}`;
}
