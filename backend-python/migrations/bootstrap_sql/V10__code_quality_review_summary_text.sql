ALTER TABLE code_quality_review_results
  MODIFY COLUMN summary TEXT NULL;

UPDATE code_quality_review_profiles
SET codex_prompt = '只审查本次变更中会导致线上缺陷、数据不一致、安全风险、事务问题、SQL 性能问题、缓存一致性问题、MQ 一致性问题、异常处理缺口、测试缺口的代码质量问题。不要报告纯风格问题。请使用简体中文输出，每个问题以“高风险：”“中风险：”或“低风险：”开头，并尽量标明文件和行号。'
WHERE profile_code = 'backend-default-ai-review'
  AND (
    codex_prompt IS NULL
    OR codex_prompt = ''
    OR codex_prompt = 'Only report actionable correctness, data consistency, security, transaction, SQL performance, cache consistency, MQ consistency, exception handling, and test gap issues. Do not report style-only issues.'
    OR codex_prompt = 'Only report actionable code quality issues.'
  );
