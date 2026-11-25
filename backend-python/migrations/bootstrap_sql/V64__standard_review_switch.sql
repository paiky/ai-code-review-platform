ALTER TABLE code_quality_review_settings
    ADD COLUMN standard_review_enabled BOOLEAN NOT NULL DEFAULT TRUE AFTER review_enabled;

ALTER TABLE code_quality_review_settings
    ALTER COLUMN review_enabled SET DEFAULT TRUE;

UPDATE code_quality_review_settings SET review_enabled = TRUE WHERE id = 1 AND review_enabled = FALSE;
