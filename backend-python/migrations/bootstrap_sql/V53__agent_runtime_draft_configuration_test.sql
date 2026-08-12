ALTER TABLE code_quality_agent_runtimes
  ADD COLUMN test_runtime_snapshot_json TEXT NULL AFTER test_finished_at,
  ADD COLUMN test_api_key_ciphertext TEXT NULL AFTER test_runtime_snapshot_json;
