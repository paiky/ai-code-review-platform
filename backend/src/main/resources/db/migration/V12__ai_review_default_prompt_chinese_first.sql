UPDATE code_quality_review_profiles
SET codex_prompt = '只报告会影响线上正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理或测试覆盖的问题。
不报告纯代码风格、命名偏好、无明确影响的重构建议。
每个问题都要说明触发条件、潜在影响和建议修复方式。',
    openai_instructions = 'Review only the supplied diff. Return strict JSON. Only report actionable correctness, data consistency, security, transaction, SQL performance, cache consistency, MQ consistency, exception handling, and test gap issues. Do not report style-only issues.',
    updated_at = CURRENT_TIMESTAMP(3)
WHERE profile_code = 'backend-default-ai-review'
  AND (
    codex_prompt IS NULL
    OR codex_prompt = 'Only report actionable correctness, data consistency, security, transaction, SQL performance, cache consistency, MQ consistency, exception handling, and test gap issues. Do not report style-only issues.'
  );
