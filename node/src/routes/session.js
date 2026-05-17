// src/routes/session.js
/**
 * GET    /api/session/:thread_id — fetch chat history
 * DELETE /api/session/:thread_id — clear chat history
 */
import { Router } from "express";
import { callPython } from "../services/pythonApi.js";

const router = Router();

router.get("/:thread_id", async (req, res) => {
  const { thread_id } = req.params;
  const data = await callPython(`/api/session/${encodeURIComponent(thread_id)}`);
  res.json(data);
});

router.delete("/:thread_id", async (req, res) => {
  const { thread_id } = req.params;
  const data = await callPython(`/api/session/${encodeURIComponent(thread_id)}`, {
    method: "DELETE",
  });
  res.json(data);
});

export default router;