ALTER TABLE project_groups
  ADD COLUMN push_branch_patterns JSON NULL AFTER default_provider_code,
  ADD COLUMN push_min_changed_files INT NULL DEFAULT 10 AFTER push_branch_patterns,
  ADD COLUMN push_min_diff_bytes INT NULL DEFAULT 30000 AFTER push_min_changed_files,
  ADD COLUMN push_min_commit_count INT NULL DEFAULT 3 AFTER push_min_diff_bytes,
  ADD COLUMN push_max_changed_files INT NULL DEFAULT -1 AFTER push_min_commit_count,
  ADD COLUMN push_max_diff_bytes INT NULL DEFAULT -1 AFTER push_max_changed_files,
  ADD COLUMN push_debounce_seconds INT NULL DEFAULT 300 AFTER push_max_diff_bytes;

UPDATE project_groups
SET push_branch_patterns = JSON_ARRAY('master'),
    push_min_changed_files = 10,
    push_min_diff_bytes = 30000,
    push_min_commit_count = 3,
    push_max_changed_files = -1,
    push_max_diff_bytes = -1,
    push_debounce_seconds = 300
WHERE push_branch_patterns IS NULL;
