ALTER TABLE review_tasks
  ADD INDEX idx_review_tasks_cc_created (created_at, id),
  ALGORITHM=INPLACE,
  LOCK=NONE;

ALTER TABLE code_quality_review_results
  ADD INDEX idx_cq_results_cc_updated (updated_at, id),
  ADD INDEX idx_cq_results_cc_provider_updated_status (provider, updated_at, status),
  ALGORITHM=INPLACE,
  LOCK=NONE;

ALTER TABLE deterministic_check_runs
  ADD INDEX idx_deterministic_runs_cc_created (created_at, id),
  ALGORITHM=INPLACE,
  LOCK=NONE;

ALTER TABLE notification_records
  ADD INDEX idx_notification_records_cc_created_status_task (created_at, status, task_id),
  ALGORITHM=INPLACE,
  LOCK=NONE;

ALTER TABLE agent_review_runs
  ADD INDEX idx_agent_review_runs_cc_status_updated (status, updated_at, id),
  ALGORITHM=INPLACE,
  LOCK=NONE;
