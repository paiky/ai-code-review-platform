UPDATE project_groups
SET review_engine = 'AGENT',
    agent_source_export_allowed = TRUE,
    ai_review_enabled = TRUE,
    trigger_on_manual = TRUE;

ALTER TABLE project_groups
  MODIFY COLUMN review_engine VARCHAR(32) NOT NULL DEFAULT 'AGENT',
  MODIFY COLUMN agent_source_export_allowed BOOLEAN NOT NULL DEFAULT TRUE,
  MODIFY COLUMN ai_review_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  MODIFY COLUMN trigger_on_manual BOOLEAN NOT NULL DEFAULT TRUE;
