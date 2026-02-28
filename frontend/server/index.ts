import express from "express";
import { createServer } from "http";
import fs from "node:fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
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

async function startServer() {
  const app = express();
  const server = createServer(app);
  const allowedRoots = resolveAllowedLocalRoots(process.env.VITE_LOCAL_FILE_ROOTS);

  // Serve static files from dist/public in production
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  app.get(LOCAL_FILE_ROUTE, (req, res) => {
    const requestedPath = String(req.query.path ?? "");

    if (!requestedPath) {
      res.status(400).send("Missing file path");
      return;
    }

    if (!isAllowedLocalPath(requestedPath, allowedRoots)) {
      res.status(403).send("Path not allowed");
      return;
    }

    if (!fs.existsSync(requestedPath) || !fs.statSync(requestedPath).isFile()) {
      res.status(404).send("File not found");
      return;
    }

    res.type(contentTypeForFile(requestedPath));
    fs.createReadStream(requestedPath).pipe(res);
  });

  // Handle client-side routing - serve index.html for all routes
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
