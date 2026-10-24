-- 在目标环境的 MySQL 数据库中执行；操作步骤见 temporary-review-profile.md。
-- 仅创建 Profile，项目绑定通过现有项目配置页面完成。
-- 已在目标 MySQL 5.7.31 核对表结构并通过 EXPLAIN，未实际执行插入。
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 修改以下四个参数；补充要求为 NULL 时不会插入。
SET @source_profile_code = 'backend-default-ai-review';
SET @new_profile_code = 'project-a-temp-ai-review';
SET @new_profile_name = '项目 A 临时审查 Profile';
SET @extra_instructions = NULL;
-- 例如：SET @extra_instructions = '在此填写项目专用补充要求。';

START TRANSACTION;

INSERT INTO code_quality_review_profiles (
    profile_code, profile_name, enabled, provider, provider_code, model,
    trigger_on_manual, trigger_on_mr, trigger_on_push,
    severity_threshold, block_on_severities, enabled_categories, ignored_paths,
    push_branch_patterns, push_min_changed_files, push_min_diff_bytes,
    push_min_commit_count, push_max_changed_files, push_max_diff_bytes,
    push_debounce_seconds, trigger_only_when_risk_matched,
    codex_prompt, openai_instructions, review_instructions,
    status, description, created_at, updated_at
)
SELECT
    @new_profile_code, @new_profile_name, TRUE,
    source.provider, source.provider_code, source.model,
    source.trigger_on_manual, source.trigger_on_mr, source.trigger_on_push,
    source.severity_threshold, source.block_on_severities,
    source.enabled_categories, source.ignored_paths,
    source.push_branch_patterns, source.push_min_changed_files,
    source.push_min_diff_bytes, source.push_min_commit_count,
    source.push_max_changed_files, source.push_max_diff_bytes,
    source.push_debounce_seconds, source.trigger_only_when_risk_matched,
    CONCAT(source.review_instructions, CHAR(10), CHAR(10), CONVERT(@extra_instructions USING utf8mb4) COLLATE utf8mb4_unicode_ci),
    CONCAT(source.review_instructions, CHAR(10), CHAR(10), CONVERT(@extra_instructions USING utf8mb4) COLLATE utf8mb4_unicode_ci),
    CONCAT(source.review_instructions, CHAR(10), CHAR(10), CONVERT(@extra_instructions USING utf8mb4) COLLATE utf8mb4_unicode_ci),
    'ENABLED', CONCAT('Temporary profile cloned from ', source.profile_code),
    NOW(3), NOW(3)
FROM code_quality_review_profiles AS source
WHERE source.profile_code = CONVERT(@source_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
  AND source.enabled = TRUE
  AND source.status = 'ENABLED'
  AND NULLIF(TRIM(source.review_instructions), '') IS NOT NULL
  AND NULLIF(TRIM(@extra_instructions), '') IS NOT NULL
  AND NULLIF(TRIM(@new_profile_code), '') IS NOT NULL
  AND CHAR_LENGTH(@new_profile_code) <= 64
  AND NULLIF(TRIM(@new_profile_name), '') IS NOT NULL
  AND CHAR_LENGTH(@new_profile_name) <= 128
  AND NOT EXISTS (
    SELECT 1 FROM code_quality_review_profiles AS existing
    WHERE existing.profile_code = CONVERT(@new_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
  );

SET @inserted_rows = ROW_COUNT();
COMMIT;

-- inserted_rows 必须为 1；为 0 时先检查参数、来源及目标是否已存在。
SELECT DATABASE() AS current_database, @inserted_rows AS inserted_rows;

SELECT profile_code, profile_name, enabled, status, provider_code, model,
       review_instructions
FROM code_quality_review_profiles
WHERE profile_code = CONVERT(@new_profile_code USING utf8mb4) COLLATE utf8mb4_unicode_ci;
