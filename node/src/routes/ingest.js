// src/routes/ingest.js
/**
 * POST /api/ingest/file  — upload a document
 * POST /api/ingest/crawl — crawl a website
 */
import { Router } from "express";
import multer from "multer";
import fetch from "node-fetch";
import FormData from "form-data";

const router = Router();

const MAX_MB = Number(process.env.MAX_UPLOAD_SIZE_MB) || 50;
const ALLOWED_EXTS = new Set([".pdf", ".docx", ".txt", ".md"]);

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_MB * 1024 * 1024 },
  fileFilter(_req, file, cb) {
    const ext = "." + (file.originalname.split(".").pop() || "").toLowerCase();
    if (ALLOWED_EXTS.has(ext)) return cb(null, true);
    cb(new Error(`Unsupported file type. Allowed: ${[...ALLOWED_EXTS].join(", ")}`));
  },
});

// File upload
router.post("/file", upload.single("file"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded. Use field name `file`." });
  }

  const { originalname, buffer, mimetype } = req.file;

  const form = new FormData();
  form.append("file", buffer, { filename: originalname, contentType: mimetype });

  const pythonUrl = `${process.env.PYTHON_API_URL || "http://localhost:8000"}/api/ingest/file`;
  const pythonRes = await fetch(pythonUrl, { method: "POST", body: form });
  const data = await pythonRes.json();

  if (!pythonRes.ok) {
    return res.status(pythonRes.status).json({ error: data.detail || "Ingestion failed." });
  }

  res.json(data);
});

// Crawl
router.post("/crawl", async (req, res) => {
  const { url, max_depth = 2, max_pages = 30 } = req.body;

  if (!url || typeof url !== "string") {
    return res.status(400).json({ error: "`url` is required." });
  }

  // Validate URL format
  try {
    new URL(url);
  } catch {
    return res.status(400).json({ error: "Invalid URL format." });
  }

  // SSRF guard
  const parsed = new URL(url);
  const blocked = ["localhost", "127.0.0.1", "0.0.0.0", "::1"];
  if (blocked.some((b) => parsed.hostname.includes(b))) {
    return res.status(403).json({ error: "Crawling local addresses is not allowed." });
  }

  const pythonUrl = `${process.env.PYTHON_API_URL || "http://localhost:8000"}/api/ingest/crawl`;
  const pythonRes = await fetch(pythonUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      max_depth: Math.min(Number(max_depth), 4),
      max_pages: Math.min(Number(max_pages), 100),
    }),
  });

  const data = await pythonRes.json();

  if (!pythonRes.ok) {
    return res.status(pythonRes.status).json({ error: data.detail || "Crawl failed." });
  }

  res.json(data);
});

// Multer error handler
router.use((err, _req, res, _next) => {
  if (err.code === "LIMIT_FILE_SIZE") {
    return res.status(413).json({ error: `File too large. Max: ${MAX_MB}MB` });
  }
  res.status(400).json({ error: err.message });
});

export default router;