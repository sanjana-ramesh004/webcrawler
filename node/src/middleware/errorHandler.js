// src/middleware/errorHandler.js
export function errorHandler(err, req, res, _next) {
  const status = err.status || err.statusCode || 500;
  const message = err.message || "Internal server error";

  console.error(`[error] ${req.method} ${req.path} → ${status}: ${message}`);

  if (err.stack && process.env.NODE_ENV !== "production") {
    console.error(err.stack);
  }

  // Don't leak stack traces in production
  res.status(status).json({
    error: message,
    path: req.path,
    requestId: req.requestId || null,
    ...(process.env.NODE_ENV !== "production" && { stack: err.stack }),
  });
}