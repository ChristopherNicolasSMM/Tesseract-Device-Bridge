CREATE INDEX IF NOT EXISTS idx_recipes_source ON recipes(source);
CREATE INDEX IF NOT EXISTS idx_audit_event_type_date ON audit_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_config_drafts_status ON configuration_drafts(status);
