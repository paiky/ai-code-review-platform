ALTER TABLE code_quality_review_settings
    ADD COLUMN review_quality_monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE;
