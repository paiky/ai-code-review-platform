ALTER TABLE review_memory_sources
  ADD COLUMN visibility VARCHAR(16) NOT NULL DEFAULT 'PROJECT';

ALTER TABLE review_memory_sources
  ADD INDEX idx_review_memory_sources_visibility_state_kind (visibility, state, kind, id);

CREATE TABLE IF NOT EXISTS review_memory_project_sources (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  source_id BIGINT NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  version INT NOT NULL DEFAULT 1,
  target_type VARCHAR(32) NULL,
  path_globs_json TEXT NULL,
  created_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL,
  UNIQUE KEY uk_review_memory_project_sources (project_id, source_id),
  KEY idx_review_memory_project_sources_project_state (project_id, state, source_id),
  KEY idx_review_memory_project_sources_source_state (source_id, state, project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO review_memory_project_sources
  (project_id, source_id, state, version, created_at, updated_at)
SELECT source.project_id, source.id, 'ACTIVE', 1, source.created_at, source.updated_at
FROM review_memory_sources source
WHERE NOT EXISTS (
  SELECT 1 FROM review_memory_project_sources binding
  WHERE binding.project_id = source.project_id AND binding.source_id = source.id
);
