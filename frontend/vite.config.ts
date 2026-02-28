import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "path";
import type { Plugin } from "vite";
import { defineConfig, loadEnv } from "vite";

const LOCAL_FILE_ROUTE = "/__vizier/local-file";
const DEFAULT_LOCAL_ROOTS = ["/tmp/vizier-med", "/tmp/vizier-analysis"];

function resolveAllowedLocalRoots(value: string | undefined) {
  if (!value) {
    return DEFAULT_LOCAL_ROOTS;
  }

  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isAllowedLocalPath(candidate: string, allowedRoots: string[]) {
  const resolvedPath = path.resolve(candidate);
  return allowedRoots.some((root) => {
    const resolvedRoot = path.resolve(root);
    return (
      resolvedPath === resolvedRoot ||
      resolvedPath.startsWith(`${resolvedRoot}${path.sep}`)
    );
  });
}

function contentTypeForFile(filePath: string) {
  if (filePath.endsWith(".nii.gz") || filePath.endsWith(".gz")) {
    return "application/gzip";
  }
  if (filePath.endsWith(".nii")) {
    return "application/octet-stream";
  }
  return "application/octet-stream";
}

function localFileProxyPlugin(allowedRoots: string[]): Plugin {
  return {
    name: "vizier-local-file-proxy",
    configureServer(server) {
      server.middlewares.use(LOCAL_FILE_ROUTE, (req, res) => {
        const requestUrl = new URL(req.url ?? "", "http://localhost");
        const requestedPath = requestUrl.searchParams.get("path");

        if (!requestedPath) {
          res.statusCode = 400;
          res.end("Missing file path");
          return;
        }

        if (!isAllowedLocalPath(requestedPath, allowedRoots)) {
          res.statusCode = 403;
          res.end("Path not allowed");
          return;
        }

        if (!fs.existsSync(requestedPath) || !fs.statSync(requestedPath).isFile()) {
          res.statusCode = 404;
          res.end("File not found");
          return;
        }

        res.setHeader("Content-Type", contentTypeForFile(requestedPath));
        fs.createReadStream(requestedPath).pipe(res);
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(import.meta.dirname), "");
  const allowedRoots = resolveAllowedLocalRoots(env.VITE_LOCAL_FILE_ROOTS);

  return {
    plugins: [react(), tailwindcss(), localFileProxyPlugin(allowedRoots)],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "client", "src"),
        "@shared": path.resolve(import.meta.dirname, "shared"),
      },
    },
    envDir: path.resolve(import.meta.dirname),
    root: path.resolve(import.meta.dirname, "client"),
    build: {
      outDir: path.resolve(import.meta.dirname, "dist/public"),
      emptyOutDir: true,
    },
    server: {
      port: 3000,
      strictPort: false,
      host: true,
      fs: {
        strict: true,
        deny: ["**/.*"],
      },
    },
  };
});
