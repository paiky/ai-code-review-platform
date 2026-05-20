ALTER TABLE code_quality_review_settings
  ADD COLUMN review_provider VARCHAR(32) NOT NULL DEFAULT 'CODEX_CLI' AFTER mr_auto_review_enabled;
