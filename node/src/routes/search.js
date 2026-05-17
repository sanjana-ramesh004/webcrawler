// src/routes/search.js
/**
 * POST /api/search
 * Body: { url, query, image_b64? }
 * Proxies to FastAPI /api/search
 */
import { Router } from "express";
import { callPython } from "../services/pythonApi.js";

const router = Router();

router.post("/", async (req, res) => {
  const { url, query, image_b64 } = req.body;

  if (!url || typeof url !== "string") {
    return res.status(400).json({ error: "`url` is required." });
  }
  if (!query || typeof query !== "string") {
    return res.status(400).json({ error: "`query` is required." });
  }

  // Validate URL
  try { new URL(url); } catch {
    return res.status(400).json({ error: "Invalid URL format." });
  }

  const result = await callPython("/api/search", {
    method: "POST",
    body: {
      url:       url.trim(),
      query:     query.trim(),
      image_b64: image_b64 || null,
    },
  });

  res.json(result);
});

export default router;