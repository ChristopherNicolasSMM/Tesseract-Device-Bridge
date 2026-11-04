CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS system_config (
  id INTEGER PRIMARY KEY CHECK (id=1),
  config_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  position INTEGER NOT NULL,
  config_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_order ON devices(position);
CREATE TABLE IF NOT EXISTS configuration_revisions (
  revision INTEGER PRIMARY KEY,
  snapshot_json TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS configuration_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payload_json TEXT NOT NULL,
  base_revision INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','applied','discarded')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS recipes (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK(source IN ('public','private')),
  editable INTEGER NOT NULL CHECK(editable IN (0,1)),
  recipe_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS recipe_revisions (
  recipe_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  recipe_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (recipe_id, revision)
);
CREATE TABLE IF NOT EXISTS active_recipe (
  id INTEGER PRIMARY KEY CHECK(id=1),
  recipe_id TEXT REFERENCES recipes(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sensor_calibrations (
  sensor_id TEXT PRIMARY KEY,
  address TEXT,
  offset_c REAL NOT NULL CHECK (offset_c BETWEEN -5 AND 5),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session_state (
  id INTEGER PRIMARY KEY CHECK(id=1),
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  entity_id TEXT,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS legacy_imports (
  source_sha256 TEXT PRIMARY KEY,
  manifest_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
