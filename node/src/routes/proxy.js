// src/routes/proxy.js
/**
 * Catch-all reverse proxy for any /api/* route not handled above.
 * Forwards requests straight to the Python FastAPI server.
 */
import { createProxyMiddleware } from "http-proxy-middleware";
import { Router } from "express";

const router = Router();

const pythonProxy = createProxyMiddleware({
  target: process.env.PYTHON_API_URL || "http://localhost:8000",
  changeOrigin: true,
  on: {
    error(err, req, res) {
      console.error(`[proxy] ${req.method} ${req.path} failed:`, err.message);
      res.status(502).json({
        error: "Python API unreachable. Is FastAPI running?",
        detail: err.message,
      });
    },
    proxyReq(proxyReq, req) {
      if (req.requestId) {
        proxyReq.setHeader("X-Request-Id", req.requestId);
      }
    },
  },
});

router.use("/", pythonProxy);

export default router;