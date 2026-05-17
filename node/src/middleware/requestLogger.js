// src/middleware/requestLogger.js
import { v4 as uuidv4 } from "uuid";

export function requestLogger(req, res, next) {
  const id = uuidv4().split("-")[0];
  const start = Date.now();

  req.requestId = id;
  res.setHeader("X-Request-Id", id);

  res.on("finish", () => {
    const ms = Date.now() - start;
    const level = res.statusCode >= 500 ? "ERROR" : res.statusCode >= 400 ? "WARN" : "INFO";
    console.log(`[${level}][${id}] ${req.method} ${req.originalUrl} → ${res.statusCode} (${ms}ms)`);
  });

  next();
}