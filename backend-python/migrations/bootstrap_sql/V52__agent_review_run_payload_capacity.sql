ALTER TABLE agent_review_runs
  MODIFY COLUMN input_json LONGTEXT NULL,
  MODIFY COLUMN completion_context_json LONGTEXT NULL;
