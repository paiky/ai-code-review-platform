ALTER TABLE project_groups
  ADD COLUMN ai_review_enabled BOOLEAN NOT NULL DEFAULT TRUE AFTER default_provider_code,
  ADD COLUMN trigger_on_manual BOOLEAN NOT NULL DEFAULT TRUE AFTER ai_review_enabled,
  ADD COLUMN trigger_on_mr BOOLEAN NOT NULL DEFAULT TRUE AFTER trigger_on_manual,
  ADD COLUMN trigger_on_push BOOLEAN NOT NULL DEFAULT FALSE AFTER trigger_on_mr,
  ADD COLUMN trigger_only_when_risk_matched BOOLEAN NOT NULL DEFAULT FALSE AFTER trigger_on_push,
  ADD COLUMN auto_fix_preview_enabled BOOLEAN NOT NULL DEFAULT FALSE AFTER trigger_only_when_risk_matched,
  ADD COLUMN auto_fix_preview_severities TEXT NULL AFTER auto_fix_preview_enabled;

UPDATE project_groups
SET
  ai_review_enabled = TRUE,
  trigger_on_manual = TRUE,
  trigger_on_mr = TRUE,
  trigger_on_push = FALSE,
  trigger_only_when_risk_matched = FALSE,
  auto_fix_preview_enabled = FALSE,
  auto_fix_preview_severities = JSON_ARRAY('CRITICAL')
WHERE ai_review_enabled IS NULL
   OR trigger_on_manual IS NULL
   OR trigger_on_mr IS NULL
   OR trigger_on_push IS NULL
   OR trigger_only_when_risk_matched IS NULL
   OR auto_fix_preview_enabled IS NULL
   OR auto_fix_preview_severities IS NULL;
