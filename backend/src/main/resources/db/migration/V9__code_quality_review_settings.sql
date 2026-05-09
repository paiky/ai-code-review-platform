CREATE TABLE code_quality_review_settings (
  id BIGINT PRIMARY KEY,
  mr_auto_review_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO code_quality_review_settings (id, mr_auto_review_enabled)
VALUES (1, TRUE)
ON DUPLICATE KEY UPDATE
  mr_auto_review_enabled = mr_auto_review_enabled;
