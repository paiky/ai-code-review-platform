import { bytes, ISSUE_OPTIONS, validateEntry } from './model.js';

export const REVIEW_FEEDBACK_REASON_OPTIONS = [
  ['PROJECT_ALLOWED', '项目允许'], ['HAS_EXTERNAL_GUARD', '已有兜底'],
  ['CONTEXT_MISSING', '上下文不足'], ['RULE_NOT_APPLICABLE', '规则不适用'],
  ['LEVEL_TOO_HIGH', '等级过高'], ['DESCRIPTION_INACCURATE', '描述不准'],
  ['DUPLICATE', '重复提醒'], ['OTHER', '其他']
].map(([value, label]) => ({ value, label }));

export const MISSING_CONTEXT_TYPE_OPTIONS = [
  ['SAME_FILE_CONTEXT', '同文件上下文'], ['SAME_CLASS_METHODS', '同类方法'],
  ['REFERENCE_SEARCH', '引用搜索'], ['CALLER_CONTEXT', '调用方'],
  ['CALLEE_CONTEXT', '被调用方'], ['RELATED_FILE', '相关文件'],
  ['DB_SCHEMA_CONTEXT', '表结构'], ['CONFIG_CONTEXT', '配置'],
  ['PROJECT_POLICY_CONTEXT', '项目规则'], ['TEST_RESULT_CONTEXT', '测试结果'],
  ['OTHER', '其他']
].map(([value, label]) => ({ value, label }));

export const FEEDBACK_STATUS_OPTIONS = [
  ['PENDING', '待分析'], ['VALID', '有效反馈'], ['INSUFFICIENT', '信息不足'],
  ['IGNORED', '已撤回 / 忽略'], ['CONVERTED', '已转为旧项目策略']
].map(([value, label]) => ({ value, label }));

export const CASE_FIELDS = [
  ['applicability', '适用条件'], ['misjudgmentCause', '原误判及原因'],
  ['correctApproach', '正确判断方法'], ['requiredEvidence', '下次应查证据'],
  ['exceptions', '例外/失效条件']
];
export const isWritebackPending = (state) => ['PENDING', 'RUNNING', 'RETRY_WAIT'].includes(state);
export const WRITEBACK_LABELS = {
  PENDING: '已受理，等待回写', RUNNING: '回写处理中', RETRY_WAIT: '等待自动重试',
  SUCCEEDED: '回写已成功', FAILED: '回写失败', CANCELLED_STALE_SOURCE: '确认已失效'
};

export function memoryFeedbackState(row) {
  if (isWritebackPending(row.writebackState)) return WRITEBACK_LABELS[row.writebackState];
  if (row.sourceState === 'DELETED') return '案例已删除';
  if (row.sourceState === 'DISABLED') return '已失效 / 停用';
  if (row.writebackState === 'FAILED') return row.sourceState === 'PUBLISHED' ? '更新失败，原案例仍发布' : '回写失败';
  if (row.sourceState === 'PUBLISHED') return '已沉淀';
  if (row.writebackState === 'CANCELLED_STALE_SOURCE') return '已失效 / 停用';
  if (row.status === 'CONVERTED') return '已转为旧项目策略';
  return '尚未沉淀';
}

export function caseDraft(detail, source, targetType) {
  const entry = source?.entries?.[0];
  const draft = {
    title: source?.title || detail.riskTitle || '',
    targetType: entry ? entry.targetType : targetType || null,
    issueType: entry ? entry.issueType : ISSUE_OPTIONS.some((o) => o.value === detail.riskType) ? detail.riskType : null,
    pathGlobs: entry?.pathGlobs || [], keywords: entry?.keywords || [], loadMode: 'ON_DEMAND',
    applicability: '', misjudgmentCause: detail.reasonText || '', correctApproach: '',
    requiredEvidence: '', exceptions: ''
  };
  if (entry) {
    for (let i = 0; i < CASE_FIELDS.length; i += 1) {
      const [key, label] = CASE_FIELDS[i];
      const marker = `## ${label}\n\n`;
      const start = entry.content.indexOf(marker);
      const next = i < CASE_FIELDS.length - 1 ? entry.content.indexOf(`\n\n## ${CASE_FIELDS[i + 1][1]}\n\n`, start + marker.length) : -1;
      draft[key] = start < 0 ? '' : entry.content.slice(start + marker.length, next < 0 ? undefined : next).trim();
    }
  }
  return draft;
}

export const caseContent = (draft) => CASE_FIELDS.map(([key, label]) => `## ${label}\n\n${draft[key].trim()}`).join('\n\n');

export function caseValidation(draft) {
  if (!draft.title.trim()) return '请填写案例标题。';
  const missing = CASE_FIELDS.find(([key]) => !draft[key].trim());
  if (missing) return `请填写“${missing[1]}”。`;
  if (bytes(caseContent(draft)) > 4000) return '完整案例超过 4000 UTF-8 字节，请精简后确认，保留证据和例外条件。';
  return validateEntry({ ...draft, heading: draft.title, content: caseContent(draft) });
}

export function feedbackError(error) {
  const code = typeof error === 'string' ? error : error?.code;
  return ({
    MEMORY_FEEDBACK_CHANGED: '原反馈已变化，请刷新并对照后重新确认。',
    MEMORY_VERSION_CONFLICT: '案例版本已变化，请刷新并对照，当前输入已保留。',
    MEMORY_FEEDBACK_NOT_CONFIRMABLE: '当前反馈不可确认，请检查是否已撤回或转为旧策略。',
    MEMORY_FINDING_UNAVAILABLE: '原 finding 已不存在或变化，不能确认旧结论。',
    MEMORY_MISSING_EVIDENCE_REQUIRED: '请先修改误报反馈，说明缺少的背景或证据。',
    MEMORY_STATE_CONFLICT: '来源状态已变化；已删除的案例不能恢复。',
    MEMORY_DATABASE_TEMPORARY: '数据库暂时不可用，系统正在等待重试。',
    MEMORY_WRITEBACK_ATTEMPTS_EXHAUSTED: '回写尝试次数已用完，请检查服务状态，再修正案例重新确认。',
    MEMORY_CONFIRMATION_INVALID: '确认内容不符合规则，请修正完整案例后重新确认。',
    MEMORY_WRITEBACK_FAILED: '回写失败，请检查服务状态。相同内容再次提交会返回原失败记录。',
    MEMORY_CONFIRMATION_SUPERSEDED: '此确认已被较新的确认替代，请刷新。',
    MEMORY_FEEDBACK_MISSING: '原反馈已不可用，请刷新。'
  })[code] || (typeof error === 'string' ? '请刷新核对反馈及案例状态。' : error?.message) || '请求失败，请重试。';
}
