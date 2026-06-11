ALTER TABLE review_item_feedbacks
  ADD COLUMN missing_context_types_json TEXT NULL AFTER reason_text;
