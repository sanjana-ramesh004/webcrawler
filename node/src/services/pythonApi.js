// src/services/pythonApi.js
/**
 * Shared fetch wrapper for the Python FastAPI backend.
 * Handles base URL, JSON parsing, and error normalisation.
 */
import fetch from "node-fetch";

const BASE = () => process.env.PYTHON_API_URL || "http://localhost:8000";

/**
 * Make a JSON request to the Python API.
 * Throws an error with .status set if the response is not ok.
 */
export async function callPython(path, { method = "GET", body, headers = {} } = {}) {
  const url = `${BASE()}${path}`;

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
    timeout: 120_000,
  });

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const err = new Error(data?.detail || data?.error || `Python API error ${res.status}`);
    err.status = res.status;
    throw err;
  }

  return data;
}

/**
 * Proxy an SSE stream from Python straight through to the Node response.
 */
export async function proxyStream(path, body, nodeRes) {
  const url = `${BASE()}${path}`;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    nodeRes.status(res.status).json({ error: text });
    return;
  }

  nodeRes.setHeader("Content-Type", "text/event-stream");
  nodeRes.setHeader("Cache-Control", "no-cache");
  nodeRes.setHeader("Connection", "keep-alive");
  nodeRes.setHeader("X-Accel-Buffering", "no");
  nodeRes.flushHeaders();

  res.body.pipe(nodeRes);
}