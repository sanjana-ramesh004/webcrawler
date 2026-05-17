// src/middleware/rateLimiter.js
import rateLimit from "express-rate-limit";

export const rateLimiter = rateLimit({
  windowMs: Number(process.env.RATE_LIMIT_WINDOW_MS) || 60_000,
  max: Number(process.env.RATE_LIMIT_MAX) || 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests — please slow down." },
  skip: (req) => req.path === "/health",
  handler: (req, res, _next, options) => {
    console.warn(`[rate-limit] ${req.ip} exceeded limit on ${req.path}`);
    res.status(429).json(options.message);
  },
});