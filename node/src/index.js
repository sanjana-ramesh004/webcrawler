// src/index.js
import "express-async-errors";
import express from "express";
import cors from "cors";
import morgan from "morgan";
import { config } from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join, resolve } from "path";
import { existsSync } from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = dirname(__filename);

config({ path: join(__dirname, "../.env") });

import { rateLimiter }   from "./middleware/rateLimiter.js";
import { errorHandler }  from "./middleware/errorHandler.js";
import { requestLogger } from "./middleware/requestLogger.js";
import queryRouter   from "./routes/query.js";
import searchRouter  from "./routes/search.js";
import sessionRouter from "./routes/session.js";
import proxyRouter   from "./routes/proxy.js";

const app  = express();
const PORT = process.env.PORT || 3000;

// ── Locate frontend ────────────────────────────────────────────────────────────
const possiblePaths = [
  join(__dirname, "../../frontend"),
  join(__dirname, "../frontend"),
  resolve("frontend"),
];
let frontendPath = null;
for (const p of possiblePaths) {
  if (existsSync(join(p, "index.html"))) { frontendPath = p; break; }
}
if (frontendPath) {
  console.log(`📁 Serving frontend from: ${frontendPath}`);
  app.use(express.static(frontendPath));
} else {
  console.warn("⚠️  Frontend not found. Checked:", possiblePaths);
}

// ── Global middleware ──────────────────────────────────────────────────────────
app.use(cors({ origin: "*", methods: ["GET", "POST", "DELETE"] }));
app.use(morgan("dev"));
app.use(express.json({ limit: "20mb" }));   // 20mb for base64 images
app.use(requestLogger);
app.use(rateLimiter);

// ── Routes ─────────────────────────────────────────────────────────────────────
app.use("/api/query",   queryRouter);
app.use("/api/search",  searchRouter);
app.use("/api/session", sessionRouter);
app.use("/api",         proxyRouter);

// ── Health ─────────────────────────────────────────────────────────────────────
app.get("/health", async (_req, res) => {
  try {
    const r = await fetch(`${process.env.PYTHON_API_URL || "http://localhost:8000"}/health`);
    const d = await r.json();
    res.json({ status: "ok", service: "air-bff", model: d.model });
  } catch {
    res.json({ status: "ok", service: "air-bff", model: "unknown" });
  }
});

// ── Fallback ───────────────────────────────────────────────────────────────────
app.get("*", (req, res) => {
  if (req.path.startsWith("/api")) return res.status(404).json({ error: "Not found" });
  if (frontendPath) res.sendFile(join(frontendPath, "index.html"));
  else res.status(404).send("Frontend not found.");
});

app.use(errorHandler);

app.listen(PORT, () => {
  console.log(`\n🚀 BFF running at http://localhost:${PORT}`);
  console.log(`   Frontend  → http://localhost:${PORT}`);
  console.log(`   Proxying  → ${process.env.PYTHON_API_URL}\n`);
});