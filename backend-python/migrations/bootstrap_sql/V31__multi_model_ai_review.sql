CREATE TABLE IF NOT EXISTS project_group_ai_review_models (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  group_id BIGINT NOT NULL,
  review_key VARCHAR(64) NOT NULL,
  provider_code VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NULL,
  display_name VARCHAR(128) NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_project_group_ai_review_model_key (group_id, review_key),
  KEY idx_project_group_ai_review_models_group (group_id, enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO project_group_ai_review_models (
  group_id,
  review_key,
  provider_code,
  model_name,
  display_name,
  enabled,
  sort_order
)
SELECT
  id,
  LOWER(REPLACE(default_provider_code, '_', '-')),
  default_provider_code,
  NULL,
  default_provider_code,
  TRUE,
  10
FROM project_groups
WHERE default_provider_code IS NOT NULL
  AND default_provider_code <> ''
  AND NOT EXISTS (
    SELECT 1
    FROM project_group_ai_review_models existing
    WHERE existing.group_id = project_groups.id
  );

ALTER TABLE code_quality_review_results
  ADD COLUMN review_key VARCHAR(64) NOT NULL DEFAULT 'default' AFTER task_id,
  ADD COLUMN display_name VARCHAR(128) NULL AFTER model,
  ADD COLUMN sort_order INT NOT NULL DEFAULT 0 AFTER display_name;

ALTER TABLE code_quality_review_results
  DROP INDEX uk_task,
  ADD UNIQUE KEY uk_code_quality_result_task_review_key (task_id, review_key);

ALTER TABLE code_quality_review_progress_events
  ADD COLUMN review_key VARCHAR(64) NULL AFTER task_id;

ALTER TABLE code_quality_fix_previews
  ADD COLUMN review_key VARCHAR(64) NOT NULL DEFAULT 'default' AFTER task_id;

ALTER TABLE code_quality_fix_previews
  DROP INDEX uk_code_quality_fix_preview_task_finding,
  ADD UNIQUE KEY uk_code_quality_fix_preview_task_review_finding (task_id, review_key, finding_index);

ALTER TABLE code_quality_scheduler_jobs
  ADD COLUMN review_key VARCHAR(64) NULL AFTER task_id;
