// Minimal Express API server boilerplate
// Run: node server.js
// Requires: npm install

const express = require("express");
const cors = require("cors");
const rateLimit = require("express-rate-limit");

const app = express();
const PORT = process.env.PORT || 3000;

// ── Security & Middleware ─────────────────────────────────────────────────────
app.use(cors({ origin: process.env.ALLOWED_ORIGIN || "http://localhost:8080" }));
app.use(express.json({ limit: "10kb" })); // prevent large payload attacks
app.use(
  rateLimit({
    windowMs: 60 * 1000, // 1 minute
    max: 60,             // max 60 requests per minute per IP
    standardHeaders: true,
    legacyHeaders: false,
  })
);

// ── Health Check ─────────────────────────────────────────────────────────────
app.get("/health", (_req, res) => {
  res.json({ status: "ok", ts: new Date().toISOString() });
});

// ── Example: Contact Form Endpoint ───────────────────────────────────────────
app.post("/api/contact", (req, res) => {
  const { name, email, message } = req.body;

  // Basic validation
  if (!name || !email || !message) {
    return res.status(400).json({ error: "name, email, and message are required." });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: "Invalid email address." });
  }

  // TODO: send email (e.g. via SendGrid, Resend, or SMTP)
  console.log("New contact:", { name, email, message });

  res.json({ success: true, message: "Message received. We'll be in touch!" });
});

// ── Example: Lead Capture Endpoint ───────────────────────────────────────────
app.post("/api/leads", (req, res) => {
  const { email, source } = req.body;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: "Valid email is required." });
  }

  // TODO: add to your CRM or email list (e.g. Mailchimp, ConvertKit, Airtable)
  console.log("New lead:", { email, source });

  res.json({ success: true, message: "You're on the list!" });
});

// ── 404 Handler ───────────────────────────────────────────────────────────────
app.use((_req, res) => {
  res.status(404).json({ error: "Not found." });
});

// ── Start Server ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
