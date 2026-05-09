-- Venture Engine V1 schema

CREATE TABLE IF NOT EXISTS businesses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  domain TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  email TEXT DEFAULT '',
  vertical TEXT DEFAULT '',
  location TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_id INTEGER NOT NULL,
  problem TEXT NOT NULL,
  evidence TEXT NOT NULL DEFAULT '{}',
  proof_confidence REAL NOT NULL DEFAULT 0.0,
  estimated_loss_range TEXT DEFAULT '',
  assumptions_json TEXT DEFAULT '[]',
  score REAL NOT NULL DEFAULT 0.0,
  trust_score REAL NOT NULL DEFAULT 0.0,
  status TEXT NOT NULL DEFAULT 'new',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL,
  stage TEXT NOT NULL,
  last_updated TEXT NOT NULL,
  revenue REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS suppression_list (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact TEXT NOT NULL UNIQUE,
  reason TEXT NOT NULL,
  do_not_contact_until TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  reasons TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS block_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  details TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trust_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  trust_delta REAL NOT NULL,
  metadata TEXT DEFAULT '{}',
  created_at TEXT NOT NULL
);

-- Runtime venture_jobs.db (JobQueue) also defines opportunities + lifecycle_events for replayable state.
