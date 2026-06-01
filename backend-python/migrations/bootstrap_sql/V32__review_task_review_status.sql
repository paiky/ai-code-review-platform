ALTER TABLE review_tasks
  ADD COLUMN review_status VARCHAR(32) NOT NULL DEFAULT 'NOT_TRIGGERED' AFTER status,
  ADD KEY idx_review_status_created (review_status, created_at);

UPDATE review_tasks task
LEFT JOIN (
  SELECT
    task_id,
    SUM(status = 'RUNNING') AS running_count,
    SUM(status = 'SUCCESS') AS success_count,
    SUM(status = 'FAILED') AS failed_count,
    SUM(status = 'SKIPPED') AS skipped_count,
    MAX(
      CASE
        WHEN status = 'SUCCESS' AND JSON_CONTAINS(findings_json, JSON_OBJECT('severity', 'CRITICAL')) THEN 3
        WHEN status = 'SUCCESS' AND JSON_CONTAINS(findings_json, JSON_OBJECT('severity', 'MAJOR')) THEN 2
        WHEN status = 'SUCCESS' AND JSON_CONTAINS(findings_json, JSON_OBJECT('severity', 'MINOR')) THEN 1
        WHEN status = 'SUCCESS' AND overall_level = 'CRITICAL' THEN 3
        WHEN status = 'SUCCESS' AND overall_level = 'HIGH' THEN 2
        WHEN status = 'SUCCESS' AND overall_level = 'MEDIUM' THEN 1
        ELSE 0
      END
    ) AS max_risk_weight
  FROM code_quality_review_results
  GROUP BY task_id
) quality ON quality.task_id = task.id
SET task.review_status =
  CASE
    WHEN quality.running_count > 0 THEN 'REVIEWING'
    WHEN quality.success_count > 0 AND quality.max_risk_weight >= 3 THEN 'CRITICAL'
    WHEN quality.success_count > 0 AND quality.max_risk_weight = 2 THEN 'MAJOR'
    WHEN quality.success_count > 0 AND quality.max_risk_weight = 1 THEN 'MINOR'
    WHEN quality.success_count > 0 THEN 'NO_RISK'
    WHEN quality.failed_count > 0 THEN 'REVIEW_FAILED'
    WHEN quality.skipped_count > 0 THEN 'SKIPPED'
    WHEN task.status = 'FAILED' THEN 'TASK_FAILED'
    ELSE 'NOT_TRIGGERED'
  END;
