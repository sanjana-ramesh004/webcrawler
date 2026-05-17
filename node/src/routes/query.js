// src/routes/query.js
/**
 * POST /api/query        — RAG answer
 * POST /api/query/stream — SSE stream
 */
import { Router } from "express";
import { callPython, proxyStream } from "../services/pythonApi.js";

const router = Router();

function validate(req, res, next) {
  const { question, thread_id } = req.body;

  if (!question || typeof question !== "string" || !question.trim()) {
    return res.status(400).json({ error: "`question` is required and must be a non-empty string." });
  }
  if (!thread_id || typeof thread_id !== "string" || !thread_id.trim()) {
    return res.status(400).json({ error: "`thread_id` is required." });
  }

  next();
}

// Standard query
router.post("/", validate, async (req, res) => {
  const { question, image_url, thread_id } = req.body;

  const result = await callPython("/api/query", {
    method: "POST",
    body: {
      question: question.trim(),
      image_url: image_url || null,
      thread_id: thread_id.trim(),
    },
  });

  res.json(result);
});

// SSE streaming query
router.post("/stream", validate, async (req, res) => {
  const { question, image_url, thread_id } = req.body;

  await proxyStream(
    "/api/query/stream",
    {
      question: question.trim(),
      image_url: image_url || null,
      thread_id: thread_id.trim(),
    },
    res,
  );
});

export default router;