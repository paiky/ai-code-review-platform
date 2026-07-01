import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Cascader,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  InputNumber,
  Layout,
  message,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Steps,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography
} from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  ClusterOutlined,
  CommentOutlined,
  CopyOutlined,
  ExportOutlined,
  EyeOutlined,
  FileSearchOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  MoonOutlined,
  QuestionCircleOutlined,
  SunOutlined,
  UnorderedListOutlined
} from '@ant-design/icons';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import Prism from 'prismjs';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-java';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-jsx';
import 'prismjs/components/prism-markdown';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import 'prismjs/components/prism-tsx';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-yaml';
import { fetchApi, riskColor, statusColor } from './api.js';
import { releaseNotes } from './releaseNotes.js';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const fineChangeTypes = new Set([
  'DB_SCHEMA',
  'DB_SQL',
  'ORM_MAPPING',
  'ENTITY_MODEL',
  'DATA_MIGRATION',
  'CACHE_KEY',
  'CACHE_TTL',
  'CACHE_INVALIDATION',
  'CACHE_READ_WRITE',
  'CACHE_SERIALIZATION',
  'MQ_PRODUCER',
  'MQ_CONSUMER',
  'MQ_MESSAGE_SCHEMA',
  'MQ_TOPIC_CONFIG',
  'MQ_RETRY_DLQ'
]);

const HOME_ROUTE = '/';
const TASK_LIST_ROUTE = '/tasks';
const RULE_GAPS_ROUTE = '/rule-gaps';
const FEEDBACK_ROUTE = '/risk-feedback';
const REVIEW_QUALITY_ROUTE = '/review-quality';
const EVALUATION_CASES_ROUTE = '/evaluation-cases';
const EVALUATION_RUNS_ROUTE = '/evaluation-runs';
const SETTINGS_ROUTE = '/settings';
const RELEASES_ROUTE = '/releases';
const HELP_ROUTE = '/help';
const REVIEW_LEARNING_UI_ENABLED = String(import.meta.env.VITE_REVIEW_LEARNING_UI_ENABLED || '').toLowerCase() === 'true';
const PROJECT_REVIEW_POLICY_UI_ENABLED = REVIEW_LEARNING_UI_ENABLED
  && String(import.meta.env.VITE_PROJECT_REVIEW_POLICY_UI_ENABLED || '').toLowerCase() === 'true';
const JOB_QUEUE_REFRESH_EVENT = 'ai-review-job-queue-refresh';
const FAILURE_NOTIFICATION_REFRESH_EVENT = 'ai-review-failure-notification-refresh';
const TARGET_TYPE_OPTIONS = [
  { label: '后端', value: 'BACKEND' },
  { label: 'PC Web / H5', value: 'WEB_PC' },
  { label: 'iOS', value: 'APP_IOS' },
  { label: 'Android', value: 'APP_ANDROID' },
  { label: '跨端应用', value: 'APP_CROSS_PLATFORM' },
  { label: '通用', value: 'GENERAL' }
];
const TASK_TRIGGER_TYPE_OPTIONS = [
  { label: 'MR', value: 'GITLAB_MR_WEBHOOK' },
  { label: 'Push', value: 'GITLAB_PUSH_WEBHOOK' }
];
const AUTO_FIX_PREVIEW_SEVERITY_OPTIONS = [
  { label: '紧急 CRITICAL', value: 'CRITICAL' },
  { label: '高风险 MAJOR', value: 'MAJOR' },
  { label: '中风险 MINOR', value: 'MINOR' }
];
const TASK_REVIEW_STATUS_OPTIONS = [
  { label: '未触发审查', value: 'NOT_TRIGGERED' },
  { label: '审查中', value: 'REVIEWING' },
  { label: '无风险', value: 'NO_RISK' },
  { label: '中风险', value: 'MINOR' },
  { label: '高风险', value: 'MAJOR' },
  { label: '紧急', value: 'CRITICAL' },
  { label: '已跳过', value: 'SKIPPED' },
  { label: '审查失败', value: 'REVIEW_FAILED' },
  { label: '任务失败', value: 'TASK_FAILED' }
];
const EVALUATION_RUN_TYPE_OPTIONS = [
  { label: '评估运行', value: 'EVALUATION' },
  { label: 'Review 回放', value: 'REVIEW_REPLAY' }
];
const EVALUATION_RUN_STATUS_OPTIONS = [
  { label: '待记录', value: 'PENDING' },
  { label: '记录中', value: 'RUNNING' },
  { label: '已完成', value: 'COMPLETED' },
  { label: '失败', value: 'FAILED' },
  { label: '已取消', value: 'CANCELED' }
];
const DEFAULT_AUTO_FIX_PREVIEW_SEVERITIES = ['CRITICAL'];
const PROJECT_TARGET_TYPE_OPTIONS = TARGET_TYPE_OPTIONS.filter(item => item.value !== 'APP_CROSS_PLATFORM');
const TARGET_TYPE_DEFAULT_PATH_PATTERNS = {
  BACKEND: ['src/main/java/**', 'src/main/resources/**', 'src/*.java', 'src/**/*.java', 'pom.xml', 'backend-python/**', 'backend/**'],
  WEB_PC: ['frontend/**', 'web/**', 'src/**/*.tsx', 'src/**/*.jsx', 'src/**/*.vue', 'package.json'],
  APP_IOS: ['ios/**', '**/*.swift', '**/*.m', '**/*.mm', 'Podfile'],
  APP_ANDROID: ['android/**', '**/*.kt', '**/*.kts', 'build.gradle', 'settings.gradle', '**/*.gradle'],
  APP_CROSS_PLATFORM: ['flutter/**', '**/*.dart', 'pubspec.yaml', 'rn/**', 'miniapp/**'],
  GENERAL: ['**/*']
};
const TARGET_TYPE_PATH_MAPPING_OPTIONS = TARGET_TYPE_OPTIONS.filter(
  item => !['GENERAL', 'APP_CROSS_PLATFORM'].includes(item.value)
);
const REVIEW_PROFILE_DROPDOWN_ITEMS = [
  { profileCode: 'backend-default-ai-review', label: '后端' },
  { profileCode: 'web-pc-default-ai-review', label: '前端' },
  { profileCode: 'app-android-default-ai-review', label: 'Android' },
  { profileCode: 'app-ios-default-ai-review', label: 'IOS' }
];
const REVIEW_PROFILE_DROPDOWN_LABELS = REVIEW_PROFILE_DROPDOWN_ITEMS.reduce(
  (labels, item) => ({ ...labels, [item.profileCode]: item.label }),
  {}
);
const DEFAULT_PUSH_REVIEW_POLICY = {
  aiReviewEnabled: true,
  triggerOnManual: true,
  triggerOnMr: true,
  triggerOnPush: true,
  triggerOnlyWhenRiskMatched: false,
  autoFixPreviewEnabled: true,
  autoFixPreviewSeverities: ['CRITICAL'],
  pushBranchPatterns: ['master'],
  pushMinChangedFiles: 10,
  pushMinDiffBytes: 30000,
  pushMinCommitCount: 3,
  pushMaxChangedFiles: -1,
  pushMaxDiffBytes: -1,
  pushDebounceSeconds: 300
};
const REVIEW_FEEDBACK_SOURCE_OPTIONS = [
  { label: '规则提醒', value: 'RULE_REMINDER' },
  { label: 'AI Finding', value: 'AI_FINDING' }
];
const REVIEW_FEEDBACK_TYPE_OPTIONS = [
  { label: '有用', value: 'USEFUL' },
  { label: '误判', value: 'FALSE_POSITIVE' },
  { label: '等级过高', value: 'LEVEL_TOO_HIGH' },
  { label: '重复提醒', value: 'DUPLICATE' },
  { label: '已修复', value: 'FIXED' }
];
const REVIEW_FEEDBACK_REASON_OPTIONS = [
  { label: '项目允许', value: 'PROJECT_ALLOWED' },
  { label: '已有兜底', value: 'HAS_EXTERNAL_GUARD' },
  { label: '上下文不足', value: 'CONTEXT_MISSING' },
  { label: '规则不适用', value: 'RULE_NOT_APPLICABLE' },
  { label: '等级过高', value: 'LEVEL_TOO_HIGH' },
  { label: '描述不准', value: 'DESCRIPTION_INACCURATE' },
  { label: '重复提醒', value: 'DUPLICATE' },
  { label: '其他', value: 'OTHER' }
];
const REVIEW_FEEDBACK_STATUS_OPTIONS = [
  { label: '待分析', value: 'PENDING' },
  { label: '有效反馈', value: 'VALID' },
  { label: '信息不足', value: 'INSUFFICIENT' },
  { label: '已忽略', value: 'IGNORED' },
  { label: '已沉淀', value: 'CONVERTED' }
];
const EVALUATION_CASE_VERDICT_OPTIONS = [
  { label: '有效问题', value: 'TRUE_POSITIVE' },
  { label: '误判', value: 'FALSE_POSITIVE' },
  { label: '等级过高', value: 'LEVEL_TOO_HIGH' },
  { label: '等级过低', value: 'LEVEL_TOO_LOW' },
  { label: '上下文不足', value: 'CONTEXT_MISSING' },
  { label: '重复问题', value: 'DUPLICATE' },
  { label: '漏报样本', value: 'MISSING_FINDING' },
  { label: '待确认', value: 'UNKNOWN' }
];
const PROJECT_REVIEW_POLICY_TYPE_OPTIONS = [
  { label: '项目规则', value: 'PROJECT_RULE' },
  { label: '项目事实', value: 'CONTEXT_FACT' }
];
const MISSING_CONTEXT_TYPE_OPTIONS = [
  { label: '同文件上下文', value: 'SAME_FILE_CONTEXT' },
  { label: '同类方法', value: 'SAME_CLASS_METHODS' },
  { label: '引用搜索', value: 'REFERENCE_SEARCH' },
  { label: '调用方', value: 'CALLER_CONTEXT' },
  { label: '被调用方', value: 'CALLEE_CONTEXT' },
  { label: '相关文件', value: 'RELATED_FILE' },
  { label: '表结构', value: 'DB_SCHEMA_CONTEXT' },
  { label: '配置', value: 'CONFIG_CONTEXT' },
  { label: '项目规则', value: 'PROJECT_POLICY_CONTEXT' },
  { label: '测试结果', value: 'TEST_RESULT_CONTEXT' },
  { label: '其他', value: 'OTHER' }
];

function targetTypeLabel(value) {
  return TARGET_TYPE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function defaultTemplateCodeForTargetType(targetType) {
  if (targetType === 'BACKEND') return 'backend-default';
  if (targetType === 'GENERAL') return 'general-default';
  return 'frontend-default';
}

function defaultReminderCardEnabledForTargetType(targetType) {
  return targetType === 'BACKEND';
}

function defaultPathPatternsForTargetType(targetType) {
  return TARGET_TYPE_DEFAULT_PATH_PATTERNS[targetType] || TARGET_TYPE_DEFAULT_PATH_PATTERNS.GENERAL;
}

function pushPolicyFromGroup(group) {
  return {
    ...DEFAULT_PUSH_REVIEW_POLICY,
    ...(group || {}),
    pushBranchPatterns: Array.isArray(group?.pushBranchPatterns) ? group.pushBranchPatterns : [...DEFAULT_PUSH_REVIEW_POLICY.pushBranchPatterns],
    autoFixPreviewSeverities: normalizeAutoFixPreviewSeverities(group?.autoFixPreviewSeverities)
  };
}

function requestJobQueueRefresh() {
  window.dispatchEvent(new Event(JOB_QUEUE_REFRESH_EVENT));
  window.dispatchEvent(new Event(FAILURE_NOTIFICATION_REFRESH_EVENT));
}

function profileLabel(profile) {
  const labels = {
    ...REVIEW_PROFILE_DROPDOWN_LABELS,
    'app-cross-platform-default-ai-review': '跨端应用默认 AI Review'
  };
  return labels[profile?.profileCode] || profile?.profileName || profile?.profileCode || '-';
}

function selectableReviewProfiles(profiles = []) {
  const byCode = new Map(profiles.map(profile => [profile.profileCode, profile]));
  return REVIEW_PROFILE_DROPDOWN_ITEMS
    .map(item => byCode.get(item.profileCode))
    .filter(Boolean);
}

function currentRoute(location) {
  return `${location.pathname}${location.search || ''}${location.hash || ''}`;
}

function resolveBackTarget(location, fallbackPath) {
  const from = location?.state?.from;
  return typeof from === 'string' && from.trim() ? from : fallbackPath;
}

function JsonBlock({ value }) {
  return <pre className="json-block">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function formatRate(value) {
  const number = Number(value || 0);
  return `${(number * 100).toFixed(1)}%`;
}

function confidenceColor(value) {
  if (value === 'HIGH') return 'red';
  if (value === 'MEDIUM') return 'orange';
  if (value === 'LOW') return 'green';
  return 'default';
}

function confidenceLabel(value) {
  switch (value) {
    case 'HIGH':
      return '高';
    case 'MEDIUM':
      return '中';
    case 'LOW':
      return '低';
    default:
      return value || '-';
  }
}

function contextStatusColor(value) {
  if (value === 'SUFFICIENT') return 'green';
  if (value === 'PARTIAL') return 'gold';
  if (value === 'INSUFFICIENT') return 'red';
  return 'default';
}

function contextStatusLabel(value) {
  switch (value) {
    case 'SUFFICIENT':
      return '充分';
    case 'PARTIAL':
      return '部分';
    case 'INSUFFICIENT':
      return '不足';
    default:
      return value || '-';
  }
}

function missingContextLabel(value) {
  return MISSING_CONTEXT_TYPE_OPTIONS.find(item => item.value === value)?.label || value;
}

const REFINEMENT_CANDIDATE_SEVERITIES = new Set(['CRITICAL', 'MAJOR', 'HIGH']);
const REFINEMENT_CANDIDATE_CONTEXT_STATUSES = new Set(['PARTIAL', 'INSUFFICIENT']);

function isRefinementCandidate(finding) {
  return REFINEMENT_CANDIDATE_SEVERITIES.has(String(finding?.severity || '').toUpperCase())
    && REFINEMENT_CANDIDATE_CONTEXT_STATUSES.has(String(finding?.contextStatus || '').toUpperCase());
}

function refinementStatusColor(status) {
  switch (String(status || '').toUpperCase()) {
    case 'COMPLETED':
      return 'green';
    case 'FAILED':
      return 'red';
    default:
      return 'default';
  }
}

function refinementStatusLabel(status) {
  switch (String(status || '').toUpperCase()) {
    case 'COMPLETED':
      return '已完成';
    case 'FAILED':
      return '失败';
    default:
      return status || '未触发';
  }
}

function refinementTriggerReasonLabel(value) {
  switch (value) {
    case 'HIGH_IMPACT_CONTEXT_INSUFFICIENT':
      return '高影响且上下文不足';
    default:
      return value || '-';
  }
}

function sanitizeRefinementText(value) {
  return String(value ?? '')
    .replace(/Authorization:\s*Bearer\s+[^\s,;]+/gi, 'Authorization: Bearer ***')
    .replace(/\b[A-Za-z]:\\[^\s"',;]+/g, '[local-path]')
    .replace(/\b(?:sk|api|token|key)-[A-Za-z0-9._-]{8,}\b/gi, '[secret]')
    .slice(0, 500);
}

function normalizeTextList(value) {
  const raw = Array.isArray(value) ? value : (value ? [value] : []);
  return raw
    .map(item => {
      if (item && typeof item === 'object') {
        return item.text || item.summary || item.snippet || item.type || '';
      }
      return item;
    })
    .map(item => String(item || '').trim())
    .filter(Boolean);
}

function severityColor(value) {
  if (value === 'CRITICAL') return 'red';
  if (value === 'MAJOR') return 'volcano';
  if (value === 'MINOR') return 'gold';
  if (value === 'HIGH') return 'volcano';
  if (value === 'MEDIUM') return 'gold';
  if (value === 'LOW') return 'green';
  return riskColor(value);
}

function severityLabel(value) {
  switch (value) {
    case 'CRITICAL':
      return '紧急';
    case 'HIGH':
    case 'MAJOR':
      return '高风险';
    case 'MEDIUM':
    case 'MINOR':
      return '中风险';
    case 'LOW':
      return '低风险';
    default:
      return value || '-';
  }
}

function reviewFeedbackSourceLabel(value) {
  return REVIEW_FEEDBACK_SOURCE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function reviewFeedbackTypeLabel(value) {
  return REVIEW_FEEDBACK_TYPE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function reviewFeedbackReasonLabel(value) {
  return REVIEW_FEEDBACK_REASON_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function reviewFeedbackStatusLabel(value) {
  return REVIEW_FEEDBACK_STATUS_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function reviewFeedbackStatusColor(value) {
  if (value === 'VALID') return 'green';
  if (value === 'INSUFFICIENT') return 'orange';
  if (value === 'IGNORED') return 'default';
  if (value === 'CONVERTED') return 'purple';
  return 'blue';
}

function evaluationCaseVerdictLabel(value) {
  return EVALUATION_CASE_VERDICT_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function evaluationCaseVerdictColor(value) {
  if (value === 'TRUE_POSITIVE') return 'green';
  if (value === 'FALSE_POSITIVE') return 'red';
  if (value === 'LEVEL_TOO_HIGH' || value === 'LEVEL_TOO_LOW') return 'orange';
  if (value === 'CONTEXT_MISSING') return 'gold';
  if (value === 'DUPLICATE') return 'purple';
  if (value === 'MISSING_FINDING') return 'blue';
  return 'default';
}

function evaluationRunTypeLabel(value) {
  return EVALUATION_RUN_TYPE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function evaluationRunStatusLabel(value) {
  return EVALUATION_RUN_STATUS_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function evaluationRunStatusColor(value) {
  switch (value) {
    case 'COMPLETED':
      return 'green';
    case 'FAILED':
      return 'red';
    case 'RUNNING':
      return 'processing';
    case 'CANCELED':
      return 'default';
    case 'PENDING':
      return 'blue';
    default:
      return 'default';
  }
}

function compactHash(value) {
  return value ? String(value).slice(0, 12) : '-';
}

function projectReviewPolicyTypeLabel(value) {
  return PROJECT_REVIEW_POLICY_TYPE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function projectReviewPolicyTypeColor(value) {
  if (value === 'PROJECT_RULE') return 'blue';
  if (value === 'CONTEXT_FACT') return 'cyan';
  return 'default';
}

function reviewFeedbackTypeColor(value) {
  if (value === 'USEFUL' || value === 'FIXED') return 'green';
  if (value === 'FALSE_POSITIVE') return 'red';
  if (value === 'LEVEL_TOO_HIGH') return 'orange';
  if (value === 'DUPLICATE') return 'purple';
  return 'default';
}

function defaultReasonTypeForFeedback(feedbackType) {
  if (feedbackType === 'LEVEL_TOO_HIGH') return 'LEVEL_TOO_HIGH';
  if (feedbackType === 'DUPLICATE') return 'DUPLICATE';
  return 'OTHER';
}

function taskReviewStatusLabel(value) {
  return TASK_REVIEW_STATUS_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function taskReviewStatusColor(value) {
  return {
    NOT_TRIGGERED: 'default',
    REVIEWING: 'processing',
    NO_RISK: 'green',
    MINOR: 'gold',
    MAJOR: 'volcano',
    CRITICAL: 'red',
    SKIPPED: 'default',
    REVIEW_FAILED: 'red',
    TASK_FAILED: 'red'
  }[value] || 'default';
}

function normalizeAutoFixPreviewSeverities(value) {
  const raw = Array.isArray(value) ? value : [];
  const allowed = AUTO_FIX_PREVIEW_SEVERITY_OPTIONS.map(item => item.value);
  const result = raw
    .map(item => String(item || '').trim().toUpperCase())
    .filter((item, index, items) => allowed.includes(item) && items.indexOf(item) === index);
  return result.length ? result : [...DEFAULT_AUTO_FIX_PREVIEW_SEVERITIES];
}

function autoFixPreviewSeveritySummary(value) {
  const selected = normalizeAutoFixPreviewSeverities(value);
  return selected
    .map(item => severityLabel(item))
    .join(' / ');
}

function codeQualitySummary(review, findings) {
  if (review?.status === 'RUNNING') return 'AI Review 正在执行，完成后会自动刷新。';
  if (review?.status === 'FAILED') return review?.errorMessage || 'AI Review 执行失败。';
  if (review?.status === 'SKIPPED') return review?.errorMessage || 'AI Review 已跳过。';
  if (findings.length > 0) {
    const highCount = findings.filter(item => ['CRITICAL', 'HIGH', 'MAJOR'].includes(item.severity)).length;
    const mediumCount = findings.filter(item => ['MEDIUM', 'MINOR'].includes(item.severity)).length;
    return `发现 ${findings.length} 个代码质量问题，其中高风险 ${highCount} 个，中风险 ${mediumCount} 个。`;
  }
  if (!review?.summary || review.summary === '**Findings**') return '未解析到结构化代码质量问题。';
  return review.summary;
}

function categoryLabel(value) {
  switch (value) {
    case 'CODE_QUALITY':
      return '代码质量';
    case 'CORRECTNESS':
      return '正确性';
    case 'SECURITY':
      return '安全';
    case 'TRANSACTION':
      return '事务一致性';
    case 'SQL_PERFORMANCE':
      return 'SQL 性能';
    case 'CACHE_CONSISTENCY':
      return '缓存一致性';
    case 'MQ_CONSISTENCY':
      return 'MQ 一致性';
    case 'EXCEPTION_HANDLING':
      return '异常处理';
    case 'TEST_GAP':
      return '测试缺口';
    default:
      return value || '-';
  }
}

function sourceLabel(value) {
  switch (value) {
    case 'OPENAI':
      return 'OpenAI';
    case 'ANTHROPIC':
      return 'Claude';
    case 'DEEPSEEK':
      return 'DeepSeek';
    case 'XIAOMIMO':
      return 'XiaoMIMO';
    case 'GLM':
      return 'GLM';
    case 'CUSTOM':
      return '自定义';
    case 'CODEX_CLI':
      return 'Codex CLI（历史）';
    case 'OPENAI_API':
      return 'OpenAI API（历史）';
    case 'ANTHROPIC_API':
      return 'Anthropic API（历史）';
    default:
      return value || '-';
  }
}

function taskTypeLabel(value) {
  if (value === 'GITLAB_MR_WEBHOOK') return 'MR';
  if (value === 'GITLAB_PUSH_WEBHOOK') return 'Push';
  if (value === 'CODE_QUALITY_MANUAL') return '手动';
  return value || '-';
}

function taskTitle(detail) {
  if (!detail) return '-';
  if (detail.triggerType === 'GITLAB_PUSH_WEBHOOK') {
    return `${detail.projectName} Push ${detail.commitSha ? detail.commitSha.slice(0, 8) : ''}`.trim();
  }
  if (detail.triggerType === 'GITLAB_MR_WEBHOOK') return `${detail.projectName} MR !${detail.mrId || '-'}`;
  return `${detail.projectName} ${taskTypeLabel(detail.triggerType)}`;
}

function branchSummary(detail) {
  if (!detail) return '-';
  if (detail.triggerType === 'GITLAB_PUSH_WEBHOOK') return `推送分支：${detail.sourceBranch || '-'}`;
  return `${detail.sourceBranch || '-'} -> ${detail.targetBranch || '-'}`;
}

function taskListBranchText(row) {
  if (!row) return '-';
  if (row.triggerType === 'GITLAB_PUSH_WEBHOOK') return `推送分支：${row.sourceBranch || '-'}`;
  return `${row.sourceBranch || '-'} -> ${row.targetBranch || '-'}`;
}

function cleanAiMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\[([^\]]+)]\(<?[^)>\n]+>?\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1');
}

function codeLocationText(filePath, startLine, endLine) {
  if (!filePath) return '-';
  if (startLine == null) return filePath;
  const lineRange = endLine != null && endLine !== startLine ? `${startLine}-${endLine}` : `${startLine}`;
  return `${filePath}:${lineRange}`;
}

function normalizeCodePath(path) {
  return String(path || '')
    .replace(/\\/g, '/')
    .replace(/^[ab]\//, '')
    .replace(/^\/+/, '');
}

function findChangedFileForFinding(finding, changedFilesSummary) {
  const files = Array.isArray(changedFilesSummary?.files) ? changedFilesSummary.files : [];
  const targetPath = normalizeCodePath(finding?.filePath);
  if (!targetPath) return null;
  return files.find(file => {
    const candidates = [file.path, file.newPath, file.oldPath].map(normalizeCodePath).filter(Boolean);
    return candidates.some(candidate => (
      candidate === targetPath
      || candidate.endsWith(`/${targetPath}`)
      || targetPath.endsWith(`/${candidate}`)
    ));
  }) || null;
}

function findChangedFileForEvidence(evidence, changedFilesSummary) {
  return findChangedFileForFinding({ filePath: evidence?.filePath }, changedFilesSummary);
}

function parseUnifiedDiff(diffText) {
  const lines = String(diffText || '').split(/\r?\n/);
  const hunks = [];
  let current = null;
  let oldLine = 0;
  let newLine = 0;

  lines.forEach((line, index) => {
    if (index === lines.length - 1 && line === '') return;
    const hunkMatch = line.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/);
    if (hunkMatch) {
      current = {
        id: `hunk-${hunks.length}`,
        header: line,
        oldStart: Number(hunkMatch[1]),
        oldCount: Number(hunkMatch[2] ?? 1),
        newStart: Number(hunkMatch[3]),
        newCount: Number(hunkMatch[4] ?? 1),
        lines: []
      };
      oldLine = current.oldStart;
      newLine = current.newStart;
      hunks.push(current);
      return;
    }

    if (!current) {
      if (line.startsWith('diff --') || line.startsWith('index ') || line.startsWith('--- ') || line.startsWith('+++ ') || line === '') {
        return;
      }
      current = {
        id: 'hunk-raw',
        header: 'Diff',
        oldStart: null,
        newStart: null,
        oldCount: null,
        newCount: null,
        lines: []
      };
      hunks.push(current);
    }

    if (line.startsWith('\\')) {
      current.lines.push({ type: 'meta', text: line, oldLine: null, newLine: null });
      return;
    }
    if (line.startsWith('+') && !line.startsWith('+++')) {
      current.lines.push({ type: 'add', text: line.slice(1), oldLine: null, newLine });
      newLine += 1;
      return;
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      current.lines.push({ type: 'delete', text: line.slice(1), oldLine, newLine: null });
      oldLine += 1;
      return;
    }

    const text = line.startsWith(' ') ? line.slice(1) : line;
    current.lines.push({
      type: current.oldStart == null ? 'raw' : 'context',
      text,
      oldLine: current.oldStart == null ? null : oldLine,
      newLine: current.newStart == null ? null : newLine
    });
    if (current.oldStart != null) oldLine += 1;
    if (current.newStart != null) newLine += 1;
  });

  return hunks;
}

function buildSideBySideRows(parsedDiff, targetStartLine, targetEndLine) {
  const start = Number(targetStartLine);
  const end = Number(targetEndLine ?? targetStartLine);
  const hasTarget = Number.isFinite(start);
  const rows = [];

  parsedDiff.forEach(hunk => {
    hunk.lines.forEach((line, index) => {
      const highlight = hasTarget && line.newLine != null && line.newLine >= start && line.newLine <= end;
      rows.push({
        id: `${hunk.id}-${index}`,
        type: line.type,
        oldLine: line.oldLine ?? '',
        newLine: line.newLine ?? '',
        oldText: line.type === 'add' ? '' : line.text,
        newText: line.type === 'delete' ? '' : line.text,
        highlight
      });
    });
  });

  return rows;
}

function diffLanguageForPath(filePath) {
  const extension = String(filePath || '').split('.').pop()?.toLowerCase();
  return {
    java: 'java',
    py: 'python',
    js: 'javascript',
    jsx: 'jsx',
    ts: 'typescript',
    tsx: 'tsx',
    sql: 'sql',
    xml: 'xml',
    json: 'json',
    yml: 'yaml',
    yaml: 'yaml',
    css: 'css',
    scss: 'css',
    sh: 'shell',
    bash: 'shell',
    md: 'markdown'
  }[extension] || 'text';
}

function prismGrammarForLanguage(language) {
  const grammarName = {
    shell: 'bash',
    xml: 'markup'
  }[language] || language;
  return Prism.languages[grammarName] || null;
}

function prismTokenClassName(token) {
  const aliases = Array.isArray(token.alias) ? token.alias : token.alias ? [token.alias] : [];
  return ['token', token.type, ...aliases].join(' ');
}

function renderPrismTokens(tokens, keyPrefix = 'token') {
  return tokens.map((token, index) => {
    if (typeof token === 'string') return token;
    const content = Array.isArray(token.content)
      ? renderPrismTokens(token.content, `${keyPrefix}-${index}`)
      : token.content;
    return (
      <span key={`${keyPrefix}-${index}`} className={prismTokenClassName(token)}>
        {content}
      </span>
    );
  });
}

function SyntaxHighlightedCode({ text, language }) {
  const content = String(text || '');
  const grammar = prismGrammarForLanguage(language);
  return grammar ? renderPrismTokens(Prism.tokenize(content, grammar)) : content;
}

function hunkLineCounts(hunk) {
  return hunk.lines.reduce((counts, line) => {
    if (line.type === 'context' || line.type === 'delete') counts.oldCount += 1;
    if (line.type === 'context' || line.type === 'add') counts.newCount += 1;
    return counts;
  }, { oldCount: 0, newCount: 0 });
}

function validateParsedHunks(parsedDiff) {
  for (const hunk of parsedDiff) {
    if (hunk.oldStart == null || hunk.newStart == null) {
      return 'Patch 缺少标准 unified diff hunk 行号。';
    }
    const counts = hunkLineCounts(hunk);
    if (counts.oldCount !== hunk.oldCount || counts.newCount !== hunk.newCount) {
      return `Patch hunk 行数与头部声明不一致：${hunk.header}`;
    }
  }
  return null;
}

function sourceLineMatches(lines, lineNumber, text) {
  return !Array.isArray(lines) || lines[lineNumber - 1] === text;
}

function validateDiffAgainstSources(parsedDiff, leftLines, rightLines) {
  const hunkError = validateParsedHunks(parsedDiff);
  if (hunkError) return hunkError;
  for (const hunk of parsedDiff) {
    for (const line of hunk.lines) {
      if (
        (line.type === 'context' || line.type === 'delete')
        && !sourceLineMatches(leftLines, line.oldLine, line.text)
      ) {
        return `保存的 Diff 与左侧源码不匹配：${hunk.header}`;
      }
      if (
        (line.type === 'context' || line.type === 'add')
        && !sourceLineMatches(rightLines, line.newLine, line.text)
      ) {
        return `保存的 Diff 与右侧源码不匹配：${hunk.header}`;
      }
    }
  }
  return null;
}

function applyUnifiedDiffToLines(parsedDiff, baseLines) {
  const hunkError = validateParsedHunks(parsedDiff);
  if (hunkError) return { error: hunkError, lines: null };
  const result = [];
  let baseIndex = 0;
  for (const hunk of parsedDiff) {
    const hunkStartIndex = hunk.oldCount === 0 ? hunk.oldStart : hunk.oldStart - 1;
    if (hunkStartIndex < baseIndex || hunkStartIndex > baseLines.length) {
      return { error: `Patch hunk 行号超出当前源码范围：${hunk.header}`, lines: null };
    }
    result.push(...baseLines.slice(baseIndex, hunkStartIndex));
    baseIndex = hunkStartIndex;
    for (const line of hunk.lines) {
      if (line.type === 'meta') continue;
      if (line.type === 'add') {
        result.push(line.text);
        continue;
      }
      if (baseLines[baseIndex] !== line.text) {
        return { error: `Patch 上下文与当前源码不匹配：${hunk.header}`, lines: null };
      }
      if (line.type === 'context') result.push(line.text);
      baseIndex += 1;
    }
  }
  result.push(...baseLines.slice(baseIndex));
  return { error: null, lines: result };
}

function linesBeforeHunk(start, count, consumed) {
  return Math.max(0, start - consumed - (count === 0 ? 0 : 1));
}

function consumedAfterHunk(start, count) {
  return start + (count === 0 ? 0 : count - 1);
}

function contextRow(gap, offset, leftLines, rightLines) {
  const oldLine = gap.oldStart + offset;
  const newLine = gap.newStart + offset;
  return {
    id: `${gap.id}-context-${offset}`,
    type: 'context',
    oldLine,
    newLine,
    oldText: leftLines[oldLine - 1] ?? '',
    newText: rightLines[newLine - 1] ?? '',
    highlight: false
  };
}

function appendGapRows(rows, gap, gapExpansions, leftLines, rightLines) {
  if (gap.count <= 0) return;
  const expansion = gapExpansions[gap.id] || {};
  const topCount = Math.min(gap.count, expansion.top || 0);
  const bottomCount = Math.min(gap.count - topCount, expansion.bottom || 0);
  for (let offset = 0; offset < topCount; offset += 1) {
    rows.push(contextRow(gap, offset, leftLines, rightLines));
  }
  const hiddenCount = gap.count - topCount - bottomCount;
  if (hiddenCount > 0) {
    rows.push({
      id: `${gap.id}-collapsed`,
      type: 'gap',
      gap,
      hiddenCount
    });
  }
  for (let offset = gap.count - bottomCount; offset < gap.count; offset += 1) {
    rows.push(contextRow(gap, offset, leftLines, rightLines));
  }
}

function buildExpandedRows(parsedDiff, sourceContext, viewType, gapExpansions, targetStartLine, targetEndLine) {
  const leftLines = Array.isArray(sourceContext?.left?.lines) ? sourceContext.left.lines : [];
  let rightLines = Array.isArray(sourceContext?.right?.lines) ? sourceContext.right.lines : [];
  if (viewType === 'FIX_PREVIEW') {
    const applied = applyUnifiedDiffToLines(parsedDiff, leftLines);
    if (applied.error) return { error: applied.error, rows: null };
    rightLines = applied.lines;
  } else {
    const sourceError = validateDiffAgainstSources(
      parsedDiff,
      sourceContext?.left ? leftLines : null,
      sourceContext?.right ? rightLines : null
    );
    if (sourceError) return { error: sourceError, rows: null };
  }

  const rows = [];
  let oldConsumed = 0;
  let newConsumed = 0;
  for (const [hunkIndex, hunk] of parsedDiff.entries()) {
    const counts = hunkLineCounts(hunk);
    const oldGapCount = linesBeforeHunk(hunk.oldStart, counts.oldCount, oldConsumed);
    const newGapCount = linesBeforeHunk(hunk.newStart, counts.newCount, newConsumed);
    if (oldGapCount !== newGapCount) {
      return { error: `完整源码与 Diff 的隐藏上下文范围不一致：${hunk.header}`, rows: null };
    }
    appendGapRows(rows, {
      id: `gap-${hunkIndex}`,
      oldStart: oldConsumed + 1,
      newStart: newConsumed + 1,
      count: oldGapCount
    }, gapExpansions, leftLines, rightLines);
    rows.push(...buildSideBySideRows([hunk], targetStartLine, targetEndLine));
    oldConsumed = consumedAfterHunk(hunk.oldStart, counts.oldCount);
    newConsumed = consumedAfterHunk(hunk.newStart, counts.newCount);
  }
  const oldTailCount = leftLines.length - oldConsumed;
  const newTailCount = rightLines.length - newConsumed;
  if (oldTailCount !== newTailCount) {
    return { error: '完整源码与 Diff 的隐藏上下文范围不一致。', rows: null };
  }
  appendGapRows(rows, {
    id: 'gap-tail',
    oldStart: oldConsumed + 1,
    newStart: newConsumed + 1,
    count: oldTailCount
  }, gapExpansions, leftLines, rightLines);
  return { error: null, rows };
}

const focusIndicatorMeta = {
  DB_SCHEMA_CHANGE: { label: 'DB 表/字段', color: 'default' },
  MQ_CONFIG_CHANGE: { label: 'MQ 配置', color: 'gold' },
  REDIS_CONFIG_CHANGE: { label: 'Redis 配置', color: 'red' },
  VALUE_CONFIG_CHANGE: { label: '@Value', color: 'blue' }
};

const focusIndicatorOrder = [
  'DB_SCHEMA_CHANGE',
  'MQ_CONFIG_CHANGE',
  'REDIS_CONFIG_CHANGE',
  'VALUE_CONFIG_CHANGE'
];

function orderedFocusIndicators(indicators = []) {
  const byCode = new Map((Array.isArray(indicators) ? indicators : []).map(item => [item.code, item]));
  return focusIndicatorOrder.map(code => ({
    code,
    name: focusIndicatorMeta[code]?.label || byCode.get(code)?.name || code,
    matched: false,
    evidences: [],
    sourceChangeTypes: [],
    ...(byCode.get(code) || {})
  }));
}

function changeTypeLabel(value) {
  const labels = {
    API: '接口',
    DB: '数据库',
    DB_SCHEMA: 'DB 表结构',
    DB_SQL: 'SQL',
    ORM_MAPPING: 'ORM/MyBatis 映射',
    ENTITY_MODEL: '实体模型',
    DATA_MIGRATION: '数据迁移',
    CACHE: '缓存',
    CACHE_KEY: '缓存 Key',
    CACHE_TTL: '缓存 TTL',
    CACHE_INVALIDATION: '缓存失效',
    CACHE_READ_WRITE: '缓存读写',
    CACHE_SERIALIZATION: '缓存序列化',
    MQ: 'MQ',
    MQ_PRODUCER: 'MQ 生产者',
    MQ_CONSUMER: 'MQ 消费者',
    MQ_MESSAGE_SCHEMA: 'MQ 消息结构',
    MQ_TOPIC_CONFIG: 'MQ Topic/消费组配置',
    MQ_RETRY_DLQ: 'MQ 重试/死信',
    CONFIG: '配置'
  };
  return labels[value] || value || '-';
}

function focusIndicatorReasonText(item, meta) {
  if (item.reason && !/^Matched by|^No .* signal matched|^No @Value/i.test(item.reason)) {
    return item.reason;
  }
  const label = meta?.label || item.name || '该类变更';
  if (!item.matched) return `未命中${label}信号。`;
  const types = (item.sourceChangeTypes || []).map(changeTypeLabel).join('、');
  if (item.code === 'VALUE_CONFIG_CHANGE') return '命中 @Value 配置占位符变更。';
  return types ? `命中变更类型：${types}。` : `命中${label}信号。`;
}

function riskCardSummaryText(riskCard, riskItems) {
  if (!riskCard) return '-';
  if (riskItems.length === 0) return '未命中需要关注的变更提醒。';
  const groups = buildReminderGroups(riskItems).map(group => group.label);
  return `本次重点提醒涉及 ${groups.join('、')}，共 ${riskItems.length} 条提醒。`;
}

function reminderGroupKey(category) {
  if (['DB', 'DB_DATA_WRITE', 'DB_SCHEMA', 'DB_SQL', 'ORM_MAPPING', 'ENTITY_MODEL', 'DATA_MIGRATION'].includes(category)) return 'DB';
  if (['MQ', 'MQ_CONFIG', 'MQ_PRODUCER', 'MQ_CONSUMER', 'MQ_MESSAGE_SCHEMA', 'MQ_TOPIC_CONFIG', 'MQ_RETRY_DLQ'].includes(category)) return 'MQ';
  if (['CACHE', 'CACHE_WRITE_DELETE', 'CACHE_KEY', 'CACHE_TTL', 'CACHE_INVALIDATION', 'CACHE_READ_WRITE', 'CACHE_SERIALIZATION'].includes(category)) return 'CACHE';
  if (category === 'CONFIG') return 'CONFIG';
  return category || 'OTHER';
}

const reminderGroupMeta = {
  DB: { label: 'DB', titleColor: '#526a7a', sort: 1 },
  MQ: { label: 'MQ', titleColor: '#d48806', sort: 2 },
  CACHE: { label: 'Redis', titleColor: '#cf1322', sort: 3 },
  CONFIG: { label: 'Nacos', titleColor: '#1677ff', sort: 4 },
  OTHER: { label: '其他提醒', titleColor: '#595959', sort: 99 }
};

function buildReminderGroups(riskItems) {
  const groups = new Map();
  for (const item of riskItems) {
    const key = reminderGroupKey(item.category);
    const meta = reminderGroupMeta[key] || {
      label: `${changeTypeLabel(item.category)}提醒`,
      titleColor: '#595959',
      sort: 90
    };
    if (!groups.has(key)) {
      groups.set(key, { key, ...meta, items: [], categories: new Set() });
    }
    groups.get(key).items.push(item);
    if (item.category) groups.get(key).categories.add(item.category);
  }
  return [...groups.values()]
    .map(group => ({ ...group, categories: [...group.categories] }))
    .sort((a, b) => a.sort - b.sort || a.label.localeCompare(b.label));
}

function FocusIndicatorPanel({ indicators }) {
  const items = orderedFocusIndicators(indicators);
  return (
    <Card title="重点变更">
      <div className="focus-indicator-grid">
        {items.map(item => {
          const meta = focusIndicatorMeta[item.code] || {};
          const evidenceFiles = [...new Set((item.evidences || []).map(evidence => evidence.filePath).filter(Boolean))];
          return (
            <div key={item.code} className={`focus-indicator ${item.matched ? 'is-matched' : ''}`}>
              <div className="focus-indicator-head">
                <Text strong>{meta.label || item.name}</Text>
                <Space size={4} wrap>
                  <Tag color={item.matched ? meta.color : 'default'}>{item.matched ? '命中' : '未命中'}</Tag>
                </Space>
              </div>
              <Text type={item.matched ? undefined : 'secondary'} className="focus-indicator-reason">
                {focusIndicatorReasonText(item, meta)}
              </Text>
              <Space wrap size={[4, 4]}>
                {(item.sourceChangeTypes || []).map(type => <Tag key={type}>{changeTypeLabel(type)}</Tag>)}
                {evidenceFiles.slice(0, 3).map(file => <Tag key={file} title={file} className="path-tag">{file}</Tag>)}
              </Space>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function schedulerStatusColor(status) {
  return {
    QUEUED: 'default',
    RUNNING: 'processing',
    SUCCESS: 'success',
    FAILED: 'error',
    SKIPPED: 'warning'
  }[status] || 'default';
}

function schedulerStatusLabel(status) {
  return {
    QUEUED: '排队中',
    RUNNING: '运行中',
    SUCCESS: '已完成',
    FAILED: '失败',
    SKIPPED: '已跳过'
  }[status] || status || '-';
}

function jobDurationText(job) {
  const start = parseEventTime(job?.startedAt || job?.queuedAt);
  const end = parseEventTime(job?.finishedAt || job?.updatedAt);
  if (!start || !end) return '-';
  return formatDuration(Math.max(0, (end - start) / 1000));
}

function JobQueueModal({ open, queue, onClose, onOpenTask, onCancelJob }) {
  const groups = Array.isArray(queue?.groups) ? queue.groups : [];
  const canCancelJob = job => ['QUEUED', 'RUNNING'].includes(job?.status);
  const reviewColumns = [
    {
      title: '模型',
      width: 180,
      render: (_, row) => row.displayName || row.provider || row.label || '-'
    },
    { title: 'Provider', dataIndex: 'provider', width: 120, render: value => value || '-' },
    { title: 'Model', dataIndex: 'model', width: 180, ellipsis: true, render: value => value || '-' },
    { title: 'Review Key', dataIndex: 'reviewKey', width: 150, ellipsis: true, render: value => value || '-' },
    { title: '状态', dataIndex: 'status', width: 100, render: value => <Tag color={schedulerStatusColor(value)}>{schedulerStatusLabel(value)}</Tag> },
    { title: '排队时间', dataIndex: 'queuedAt', width: 170, render: value => value || '-' },
    { title: '开始时间', dataIndex: 'startedAt', width: 170, render: value => value || '-' },
    { title: '耗时', width: 90, render: (_, row) => jobDurationText(row) },
    { title: '错误', dataIndex: 'errorMessage', ellipsis: true, render: value => value || '-' },
    {
      title: '操作',
      width: 150,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => onOpenTask?.(row.taskId)}>详情</Button>
          {canCancelJob(row) && (
            <Button danger type="link" size="small" onClick={() => onCancelJob?.(row)}>中断</Button>
          )}
        </Space>
      )
    }
  ];
  const fixColumns = [
    { title: '风险点', dataIndex: 'findingIndex', width: 90, render: value => value == null ? '-' : `#${value}` },
    { title: '文件', dataIndex: 'filePath', ellipsis: true, render: value => value || '-' },
    { title: '状态', dataIndex: 'status', width: 100, render: value => <Tag color={schedulerStatusColor(value)}>{schedulerStatusLabel(value)}</Tag> },
    { title: '排队时间', dataIndex: 'queuedAt', width: 170, render: value => value || '-' },
    { title: '开始时间', dataIndex: 'startedAt', width: 170, render: value => value || '-' },
    { title: '耗时', width: 90, render: (_, row) => jobDurationText(row) },
    { title: '错误', dataIndex: 'errorMessage', ellipsis: true, render: value => value || '-' },
    {
      title: '操作',
      width: 120,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => onOpenTask?.(row.taskId)}>详情</Button>
          {canCancelJob(row) && (
            <Button danger type="link" size="small" onClick={() => onCancelJob?.(row)}>中断</Button>
          )}
        </Space>
      )
    }
  ];
  return (
    <Modal title="AI Review 调度队列" open={open} onCancel={onClose} footer={null} width="min(1100px, 96vw)">
      <div className="bounded-modal-scroll">
        {groups.length === 0 ? (
          <Empty description="暂无调度任务" />
        ) : (
          <Collapse
            items={groups.map(group => {
              const reviewJobs = Array.isArray(group.reviewJobs) ? group.reviewJobs : (group.reviewJob ? [group.reviewJob] : []);
              const activeReviewCount = reviewJobs.filter(job => ['QUEUED', 'RUNNING'].includes(job.status)).length;
              const activeFixCount = (group.fixPreviewJobs || []).filter(job => ['QUEUED', 'RUNNING'].includes(job.status)).length;
              return {
                key: group.taskId,
                label: (
                  <Space wrap>
                    <Text strong>任务 #{group.taskId}</Text>
                    <Text>{group.projectName || '-'}</Text>
                    {reviewJobs.length > 0 && (
                      <Tag color={activeReviewCount > 0 ? 'processing' : 'default'}>
                        Review {reviewJobs.length} 个{activeReviewCount > 0 ? `，${activeReviewCount} 个进行中` : ''}
                      </Tag>
                    )}
                    {activeFixCount > 0 && <Tag color="processing">修复预览 {activeFixCount} 个进行中</Tag>}
                  </Space>
                ),
                children: (
                  <Space direction="vertical" className="full-width">
                    {reviewJobs.length > 0 ? (
                      <>
                        <Descriptions
                          size="small"
                          column={2}
                          items={[
                            { key: 'triggerType', label: '触发类型', children: group.triggerType || '-' },
                            { key: 'branch', label: '分支', children: taskListBranchText(group) }
                          ]}
                        />
                        <Table
                          size="small"
                          rowKey="id"
                          columns={reviewColumns}
                          dataSource={reviewJobs}
                          pagination={false}
                          scroll={{ x: 1250 }}
                        />
                      </>
                    ) : (
                      <div className="job-queue-review-row">
                        <Alert className="job-queue-review-descriptions" type="info" showIcon message="该任务当前只有修复预览调度记录" />
                        <Button type="link" onClick={() => onOpenTask?.(group.taskId)}>查看任务详情</Button>
                      </div>
                    )}
                    <Table
                      size="small"
                      rowKey="id"
                      columns={fixColumns}
                      dataSource={group.fixPreviewJobs || []}
                      pagination={false}
                    />
                  </Space>
                )
              };
            })}
          />
        )}
      </div>
    </Modal>
  );
}

function FailureNotificationsModal({ open, notifications, onClose, onOpenTask }) {
  const items = Array.isArray(notifications?.items) ? notifications.items : [];
  const columns = [
    {
      title: '任务',
      dataIndex: 'taskId',
      width: 90,
      render: value => value ? `#${value}` : '-'
    },
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    { title: '触发类型', dataIndex: 'triggerType', width: 120, render: value => taskTypeLabel(value) },
    { title: '分支', width: 220, ellipsis: true, render: (_, row) => taskListBranchText(row) },
    {
      title: 'Provider',
      dataIndex: 'provider',
      width: 130,
      render: value => value ? sourceLabel(value) : '-'
    },
    { title: '失败原因', dataIndex: 'errorMessage', width: 260, ellipsis: true, render: value => value || '-' },
    { title: '失败时间', dataIndex: 'createdAt', width: 170, render: value => value || '-' },
    {
      title: '操作',
      width: 90,
      render: (_, row) => <Button type="link" size="small" onClick={() => onOpenTask?.(row.taskId)}>详情</Button>
    }
  ];
  return (
    <Modal
      title="AI Review 失败通知"
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(1180px, 96vw)"
    >
      <div className="bounded-modal-scroll">
        {items.length === 0 ? (
          <Empty description="最近 24 小时暂无 AI Review 执行失败" />
        ) : (
          <Table
            size="small"
            rowKey="id"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 1120 }}
          />
        )}
      </div>
    </Modal>
  );
}

const artifactTypeLabels = {
  SQL: 'SQL',
  REDIS_COMMAND: 'Redis 命令',
  MQ_CONFIG_CODE: 'MQ 配置',
  NACOS_CONFIG: 'Nacos 配置'
};

function artifactLanguageLabel(language) {
  return {
    sql: 'SQL',
    text: 'TEXT',
    java: 'JAVA',
    yaml: 'YAML',
    properties: 'PROPERTIES'
  }[language] || String(language || 'TEXT').toUpperCase();
}

function artifactCodeClassName(artifact) {
  const language = artifact?.language;
  return [
    'maintenance-artifact-code',
    ['java', 'sql', 'yaml'].includes(language) ? 'maintenance-artifact-code-dark' : '',
    language === 'java' ? 'maintenance-artifact-code-java' : '',
    language === 'sql' ? 'maintenance-artifact-code-sql' : '',
    language === 'yaml' ? 'maintenance-artifact-code-yaml' : ''
  ]
    .filter(Boolean)
    .join(' ');
}

function renderArtifactCode(artifact) {
  const content = String(artifact?.content || '');
  const tokenPattern = artifact?.language === 'java'
    ? /(\/\/.*|"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|@\w+|\b(?:public|private|protected|return|new|class|interface|void|static|final|true|false|null)\b|\b(?:Queue|Binding|TopicExchange|DirectExchange|FanoutExchange|HeadersExchange|CustomExchange|BindingBuilder)\b)/g
    : artifact?.language === 'sql'
      ? /(--.*|\/\*[\s\S]*?\*\/|"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|\b(?:CREATE|ALTER|DROP|TABLE|PRIMARY|KEY|NOT|NULL|DEFAULT|COMMENT|INDEX|UNIQUE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|FROM|SELECT|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|INT|BIGINT|VARCHAR|CHAR|TEXT|DATETIME|TIMESTAMP|DECIMAL|BOOLEAN|TINYINT|AUTO_INCREMENT)\b)/gi
      : artifact?.language === 'yaml'
        ? /(#.*|"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|\b(?:true|false|null)\b|^[ \t-]*[A-Za-z0-9_.-]+(?=\s*:))/gim
        : null;
  if (!tokenPattern) return content;
  const lines = content.split('\n');
  return lines.flatMap((line, lineIndex) => {
    const parts = [];
    let lastIndex = 0;
    for (const match of line.matchAll(tokenPattern)) {
      if (match.index > lastIndex) parts.push(line.slice(lastIndex, match.index));
      const token = match[0];
      const className = token.startsWith('//')
        || token.startsWith('--')
        || token.startsWith('/*')
        || token.startsWith('#')
        ? 'code-token-comment'
        : token.startsWith('"') || token.startsWith("'")
          ? 'code-token-string'
          : token.startsWith('@')
            ? 'code-token-annotation'
            : artifact?.language === 'yaml' && /^[ \t-]*[A-Za-z0-9_.-]+$/.test(token)
              ? 'code-token-type'
            : artifact?.language === 'java' && /^[A-Z]/.test(token)
              ? 'code-token-type'
              : 'code-token-keyword';
      parts.push(<span key={`${lineIndex}-${match.index}`} className={className}>{token}</span>);
      lastIndex = match.index + token.length;
    }
    if (lastIndex < line.length) parts.push(line.slice(lastIndex));
    if (lineIndex < lines.length - 1) parts.push('\n');
    return parts;
  });
}

async function copyTextToClipboard(text, successMessage = '已复制可维护内容') {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success(successMessage);
  } catch (err) {
    message.error(err?.message || '复制失败');
  }
}

function MaintenanceArtifacts({ artifacts }) {
  const items = Array.isArray(artifacts) ? artifacts.filter(item => item?.content) : [];
  if (items.length === 0) return null;
  return (
    <Space direction="vertical" size="small" className="full-width">
      {items.map((artifact, index) => (
        <div key={`${artifact.artifactType}-${artifact.sourceFilePath}-${index}`} className="maintenance-artifact">
          <div className="maintenance-artifact-head">
            <Space wrap size={[6, 6]}>
              <Text strong>{artifact.title || artifactTypeLabels[artifact.artifactType] || '维护内容'}</Text>
              <Tag color="blue">{artifactTypeLabels[artifact.artifactType] || artifact.artifactType}</Tag>
              <Tag>{artifactLanguageLabel(artifact.language)}</Tag>
              <Tag color={artifact.confidence === 'EXACT' ? 'green' : 'gold'}>{artifact.confidence || 'INFERRED'}</Tag>
            </Space>
            {artifact.copyable && (
              <Tooltip title="复制">
                <Button
                  icon={<CopyOutlined />}
                  size="small"
                  onClick={() => copyTextToClipboard(artifact.content)}
                />
              </Tooltip>
            )}
          </div>
          <pre className={artifactCodeClassName(artifact)}>{renderArtifactCode(artifact)}</pre>
          <Space wrap size={[4, 4]}>
            {artifact.sourceFilePath && <Tag className="path-tag">{artifact.sourceFilePath}</Tag>}
            {artifact.sourceChangeType && <Tag>{changeTypeLabel(artifact.sourceChangeType)}</Tag>}
          </Space>
          {artifact.notes && <Text type="secondary" className="maintenance-artifact-notes">{artifact.notes}</Text>}
        </div>
      ))}
    </Space>
  );
}

function TaskList({ onOpen }) {
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [groups, setGroups] = useState([]);
  const [projects, setProjects] = useState([]);
  const [groupId, setGroupId] = useState(null);
  const [projectId, setProjectId] = useState(null);
  const [targetType, setTargetType] = useState(null);
  const [triggerType, setTriggerType] = useState(null);
  const [reviewStatuses, setReviewStatuses] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [error, setError] = useState(null);

  const load = async (next = {}) => {
    const pageNo = next.pageNo ?? pagination.pageNo;
    const pageSize = next.pageSize ?? pagination.pageSize;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ pageNo, pageSize });
      if (keyword.trim()) params.set('keyword', keyword.trim());
      if (groupId) params.set('groupId', groupId);
      if (projectId) params.set('projectId', projectId);
      if (targetType) params.set('targetType', targetType);
      if (triggerType) params.set('triggerType', triggerType);
      reviewStatuses.forEach(value => params.append('reviewStatus', value));
      const data = await fetchApi(`/api/review-tasks?${params.toString()}`);
      setTasks(data.items || []);
      setPagination({ pageNo: data.pageNo, pageSize: data.pageSize, total: data.total });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    Promise.all([
      fetchApi('/api/project-groups'),
      fetchApi('/api/projects')
    ]).then(([groupData, projectData]) => {
      setGroups(groupData.items || []);
      setProjects(projectData.items || []);
    }).catch(err => setError(err.message));
    load({ pageNo: 1 });
  }, []);

  const projectScopeValue = groupId ? (projectId ? [groupId, projectId] : [groupId]) : undefined;
  const projectScopeOptions = useMemo(() => groups.map(group => {
    const childProjects = projects
      .filter(project => project.groupId === group.id)
      .map(project => ({ label: project.name, value: project.id }));
    return {
      label: group.groupName,
      value: group.id,
      ...(childProjects.length ? { children: childProjects } : {})
    };
  }), [groups, projects]);

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 64 },
    { title: '项目组', dataIndex: 'groupId', width: 120, ellipsis: true, render: value => groups.find(group => group.id === value)?.groupName || '-' },
    { title: '项目', dataIndex: 'projectName', width: 170, ellipsis: true },
    {
      title: '作者',
      width: 90,
      ellipsis: true,
      render: (_, row) => <Text ellipsis>{row.authorName || row.authorUsername || '-'}</Text>
    },
    { title: '端类型', dataIndex: 'targetType', width: 96, render: value => <Tag>{targetTypeLabel(value)}</Tag> },
    { title: '类型', dataIndex: 'triggerType', width: 76, render: value => <Tag>{taskTypeLabel(value)}</Tag> },
    { title: '分支', width: 175, ellipsis: true, render: (_, row) => <Text ellipsis>{taskListBranchText(row)}</Text> },
    { title: '状态', dataIndex: 'reviewStatus', width: 95, render: value => <Tag color={taskReviewStatusColor(value)}>{taskReviewStatusLabel(value)}</Tag> },
    { title: '风险点', dataIndex: 'riskItemCount', width: 72, render: value => value ?? 0 },
    { title: '创建时间', dataIndex: 'createdAt', width: 125, ellipsis: true },
    { title: '操作', width: 70, render: (_, row) => <Button type="link" onClick={() => onOpen(row.id)}>详情</Button> }
  ];

  return (
    <div className="page-shell">
      <div className="page-heading">
        <Space>
          <Cascader
            allowClear
            changeOnSelect
            showSearch={{ filter: (inputValue, path) => path.some(option => String(option.label).toLowerCase().includes(inputValue.toLowerCase())) }}
            className="task-project-scope-cascader"
            placeholder="项目组 / 项目"
            value={projectScopeValue}
            options={projectScopeOptions}
            onChange={value => {
              setGroupId(value?.[0] || null);
              setProjectId(value?.[1] || null);
            }}
          />
          <Select
            allowClear
            className="task-filter-select"
            placeholder="端类型"
            value={targetType}
            options={TARGET_TYPE_OPTIONS}
            onChange={value => setTargetType(value || null)}
          />
          <Select
            allowClear
            className="task-filter-select"
            placeholder="类型"
            value={triggerType}
            options={TASK_TRIGGER_TYPE_OPTIONS}
            onChange={value => setTriggerType(value || null)}
          />
          <Select
            allowClear
            mode="multiple"
            className="task-filter-select"
            placeholder="审查状态"
            value={reviewStatuses}
            options={TASK_REVIEW_STATUS_OPTIONS}
            onChange={value => setReviewStatuses(value || [])}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="项目、分支或任务"
            value={keyword}
            onChange={event => setKeyword(event.target.value)}
            onPressEnter={() => load({ pageNo: 1 })}
          />
          <Button type="primary" onClick={() => load({ pageNo: 1 })}>搜索</Button>
        </Space>
      </div>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={tasks}
          tableLayout="fixed"
          pagination={{
            current: pagination.pageNo,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showTotal: total => `共 ${total} 条`,
            onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
          }}
        />
      </Card>
    </div>
  );
}

function ReviewFeedbackControl({
  taskId,
  sourceType,
  itemFingerprint,
  feedback,
  payload,
  compact = false
}) {
  const [localFeedback, setLocalFeedback] = useState(feedback || null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    feedbackType: 'USEFUL',
    reasonType: 'OTHER',
    reasonText: '',
    missingContextTypes: [],
    suggestAsProjectRule: false
  });

  useEffect(() => {
    setLocalFeedback(feedback || null);
  }, [feedback?.id, feedback?.feedbackType, feedback?.status, feedback?.missingContextTypes]);

  if (!REVIEW_LEARNING_UI_ENABLED) return null;

  const openModal = feedbackType => {
    const defaultReasonType = defaultReasonTypeForFeedback(feedbackType);
    setDraft({
      feedbackType,
      reasonType: defaultReasonType,
      reasonText: localFeedback?.reasonText || '',
      missingContextTypes: defaultReasonType === 'CONTEXT_MISSING' ? (localFeedback?.missingContextTypes || []) : [],
      suggestAsProjectRule: localFeedback?.suggestAsProjectRule || false
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!taskId || !itemFingerprint) return;
    setSubmitting(true);
    try {
      const nextFeedback = await fetchApi(`/api/review-tasks/${taskId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          sourceType,
          itemFingerprint,
          ...payload,
          ...draft,
          missingContextTypes: draft.reasonType === 'CONTEXT_MISSING' ? draft.missingContextTypes : [],
          suggestAsProjectRule: PROJECT_REVIEW_POLICY_UI_ENABLED ? draft.suggestAsProjectRule : false
        })
      });
      setLocalFeedback(nextFeedback);
      setModalOpen(false);
      message.success('反馈已保存');
    } catch (err) {
      message.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const buttons = [
    ['USEFUL', '有用'],
    ['FALSE_POSITIVE', '误判'],
    ['LEVEL_TOO_HIGH', '等级过高'],
    ['DUPLICATE', '重复'],
    ['FIXED', '已修复']
  ];

  return (
    <div className={compact ? 'feedback-control feedback-control-compact' : 'feedback-control'}>
      <Space wrap>
        {localFeedback && (
          <>
            <Tag color={reviewFeedbackTypeColor(localFeedback.feedbackType)}>
              {reviewFeedbackTypeLabel(localFeedback.feedbackType)}
            </Tag>
            <Tag color={reviewFeedbackStatusColor(localFeedback.status)}>
              {reviewFeedbackStatusLabel(localFeedback.status)}
            </Tag>
            {(localFeedback.missingContextTypes || []).map(item => (
              <Tag key={item} color="orange">{missingContextLabel(item)}</Tag>
            ))}
          </>
        )}
        {buttons.map(([value, label]) => (
          <Button
            key={value}
            size="small"
            disabled={!taskId || !itemFingerprint}
            onClick={() => openModal(value)}
          >
            {label}
          </Button>
        ))}
      </Space>
      <Modal
        title="提交反馈"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" className="full-width">
          <Select
            className="full-width"
            value={draft.feedbackType}
            options={REVIEW_FEEDBACK_TYPE_OPTIONS}
            onChange={value => setDraft(current => ({
              ...current,
              feedbackType: value,
              reasonType: defaultReasonTypeForFeedback(value),
              missingContextTypes: []
            }))}
          />
          <Select
            className="full-width"
            value={draft.reasonType}
            options={REVIEW_FEEDBACK_REASON_OPTIONS}
            onChange={value => setDraft(current => ({
              ...current,
              reasonType: value,
              missingContextTypes: value === 'CONTEXT_MISSING' ? current.missingContextTypes : []
            }))}
          />
          {draft.reasonType === 'CONTEXT_MISSING' && (
            <Select
              mode="multiple"
              allowClear
              className="full-width"
              placeholder="选择缺失的上下文"
              value={draft.missingContextTypes}
              options={MISSING_CONTEXT_TYPE_OPTIONS}
              onChange={value => setDraft(current => ({ ...current, missingContextTypes: value }))}
            />
          )}
          <Input.TextArea
            value={draft.reasonText}
            rows={4}
            maxLength={4000}
            placeholder="补充说明"
            onChange={event => setDraft(current => ({ ...current, reasonText: event.target.value }))}
          />
          {PROJECT_REVIEW_POLICY_UI_ENABLED && (
            <Switch
              checked={draft.suggestAsProjectRule}
              checkedChildren="沉淀"
              unCheckedChildren="不沉淀"
              onChange={checked => setDraft(current => ({ ...current, suggestAsProjectRule: checked }))}
            />
          )}
        </Space>
      </Modal>
    </div>
  );
}

function EvaluationCaseControl({ taskId, review, finding, compact = false }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savedCase, setSavedCase] = useState(null);
  const [draft, setDraft] = useState({
    verdict: 'UNKNOWN',
    humanComment: ''
  });
  const fingerprint = finding?.fingerprint;
  const disabled = !taskId || !fingerprint;

  const openModal = () => {
    setDraft({
      verdict: savedCase?.verdict || 'UNKNOWN',
      humanComment: savedCase?.humanComment || ''
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (disabled) return;
    setSubmitting(true);
    try {
      const created = await fetchApi('/api/evaluation-cases', {
        method: 'POST',
        body: JSON.stringify({
          source: 'AI_FINDING',
          taskId,
          reviewKey: review?.reviewKey,
          fingerprint,
          findingId: finding?.findingId || finding?.id || null,
          provider: review?.provider || finding?.source || null,
          profile: review?.profileCode || null,
          riskType: finding?.category || null,
          severity: finding?.severity || null,
          contextStatus: finding?.contextStatus || null,
          verdict: draft.verdict,
          humanComment: draft.humanComment
        })
      });
      setSavedCase(created);
      setModalOpen(false);
      message.success('评估样本已保存');
    } catch (err) {
      message.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={compact ? 'feedback-control feedback-control-compact' : 'feedback-control'}>
      <Space wrap>
        {savedCase && (
          <Tag color={evaluationCaseVerdictColor(savedCase.verdict)}>
            样本：{evaluationCaseVerdictLabel(savedCase.verdict)}
          </Tag>
        )}
        <Tooltip title={disabled ? '该 finding 缺少 fingerprint，无法定位原始结果' : '保存为 Review 质量评估样本'}>
          <span>
            <Button
              size="small"
              icon={<PlusOutlined />}
              disabled={disabled}
              onClick={openModal}
            >
              标注评估样本
            </Button>
          </span>
        </Tooltip>
      </Space>
      <Modal
        title="标注评估样本"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        confirmLoading={submitting}
        okText="保存样本"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle" className="full-width">
          <Alert
            type="info"
            showIcon
            message="评估样本只用于后续质量评估"
            description="不会修改原 AI Review 结果，不会创建反馈池记录，不会生成项目策略，也不会触发模型回放。"
          />
          <Select
            className="full-width"
            value={draft.verdict}
            options={EVALUATION_CASE_VERDICT_OPTIONS}
            onChange={value => setDraft(current => ({ ...current, verdict: value }))}
          />
          <Input.TextArea
            value={draft.humanComment}
            rows={4}
            maxLength={4000}
            placeholder="填写人工说明，例如为什么是误判、等级偏差或上下文不足"
            onChange={event => setDraft(current => ({ ...current, humanComment: event.target.value }))}
          />
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="任务">{taskId}</Descriptions.Item>
            <Descriptions.Item label="Review Key">{review?.reviewKey || '-'}</Descriptions.Item>
            <Descriptions.Item label="Provider">{review?.provider || finding?.source || '-'}</Descriptions.Item>
            <Descriptions.Item label="Profile">{review?.profileCode || '-'}</Descriptions.Item>
            <Descriptions.Item label="风险类型">{categoryLabel(finding?.category)}</Descriptions.Item>
            <Descriptions.Item label="等级">{severityLabel(finding?.severity)}</Descriptions.Item>
            <Descriptions.Item label="上下文">{contextStatusLabel(finding?.contextStatus)}</Descriptions.Item>
            <Descriptions.Item label="Fingerprint"><Text code>{fingerprint || '-'}</Text></Descriptions.Item>
          </Descriptions>
        </Space>
      </Modal>
    </div>
  );
}

function RiskCardView({ taskId, riskCard }) {
  const location = useLocation();
  const [activeReminderItemKeys, setActiveReminderItemKeys] = useState([]);

  const riskItems = useMemo(
    () => (riskCard?.riskItems || []).filter(item => item.ruleCode !== 'API_COMPATIBILITY_CHECK' && item.category !== 'API'),
    [riskCard]
  );
  const reminderGroups = useMemo(() => buildReminderGroups(riskItems), [riskItems]);
  const reminderItems = useMemo(
    () => reminderGroups.flatMap(group => group.items.map(item => ({ ...item, reminderGroup: group }))),
    [reminderGroups]
  );
  const firstReminderItemKey = reminderItems[0]?.riskId;

  useEffect(() => {
    if (!riskCard) return;
    setActiveReminderItemKeys(firstReminderItemKey ? [firstReminderItemKey] : []);
  }, [riskCard, firstReminderItemKey]);

  useEffect(() => {
    if (!riskCard) return;
    const match = /^#risk-item-(.+)$/.exec(location.hash || '');
    if (!match) return;
    const riskId = decodeURIComponent(match[1]);
    if (!reminderItems.some(item => item.riskId === riskId)) return;
    setActiveReminderItemKeys(current => current.includes(riskId) ? current : [...current, riskId]);
    window.setTimeout(() => {
      document.getElementById(`risk-item-${riskId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 180);
  }, [location.hash, riskCard, reminderItems]);

  if (!riskCard) return <Empty description="暂无提醒卡片" />;

  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card title="提醒项">
        {reminderItems.length === 0 ? (
          <Empty description="暂无提醒项" />
        ) : <Collapse
          className="reminder-item-list"
          key={riskCard.cardId || firstReminderItemKey || 'reminder-items'}
          activeKey={activeReminderItemKeys}
          onChange={keys => setActiveReminderItemKeys(Array.isArray(keys) ? keys : [keys].filter(Boolean))}
          items={reminderItems.map(item => ({
            key: item.riskId,
            label: (
              <Space className="risk-item-heading" wrap>
                <Text strong style={{ color: item.reminderGroup?.titleColor || '#595959' }}>
                  {item.reminderGroup?.label || changeTypeLabel(item.category)}
                </Text>
              </Space>
            ),
            children: (
              <div id={`risk-item-${item.riskId}`} className="reminder-item-content">
                <MaintenanceArtifacts artifacts={item.maintenanceArtifacts} />
                {(!Array.isArray(item.maintenanceArtifacts) || item.maintenanceArtifacts.filter(artifact => artifact?.content).length === 0) && (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可维护内容" />
                )}
                <ReviewFeedbackControl
                  taskId={taskId}
                  sourceType="RULE_REMINDER"
                  itemFingerprint={item.feedbackKey}
                  feedback={item.feedback}
                  payload={{
                    cardId: riskCard.cardId,
                    riskId: item.riskId,
                    riskType: item.category || item.ruleCode,
                    riskTitle: item.title,
                    originalRiskLevel: item.riskLevel
                  }}
                />
              </div>
            )
          }))}
        />}
      </Card>
    </Space>
  );
}

function AnalysisView({ changeAnalysis }) {
  if (!changeAnalysis) return <Empty description="暂无分析结果" />;
  const files = changeAnalysis.changedFiles || [];
  const resources = changeAnalysis.impactedResources || [];
  const changeTypes = changeAnalysis.changeTypes || [];
  const summary = `本次分析 ${files.length} 个变更文件，命中变更类型：${changeTypes.map(changeTypeLabel).join('、') || '无'}。`;
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Paragraph>{summary}</Paragraph>
        <Space wrap>{changeTypes.map(type => <Tag color="blue" key={type}>{changeTypeLabel(type)}</Tag>)}</Space>
      </Card>
      <Card title="变更文件">
        <Table
          rowKey={(row, index) => `${row.path}-${index}`}
          size="small"
          dataSource={files}
          pagination={false}
          columns={[
            { title: '文件', dataIndex: 'path', ellipsis: true },
            { title: '变更', dataIndex: 'changeType', width: 120 },
            { title: '命中类型', dataIndex: 'matchedChangeTypes', width: 220, render: values => <Space wrap>{(values || []).map(value => <Tag key={value}>{value}</Tag>)}</Space> }
          ]}
        />
      </Card>
      <Card title="影响资源">
        <Table
          rowKey={(row, index) => `${row.resourceType}-${row.name}-${index}`}
          size="small"
          dataSource={resources}
          pagination={false}
          columns={[
            { title: '类型', dataIndex: 'resourceType', width: 130 },
            { title: '名称', dataIndex: 'name', ellipsis: true },
            { title: '文件', dataIndex: 'filePath', ellipsis: true }
          ]}
        />
      </Card>
    </Space>
  );
}

function progressColor(level) {
  if (level === 'ERROR') return 'red';
  if (level === 'WARN') return 'orange';
  if (level === 'DEBUG') return 'blue';
  return 'green';
}

function phaseLabel(phase) {
  const labels = {
    QUEUED: '已排队',
    STARTED: '已启动',
    REQUEST_BUILT: '请求已构建',
    PROVIDER_SELECTED: '已选择 Provider',
    REQUEST_VALIDATED: '请求校验',
    CONTEXT_PACK_BUILT: '上下文包已构建',
    LOCAL_REPO_PREPARED: '本地仓库已准备',
    LOCAL_REPO_PREPARE_FAILED: '本地仓库不可用',
    LOCAL_CONTEXT_RETRIEVED: '本地引用检索完成',
    LOCAL_CONTEXT_RETRIEVE_FAILED: '本地引用检索不可用',
    PROVIDER_START: '调用 Provider',
    PROVIDER_FAILED: 'Provider 调用失败',
    CODEX_REPOSITORY: '确认仓库（历史）',
    PROMPT_METADATA: 'Prompt 元数据',
    CODEX_OUTPUT_FILE: '准备输出文件（历史）',
    CODEX_COMMAND: '启动命令（历史）',
    CODEX_PROCESS_STARTED: '子进程启动（历史）',
    CODEX_OUTPUT: '过程输出（历史）',
    CODEX_PROCESS_EXIT: '子进程退出（历史）',
    CODEX_PARSED: '解析输出（历史）',
    CODEX_TIMEOUT: '执行超时（历史）',
    CODEX_FAILED: '历史 CLI 执行失败',
    CODEX_IO_ERROR: '历史 CLI 启动或读取失败',
    CODEX_INTERRUPTED: '历史 CLI 执行中断',
    OPENAI_REQUEST: '调用 OpenAI',
    OPENAI_REQUEST_DEBUG: 'OpenAI 请求摘要',
    OPENAI_REQUEST_PREVIEW: 'OpenAI 请求预览',
    OPENAI_RESPONSE: 'OpenAI 已响应',
    OPENAI_RESPONSE_DEBUG: 'OpenAI 响应摘要',
    OPENAI_RESPONSE_RAW: 'OpenAI 原始响应',
    OPENAI_OUTPUT_TEXT: 'OpenAI 输出文本',
    OPENAI_PARSED: '解析 OpenAI 输出',
    OPENAI_PARSE_RESULT: 'OpenAI 解析结果',
    OPENAI_FAILED: 'OpenAI 执行失败',
    ANTHROPIC_REQUEST: '调用 Anthropic',
    ANTHROPIC_RESPONSE: 'Anthropic 已响应',
    ANTHROPIC_PARSED: '解析 Anthropic 输出',
    ANTHROPIC_FAILED: 'Anthropic 执行失败',
    DEEPSEEK_REQUEST: '调用 DeepSeek',
    DEEPSEEK_RESPONSE: 'DeepSeek 已响应',
    DEEPSEEK_PARSED: '解析 DeepSeek 输出',
    DEEPSEEK_FAILED: 'DeepSeek 执行失败',
    XIAOMIMO_REQUEST: '调用 XiaoMIMO',
    XIAOMIMO_RESPONSE: 'XiaoMIMO 已响应',
    XIAOMIMO_PARSED: '解析 XiaoMIMO 输出',
    XIAOMIMO_FAILED: 'XiaoMIMO 执行失败',
    GLM_REQUEST: '调用 GLM',
    GLM_RESPONSE: 'GLM 已响应',
    GLM_PARSED: '解析 GLM 输出',
    GLM_FAILED: 'GLM 执行失败',
    CUSTOM_REQUEST: '调用自定义 Provider',
    CUSTOM_RESPONSE: '自定义 Provider 已响应',
    CUSTOM_PARSED: '解析自定义 Provider 输出',
    CUSTOM_FAILED: '自定义 Provider 执行失败',
    HTTP_REQUEST_START: 'HTTP 请求已发起',
    HTTP_RESPONSE_HEADERS: 'HTTP 响应头',
    HTTP_RESPONSE_BODY_PREVIEW: 'HTTP 响应预览',
    OUTPUT_EXTRACTED: '输出文本已提取',
    JSON_PARSE_START: '解析 JSON',
    JSON_PARSE_FAILED: 'JSON 解析失败',
    SAVE_RESULT: '保存结果',
    RESULT_SAVED: '结果已保存',
    FIX_PREVIEW_QUEUED: '修复预览已排队',
    FIX_PREVIEW_AUTO_QUEUED: '修复预览批量排队',
    FIX_PREVIEW_REQUEST_BUILT: '修复预览请求已构建',
    FIX_PREVIEW_SAVED: '修复预览已保存',
    FIX_PREVIEW_AUTO_FAILED: '修复预览失败',
    FINISHED: '已完成',
    FAILED: '失败',
    SAVE_FAILED: '保存失败'
  };
  return labels[phase] || phase || '-';
}

const keyProgressPhases = new Set([
  'QUEUED',
  'STARTED',
  'REQUEST_BUILT',
  'PROVIDER_SELECTED',
  'REQUEST_VALIDATED',
  'CONTEXT_PACK_BUILT',
  'LOCAL_REPO_PREPARED',
  'LOCAL_REPO_PREPARE_FAILED',
  'LOCAL_CONTEXT_RETRIEVED',
  'LOCAL_CONTEXT_RETRIEVE_FAILED',
  'PROVIDER_START',
  'PROVIDER_FAILED',
  'PROMPT_METADATA',
  'CODEX_COMMAND',
  'CODEX_PROCESS_STARTED',
  'CODEX_PROCESS_EXIT',
  'CODEX_PARSED',
  'OPENAI_REQUEST',
  'OPENAI_RESPONSE',
  'OPENAI_PARSED',
  'ANTHROPIC_REQUEST',
  'ANTHROPIC_RESPONSE',
  'ANTHROPIC_PARSED',
  'DEEPSEEK_REQUEST',
  'DEEPSEEK_RESPONSE',
  'DEEPSEEK_PARSED',
  'XIAOMIMO_REQUEST',
  'XIAOMIMO_RESPONSE',
  'XIAOMIMO_PARSED',
  'GLM_REQUEST',
  'GLM_RESPONSE',
  'GLM_PARSED',
  'CUSTOM_REQUEST',
  'CUSTOM_RESPONSE',
  'CUSTOM_PARSED',
  'HTTP_REQUEST_START',
  'HTTP_RESPONSE_HEADERS',
  'HTTP_RESPONSE_BODY_PREVIEW',
  'OUTPUT_EXTRACTED',
  'JSON_PARSE_START',
  'JSON_PARSE_FAILED',
  'SAVE_RESULT',
  'RESULT_SAVED',
  'FINISHED',
  'FAILED',
  'SAVE_FAILED',
  'CODEX_TIMEOUT',
  'CODEX_FAILED',
  'CODEX_IO_ERROR',
  'CODEX_INTERRUPTED',
  'OPENAI_FAILED',
  'ANTHROPIC_FAILED',
  'DEEPSEEK_FAILED',
  'XIAOMIMO_FAILED',
  'GLM_FAILED',
  'CUSTOM_FAILED'
]);

function isDebugProgressEvent(event) {
  return event?.level === 'DEBUG' || event?.phase === 'CODEX_OUTPUT';
}

function isKeyProgressEvent(event) {
  return keyProgressPhases.has(event?.phase) || ['WARN', 'ERROR'].includes(event?.level);
}

function isFixPreviewProgressEvent(event) {
  return String(event?.phase || '').startsWith('FIX_PREVIEW');
}

function progressStepDescription(event) {
  switch (event?.phase) {
    case 'QUEUED':
      return '任务已进入 AI Review 队列，等待执行。';
    case 'STARTED':
      return '开始执行代码质量 Review。';
    case 'REQUEST_BUILT':
      return '已确定本轮使用的 profile、provider、model、审查模式和变更范围。';
    case 'PROVIDER_SELECTED':
      return '已选择本轮使用的模型 Provider。';
    case 'REQUEST_VALIDATED':
      return event?.level === 'ERROR' ? 'Provider 请求参数未通过校验。' : 'Provider 请求参数已通过校验。';
    case 'CONTEXT_PACK_BUILT':
      return '已构建 Context Pack，并汇总高准确模式可用的本地仓库上下文检索摘要。';
    case 'LOCAL_REPO_PREPARED':
      return '本地仓库工作区已准备，可用于高准确模式引用检索。';
    case 'LOCAL_REPO_PREPARE_FAILED':
      return '本地仓库工作区不可用，本次 Review 会继续使用已有 diff 和可用上下文。';
    case 'LOCAL_CONTEXT_RETRIEVED':
      return '本地仓库上下文检索已完成，摘要见上方高准确模式卡片。';
    case 'LOCAL_CONTEXT_RETRIEVE_FAILED':
      return '本地仓库引用检索不可用，本次 Review 不会把检索失败解释为无风险。';
    case 'PROVIDER_START':
      return '开始调用代码质量 Review provider。';
    case 'PROVIDER_FAILED':
      return '代码质量 Review Provider 调用失败。';
    case 'PROMPT_METADATA':
      return '已生成最终 prompt，并记录 hash、长度、预览和运行环境。';
    case 'CODEX_COMMAND':
      return '历史 CLI 模式准备启动命令。';
    case 'CODEX_PROCESS_STARTED':
      return '历史 CLI 子进程已经启动，开始分析变更。';
    case 'CODEX_PROCESS_EXIT':
      return '历史 CLI 子进程已退出。';
    case 'CODEX_PARSED':
      return '历史 CLI 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'OPENAI_REQUEST':
      return '开始调用 OpenAI API。';
    case 'OPENAI_RESPONSE':
      return 'OpenAI API 已返回响应。';
    case 'OPENAI_PARSED':
      return 'OpenAI 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'ANTHROPIC_REQUEST':
      return '开始调用 Anthropic API。';
    case 'ANTHROPIC_RESPONSE':
      return 'Anthropic API 已返回响应。';
    case 'ANTHROPIC_PARSED':
      return 'Anthropic 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'DEEPSEEK_REQUEST':
      return '开始调用 DeepSeek API。';
    case 'DEEPSEEK_RESPONSE':
      return 'DeepSeek API 已返回响应。';
    case 'DEEPSEEK_PARSED':
      return 'DeepSeek 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'XIAOMIMO_REQUEST':
      return '开始调用 XiaoMIMO API。';
    case 'XIAOMIMO_RESPONSE':
      return 'XiaoMIMO API 已返回响应。';
    case 'XIAOMIMO_PARSED':
      return 'XiaoMIMO 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'GLM_REQUEST':
      return '开始调用 GLM API。';
    case 'GLM_RESPONSE':
      return 'GLM API 已返回响应。';
    case 'GLM_PARSED':
      return 'GLM 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'CUSTOM_REQUEST':
      return '开始调用自定义 OpenAI-compatible Provider。';
    case 'CUSTOM_RESPONSE':
      return '自定义 Provider 已返回响应。';
    case 'CUSTOM_PARSED':
      return '自定义 Provider 输出已解析为结构化质量问题；评审建议见上方“质量问题”。';
    case 'HTTP_REQUEST_START':
      return '已发起 Provider HTTP 请求，正在等待模型服务响应。';
    case 'HTTP_RESPONSE_HEADERS':
      return 'Provider HTTP 响应头已返回。';
    case 'HTTP_RESPONSE_BODY_PREVIEW':
      return '已记录 Provider 响应体预览，可用于判断网关错误或非预期响应。';
    case 'OUTPUT_EXTRACTED':
      return event?.level === 'ERROR' ? 'Provider 响应中未提取到可解析的模型输出。' : 'Provider 输出文本已提取。';
    case 'JSON_PARSE_START':
      return '开始把模型输出解析为平台要求的结构化 JSON。';
    case 'JSON_PARSE_FAILED':
      return '模型已返回文本，但不是平台要求的合法 Review JSON。';
    case 'SAVE_RESULT':
      return 'Provider 执行完成，正在保存 Review 结果。';
    case 'RESULT_SAVED':
      return 'AI Review 结果已保存到数据库。';
    case 'FINISHED':
      return 'AI Review 已完成。';
    case 'FAILED':
    case 'SAVE_FAILED':
    case 'CODEX_TIMEOUT':
    case 'CODEX_FAILED':
    case 'CODEX_IO_ERROR':
    case 'CODEX_INTERRUPTED':
    case 'OPENAI_FAILED':
    case 'ANTHROPIC_FAILED':
    case 'DEEPSEEK_FAILED':
    case 'XIAOMIMO_FAILED':
    case 'GLM_FAILED':
    case 'CUSTOM_FAILED':
      return '该阶段失败，需要查看错误详情。';
    default:
      return event?.message || '-';
  }
}

function formatCodexOutputDetail(detail) {
  if (!detail) return '';
  try {
    const payload = JSON.parse(detail);
    const item = payload.item || {};
    const parts = [];
    if (payload.type) parts.push(`type: ${payload.type}`);
    if (item.type) parts.push(`item.type: ${item.type}`);
    if (payload.text) parts.push(`text:\n${payload.text}`);
    if (item.text) parts.push(`text:\n${item.text}`);
    if (item.command) parts.push(`command:\n${item.command}`);
    if (item.status) parts.push(`status: ${item.status}`);
    if (item.exit_code !== undefined) parts.push(`exitCode: ${item.exit_code}`);
    if (item.aggregated_output) parts.push(`output:\n${item.aggregated_output}`);
    if (parts.length > 0) return parts.join('\n\n');
  } catch {
    return detail;
  }
  return detail;
}

function progressDetailText(event) {
  if (!event?.detail) return '';
  if (event.phase === 'CODEX_OUTPUT') {
    return formatCodexOutputDetail(event.detail);
  }
  return event.detail;
}

function parseEventTime(value) {
  if (!value) return null;
  const normalized = String(value).includes('T') ? value : String(value).replace(' ', 'T');
  const timestamp = new Date(normalized).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatDuration(seconds) {
  if (seconds == null) return null;
  if (seconds < 1) return '<1 秒';
  if (seconds < 10) return `${seconds.toFixed(1)} 秒`;
  return `${Math.round(seconds)} 秒`;
}

function totalProgressDuration(events) {
  const timestamps = events
    .filter(event => !isFixPreviewProgressEvent(event))
    .map(event => parseEventTime(event.createdAt))
    .filter(timestamp => timestamp != null);
  if (timestamps.length < 2) return null;
  return Math.max(0, (timestamps[timestamps.length - 1] - timestamps[0]) / 1000);
}

function parseProgressDetailJson(detail) {
  if (!detail) return null;
  if (typeof detail === 'object') return detail;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function latestProgressEvent(events, phases) {
  const phaseSet = new Set(Array.isArray(phases) ? phases : [phases]);
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (phaseSet.has(events[index]?.phase)) return events[index];
  }
  return null;
}

function countValue(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.floor(parsed);
}

function countText(value) {
  return value == null ? '-' : String(countValue(value));
}

function countListTotal(items) {
  if (!Array.isArray(items)) return 0;
  return items.reduce((sum, item) => sum + countValue(item?.count), 0);
}

function countItemsText(items, valueKey = 'type') {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return '-';
  return rows
    .slice(0, 4)
    .map(item => `${item?.[valueKey] || '-'} ${countValue(item?.count)}`)
    .join('、');
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function localRepositoryStatusLabel(status, hasRecord) {
  if (!hasRecord) return '未产生记录';
  switch (String(status || '').toUpperCase()) {
    case 'PREPARED':
      return '已准备';
    case 'WORKTREE_MISSING':
      return '工作区缺失';
    case 'UNAVAILABLE':
      return '不可用';
    case 'DISABLED':
      return '未启用';
    default:
      return status || '未知';
  }
}

function localRepositoryStatusColor(status, hasRecord) {
  if (!hasRecord) return 'default';
  switch (String(status || '').toUpperCase()) {
    case 'PREPARED':
      return 'green';
    case 'WORKTREE_MISSING':
      return 'orange';
    case 'UNAVAILABLE':
      return 'orange';
    case 'DISABLED':
      return 'default';
    default:
      return 'blue';
  }
}

function latestPhaseEvent(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return events[index];
  }
  return null;
}

function phaseStartsWith(event, prefixes) {
  const phase = String(event?.phase || '');
  return prefixes.some(prefix => phase.startsWith(prefix));
}

function roleStepStatus({ hasEvent, failed = false, running = false, skipped = false }) {
  if (failed) return 'error';
  if (running) return 'process';
  if (hasEvent || skipped) return 'finish';
  return 'wait';
}

function buildHighAccuracyContextSummary(progress) {
  const events = Array.isArray(progress) ? progress : [];
  const contextEvent = latestProgressEvent(events, 'CONTEXT_PACK_BUILT');
  const repoEvent = latestProgressEvent(events, ['LOCAL_REPO_PREPARED', 'LOCAL_REPO_PREPARE_FAILED']);
  const referenceEvent = latestProgressEvent(events, ['LOCAL_CONTEXT_RETRIEVED', 'LOCAL_CONTEXT_RETRIEVE_FAILED']);
  const contextDetail = parseProgressDetailJson(contextEvent?.detail) || {};
  const repoDetail = parseProgressDetailJson(repoEvent?.detail) || {};
  const referenceDetail = parseProgressDetailJson(referenceEvent?.detail) || {};
  const summary = contextDetail.summary || {};
  const meta = contextDetail.meta || {};
  const localRepository = {
    ...(summary.localRepository || {}),
    ...repoDetail
  };
  const localReferenceSearch = {
    ...(summary.localReferenceSearch || {}),
    ...referenceDetail
  };
  const hasRecord = Boolean(contextEvent || repoEvent || referenceEvent);
  const enabledValue = localRepository.enabled !== undefined
    ? localRepository.enabled
    : meta.localRepositoryEnabled;
  const enabled = Boolean(enabledValue);
  const rawStatus = localRepository.status || meta.localRepositoryStatus || (hasRecord ? (enabled ? 'UNKNOWN' : 'DISABLED') : '');
  const referenceStatus = String(localReferenceSearch.status || '').toUpperCase();
  const status = String(rawStatus || '').toUpperCase() === 'PREPARED' && referenceStatus === 'UNAVAILABLE'
    ? 'WORKTREE_MISSING'
    : rawStatus;
  return {
    hasRecord,
    enabled,
    status,
    truncated: Boolean(localReferenceSearch.truncated || meta.localReferenceTruncated || summary.truncated || meta.truncated),
    plannerSignalCount: hasRecord ? (summary.plannerSignalCount ?? meta.plannerSignalCount) : null,
    plannerSignalTypeCounts: safeArray(summary.plannerSignalTypeCounts),
    retrieverSupportedSignalTypes: safeArray(summary.retrieverSupportedSignalTypes),
    retrieverUnsupportedSignalTypeCounts: safeArray(summary.retrieverUnsupportedSignalTypeCounts),
    requestedContextAvailability: summary.requestedContextAvailability || {},
    budgetCutSummary: summary.budgetCutSummary || meta.budgetCutSummary || {},
    ruleGapSummary: summary.ruleGapSummary || {},
    ruleGapItems: safeArray(summary.ruleGapItems),
    queryCount: hasRecord ? (localReferenceSearch.queryCount ?? meta.localReferenceQueryCount) : null,
    matchedFileCount: hasRecord ? (localReferenceSearch.matchedFileCount ?? meta.localReferenceMatchedFileCount) : null,
    includedSnippetCount: hasRecord ? (localReferenceSearch.includedSnippetCount ?? meta.localReferenceSnippetCount) : null,
    unavailableContextCount: hasRecord ? (summary.unavailableContextCount ?? meta.unavailableContextCount) : null,
    contextEvent,
    repoEvent,
    referenceEvent,
    localRepository,
    localReferenceSearch,
    meta,
    rawSummary: summary
  };
}

function HighAccuracyContextSummary({ progress }) {
  const summary = buildHighAccuracyContextSummary(progress);
  const statusLabel = localRepositoryStatusLabel(summary.status, summary.hasRecord);
  const statusColor = localRepositoryStatusColor(summary.status, summary.hasRecord);
  const message = summary.hasRecord
    ? '本次 AI Review 的本地仓库上下文检索摘要'
    : '暂无本地仓库上下文检索记录';
  const description = summary.hasRecord
    ? '高准确模式会把预算内的本地引用证据注入 Context Pack；页面仅展示统计摘要，不展开源码片段。'
    : '触发代码质量 AI Review 后，这里会展示高准确模式的仓库准备和引用检索计数。';

  return (
    <Card
      className="high-accuracy-context-card"
      title={(
        <Space wrap>
          <FileSearchOutlined />
          <span>高准确模式 · 本地仓库上下文检索</span>
        </Space>
      )}
    >
      <Space direction="vertical" size="middle" className="full-width">
        <Alert
          type="info"
          showIcon
          message={message}
          description={description}
        />
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
          <Descriptions.Item label="启用状态">
            <Tag color={summary.hasRecord && summary.enabled ? 'green' : 'default'}>
              {summary.hasRecord ? (summary.enabled ? '已启用' : '未启用') : '未产生记录'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="仓库准备状态">
            <Tag color={statusColor}>{statusLabel}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Planner Signal 数">
            <Text strong>{countText(summary.plannerSignalCount)}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="引用查询数">
            <Text strong>{countText(summary.queryCount)}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="命中文件数">
            <Text strong>{countText(summary.matchedFileCount)}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="Snippet 数">
            <Text strong>{countText(summary.includedSnippetCount)}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="不可用上下文数">
            <Text strong>{countText(summary.unavailableContextCount)}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="检索预算">
            {summary.truncated ? <Tag color="orange">已截断</Tag> : <Tag>未截断</Tag>}
          </Descriptions.Item>
        </Descriptions>
      </Space>
    </Card>
  );
}

function zeroQueryExplanation(summary) {
  if (!summary.hasRecord || countValue(summary.queryCount) > 0) return null;
  const repositoryStatus = String(summary.status || '').toUpperCase();
  const supportedSignals = new Set(summary.retrieverSupportedSignalTypes || []);
  const supportedSignalCount = safeArray(summary.plannerSignalTypeCounts)
    .filter(item => supportedSignals.has(item?.type))
    .reduce((sum, item) => sum + countValue(item?.count), 0);
  const unsupportedSignalCount = countListTotal(summary.retrieverUnsupportedSignalTypeCounts);
  if (summary.referenceEvent?.phase === 'LOCAL_CONTEXT_RETRIEVE_FAILED') {
    return '引用查询数为 0：Local Retriever 执行失败或检索不可用，本次不会把检索失败解释为无风险。';
  }
  if (summary.enabled && repositoryStatus !== 'PREPARED') {
    return '引用查询数为 0：本地仓库未准备完成，Retriever 被跳过。';
  }
  if (supportedSignalCount === 0 && unsupportedSignalCount > 0) {
    const unsupported = countItemsText(summary.retrieverUnsupportedSignalTypeCounts);
    const supported = (summary.retrieverSupportedSignalTypes || []).join('、') || '-';
    return `引用查询数为 0：Planner 命中 ${unsupported}，但当前 Retriever 只支持 ${supported}。`;
  }
  if (countValue(summary.plannerSignalCount) === 0) {
    return '引用查询数为 0：Planner 未命中需要本地引用检索的 signal。';
  }
  return '引用查询数为 0：Retriever 被跳过，或没有生成可执行的引用查询。';
}

function roleDetailLine(items) {
  return (
    <Space size={4} wrap>
      {items.filter(Boolean).map((item, index) => (
        <Tag key={`${item}-${index}`}>{item}</Tag>
      ))}
    </Space>
  );
}

function buildFindingRefinementSummary(review) {
  const findings = Array.isArray(review?.findings) ? review.findings : [];
  const overlays = findings
    .map((finding, index) => ({ index, overlay: finding?.refinementOverlay }))
    .filter(item => item.overlay);
  const completed = overlays.filter(item => String(item.overlay.status || '').toUpperCase() === 'COMPLETED').length;
  const failed = overlays.filter(item => String(item.overlay.status || '').toUpperCase() === 'FAILED').length;
  return {
    total: overlays.length,
    completed,
    failed,
    items: overlays,
  };
}

function buildHighAccuracyRoleSteps(progress, refinementSummary) {
  const events = Array.isArray(progress) ? progress : [];
  const summary = buildHighAccuracyContextSummary(events);
  const requestEvent = latestProgressEvent(events, 'REQUEST_BUILT');
  const providerFailedEvent = latestProgressEvent(events, [
    'PROVIDER_FAILED',
    'OPENAI_FAILED',
    'ANTHROPIC_FAILED',
    'DEEPSEEK_FAILED',
    'XIAOMIMO_FAILED',
    'GLM_FAILED',
    'CUSTOM_FAILED',
  ]);
  const providerRequestEvent = latestPhaseEvent(events, event => (
    event?.phase === 'PROVIDER_START'
    || event?.phase === 'HTTP_REQUEST_START'
    || phaseStartsWith(event, [
      'OPENAI_REQUEST',
      'ANTHROPIC_REQUEST',
      'DEEPSEEK_REQUEST',
      'XIAOMIMO_REQUEST',
      'GLM_REQUEST',
      'CUSTOM_REQUEST',
    ])
  ));
  const providerResponseEvent = latestPhaseEvent(events, event => (
    event?.phase === 'HTTP_RESPONSE_HEADERS'
    || event?.phase === 'HTTP_RESPONSE_BODY_PREVIEW'
    || phaseStartsWith(event, [
      'OPENAI_RESPONSE',
      'ANTHROPIC_RESPONSE',
      'DEEPSEEK_RESPONSE',
      'XIAOMIMO_RESPONSE',
      'GLM_RESPONSE',
      'CUSTOM_RESPONSE',
    ])
  ));
  const parseFailedEvent = latestProgressEvent(events, ['JSON_PARSE_FAILED', 'FAILED', 'SAVE_FAILED']);
  const parsedEvent = latestPhaseEvent(events, event => (
    event?.phase === 'OUTPUT_EXTRACTED'
    || event?.phase === 'JSON_PARSE_START'
    || event?.phase === 'RESULT_SAVED'
    || event?.phase === 'FINISHED'
    || String(event?.phase || '').endsWith('_PARSED')
    || String(event?.phase || '').endsWith('_PARSE_RESULT')
  ));
  const repoFailed = summary.repoEvent?.phase === 'LOCAL_REPO_PREPARE_FAILED';
  const retrieverFailed = summary.referenceEvent?.phase === 'LOCAL_CONTEXT_RETRIEVE_FAILED';
  const retrieverSkipped = summary.hasRecord && !summary.referenceEvent && countValue(summary.queryCount) === 0;
  const providerRunning = Boolean(providerRequestEvent && !providerResponseEvent && !providerFailedEvent);

  return [
    {
      title: '变更接入',
      status: roleStepStatus({ hasEvent: Boolean(requestEvent || summary.hasRecord) }),
      description: roleDetailLine([
        `文件 ${countText(summary.rawSummary?.changedFileCount)}`,
        `Diff ${countText(summary.rawSummary?.diffBytes)} bytes`,
      ]),
    },
    {
      title: 'Context Pack',
      status: roleStepStatus({ hasEvent: Boolean(summary.contextEvent) }),
      description: roleDetailLine([
        `Prompt ${countText(summary.rawSummary?.promptLength)} chars`,
        summary.truncated ? '已截断' : '未截断',
        `不可用 ${countText(summary.unavailableContextCount)}`,
      ]),
    },
    {
      title: 'Planner',
      status: roleStepStatus({ hasEvent: Boolean(summary.contextEvent) }),
      description: roleDetailLine([
        `Signal ${countText(summary.plannerSignalCount)}`,
        `类型 ${countItemsText(summary.plannerSignalTypeCounts)}`,
      ]),
    },
    {
      title: '本地仓库',
      status: roleStepStatus({ hasEvent: Boolean(summary.repoEvent || summary.hasRecord), failed: repoFailed }),
      description: roleDetailLine([
        localRepositoryStatusLabel(summary.status, summary.hasRecord),
        summary.localRepository?.mirrorStatus && `mirror ${summary.localRepository.mirrorStatus}`,
        summary.localRepository?.worktreeStatus && `worktree ${summary.localRepository.worktreeStatus}`,
      ]),
    },
    {
      title: 'Retriever',
      status: roleStepStatus({
        hasEvent: Boolean(summary.referenceEvent),
        failed: retrieverFailed,
        skipped: retrieverSkipped,
      }),
      description: roleDetailLine([
        `查询 ${countText(summary.queryCount)}`,
        `文件 ${countText(summary.matchedFileCount)}`,
        `Snippet ${countText(summary.includedSnippetCount)}`,
        retrieverSkipped ? '已跳过' : null,
      ]),
    },
    {
      title: '预算裁剪',
      status: roleStepStatus({ hasEvent: Boolean(summary.contextEvent) }),
      description: roleDetailLine([
        summary.budgetCutSummary?.truncated ? '发生裁剪' : '未裁剪',
        `变更文件排除 ${countText(summary.budgetCutSummary?.changedFilesExcluded)}`,
        `引用 Snippet 裁剪 ${countText(summary.budgetCutSummary?.localReferenceSnippetsRemoved)}`,
      ]),
    },
    {
      title: 'Provider',
      status: roleStepStatus({
        hasEvent: Boolean(providerResponseEvent),
        failed: Boolean(providerFailedEvent),
        running: providerRunning,
      }),
      description: roleDetailLine([
        providerResponseEvent ? phaseLabel(providerResponseEvent.phase) : providerRequestEvent ? phaseLabel(providerRequestEvent.phase) : '等待调用',
      ]),
    },
    {
      title: '结果解析',
      status: roleStepStatus({
        hasEvent: Boolean(parsedEvent),
        failed: Boolean(parseFailedEvent),
      }),
      description: roleDetailLine([
        parsedEvent ? phaseLabel(parsedEvent.phase) : '等待解析',
      ]),
    },
    {
      title: 'Finding 补证据',
      status: roleStepStatus({
        hasEvent: countValue(refinementSummary?.total) > 0,
        failed: countValue(refinementSummary?.failed) > 0,
      }),
      description: roleDetailLine([
        `总数 ${countText(refinementSummary?.total)}`,
        `完成 ${countText(refinementSummary?.completed)}`,
        `失败 ${countText(refinementSummary?.failed)}`,
      ]),
    },
  ];
}

function HighAccuracyFlowView({ progress, review }) {
  const navigate = useNavigate();
  const location = useLocation();
  const summary = buildHighAccuracyContextSummary(progress);
  const refinementSummary = buildFindingRefinementSummary(review);
  const zeroReason = zeroQueryExplanation(summary);
  const availabilityItems = safeArray(summary.requestedContextAvailability?.items);
  const ruleGapItems = safeArray(summary.ruleGapItems);
  const budgetCutDetails = safeArray(
    summary.budgetCutSummary?.localReferenceCutDetails?.length
      ? summary.budgetCutSummary.localReferenceCutDetails
      : summary.budgetCutSummary?.notInjectedEvidence
  );
  const gapText = value => {
    const text = value || '-';
    return (
      <Tooltip title={text}>
        <span className="rule-gap-cell-text">{text}</span>
      </Tooltip>
    );
  };
  const gapColumns = [
    {
      title: '缺口类型',
      dataIndex: 'gapType',
      width: 210,
      render: value => (
        <Tooltip title={value || '-'}>
          <Tag color="orange" className="rule-gap-type-tag">{value || '-'}</Tag>
        </Tooltip>
      ),
    },
    { title: 'Signal', dataIndex: 'signal', width: 240, render: gapText },
    { title: 'Requested Context', dataIndex: 'requestedContext', width: 220, render: gapText },
    { title: '建议能力', dataIndex: 'suggestedCapability', width: 380, render: gapText },
    { title: '优先级原因', dataIndex: 'priorityReason', width: 360, render: gapText },
  ];
  const availabilityColumns = [
    { title: 'Context', dataIndex: 'type', width: 220, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'available',
      width: 120,
      render: value => value ? <Tag color="green">可用</Tag> : <Tag color="orange">不可用</Tag>,
    },
    { title: 'Signal 数', dataIndex: 'signalCount', width: 100 },
    { title: '优先级', dataIndex: 'priority', width: 110 },
    { title: '原因', dataIndex: 'reasonCode', ellipsis: true, render: value => value || '-' },
  ];
  const budgetCutColumns = [
    { title: 'Signal', dataIndex: 'signal', width: 190, ellipsis: true },
    { title: 'Requested Context', dataIndex: 'requestedContext', width: 170, ellipsis: true },
    { title: '查询摘要', dataIndex: 'querySummary', width: 150, ellipsis: true, render: (value, row) => value || row.query || '-' },
    { title: '命中文件', dataIndex: 'matchedFileCount', width: 90, render: value => countText(value) },
    { title: '裁剪 Snippet', dataIndex: 'cutSnippetCount', width: 110, render: value => countText(value) },
    {
      title: 'Top 相对路径',
      dataIndex: 'topRelativePaths',
      ellipsis: true,
      render: (value, row) => {
        const paths = safeArray(value?.length ? value : row.topMatchedPaths);
        return paths.length ? paths.join('、') : '-';
      },
    },
    { title: '原因', dataIndex: 'reason', width: 220, ellipsis: true, render: value => value || '-' },
  ];

  return (
    <Space direction="vertical" size="large" className="full-width">
      <HighAccuracyContextSummary progress={progress} />
      <Card title="角色流转">
        <Steps
          direction="vertical"
          size="small"
          items={buildHighAccuracyRoleSteps(progress, refinementSummary)}
        />
      </Card>
      <Card title="Finding 级二次补证据">
        {refinementSummary.total === 0 ? (
          <Empty description="当前 Review 暂无 finding 级补证据记录" />
        ) : (
          <Space direction="vertical" size="middle" className="full-width">
            <Descriptions size="small" column={{ xs: 1, md: 3 }}>
              <Descriptions.Item label="补证据记录"><Text strong>{countText(refinementSummary.total)}</Text></Descriptions.Item>
              <Descriptions.Item label="已完成"><Text strong>{countText(refinementSummary.completed)}</Text></Descriptions.Item>
              <Descriptions.Item label="失败"><Text strong>{countText(refinementSummary.failed)}</Text></Descriptions.Item>
            </Descriptions>
            <Alert
              type="info"
              showIcon
              message="补证据结果只作为 finding 覆盖层展示"
              description="这里仅汇总安全摘要；具体触发条件、检索计划、证据摘要、缺失上下文和失败原因请在 AI Review 结果中展开对应 finding 查看。"
            />
          </Space>
        )}
      </Card>
      {zeroReason && (
        <Alert
          type="warning"
          showIcon
          message="引用查询数为 0"
          description={zeroReason}
        />
      )}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="Planner / Retriever 摘要">
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="Planner Signal 类型">
                {countItemsText(summary.plannerSignalTypeCounts)}
              </Descriptions.Item>
              <Descriptions.Item label="Retriever 支持 Signal">
                {(summary.retrieverSupportedSignalTypes || []).join('、') || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="暂不支持 Signal">
                {countItemsText(summary.retrieverUnsupportedSignalTypeCounts)}
              </Descriptions.Item>
              <Descriptions.Item label="Requested Context">
                可用 {countText(summary.requestedContextAvailability?.available)} / 不可用 {countText(summary.requestedContextAvailability?.unavailable)}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="预算裁剪摘要">
            <Space direction="vertical" size="middle" className="full-width">
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="状态">
                  {summary.budgetCutSummary?.truncated ? <Tag color="orange">已裁剪</Tag> : <Tag>未裁剪</Tag>}
                </Descriptions.Item>
                <Descriptions.Item label="变更文件排除">{countText(summary.budgetCutSummary?.changedFilesExcluded)}</Descriptions.Item>
                <Descriptions.Item label="同文件片段裁剪">{countText(summary.budgetCutSummary?.sameFileSourceSnippetsRemoved)}</Descriptions.Item>
                <Descriptions.Item label="引用片段裁剪">{countText(summary.budgetCutSummary?.localReferenceSnippetsRemoved)}</Descriptions.Item>
                <Descriptions.Item label="高误判 Signal 保留">
                  {safeArray(summary.budgetCutSummary?.protectedSignalTypes).join('、') || '-'}
                </Descriptions.Item>
              </Descriptions>
              {budgetCutDetails.length > 0 && (
                <>
                  <Alert
                    type="warning"
                    showIcon
                    message="存在未注入证据"
                    description="以下为预算裁剪安全摘要，仅包含查询、命中文件数、裁剪数、相对路径和原因，不展示源码片段。"
                  />
                  <Table
                    rowKey={(row, index) => `${row.signal || '-'}-${row.querySummary || row.query || '-'}-${index}`}
                    size="small"
                    columns={budgetCutColumns}
                    dataSource={budgetCutDetails}
                    pagination={false}
                    scroll={{ x: 960 }}
                  />
                </>
              )}
            </Space>
          </Card>
        </Col>
      </Row>
      <Card title="Requested Context 可用性">
        {availabilityItems.length === 0 ? (
          <Empty description="暂无 requested context 摘要" />
        ) : (
          <Table
            rowKey={(row, index) => `${row.type}-${index}`}
            size="small"
            columns={availabilityColumns}
            dataSource={availabilityItems}
            pagination={false}
          />
        )}
      </Card>
      <Card
        title="本任务规则缺口"
        extra={(
          <Button
            size="small"
            icon={<FileSearchOutlined />}
            onClick={() => navigate(RULE_GAPS_ROUTE, { state: { from: currentRoute(location) } })}
          >
            查看看板
          </Button>
        )}
      >
        {ruleGapItems.length === 0 ? (
          <Empty description="本任务暂无规则缺口摘要" />
        ) : (
          <Table
            rowKey={(row, index) => `${row.gapType}-${row.signal}-${index}`}
            size="small"
            columns={gapColumns}
            dataSource={ruleGapItems}
            pagination={false}
            tableLayout="fixed"
            scroll={{ x: 1410 }}
            className="rule-gap-table"
          />
        )}
      </Card>
    </Space>
  );
}

function ProgressEventView({ event, showStepDescription = false }) {
  const description = showStepDescription ? progressStepDescription(event) : event.message;
  const detail = progressDetailText(event);
  return (
    <div className="progress-event">
      <Space wrap size="small">
        <Tag color={progressColor(event.level)}>{event.level || 'INFO'}</Tag>
        <Tag>{phaseLabel(event.phase)}</Tag>
        <Text type="secondary">{event.createdAt || '-'}</Text>
      </Space>
      <div className="progress-message">{description}</div>
      {showStepDescription && event.message && event.message !== description && (
        <Text type="secondary" className="progress-original-message">{event.message}</Text>
      )}
      {detail && <pre className="progress-detail">{detail}</pre>}
    </div>
  );
}

function FindingContext({ finding }) {
  const evidences = normalizeTextList(finding?.evidence);
  const missingContext = normalizeTextList(finding?.missingContext);
  const hasContext = finding?.contextStatus || finding?.contextSummary || evidences.length > 0 || missingContext.length > 0;
  if (!hasContext) return null;

  return (
    <div className="finding-context-panel">
      <Space direction="vertical" size={8} className="full-width">
        <Space wrap>
          {finding.contextStatus && (
            <Tag color={contextStatusColor(finding.contextStatus)}>
              上下文 {contextStatusLabel(finding.contextStatus)}
            </Tag>
          )}
          {missingContext.map(item => (
            <Tag key={item} color="orange">{missingContextLabel(item)}</Tag>
          ))}
        </Space>
        {finding.contextSummary && (
          <Text className="finding-context-summary">{cleanAiMarkdown(finding.contextSummary)}</Text>
        )}
        {evidences.length > 0 && (
          <div className="finding-context-evidence">
            <Text type="secondary">判断依据</Text>
            <ul>
              {evidences.map((item, index) => (
                <li key={`${item}-${index}`}>{cleanAiMarkdown(item)}</li>
              ))}
            </ul>
          </div>
        )}
      </Space>
    </div>
  );
}

function RefinementStatDescriptions({ title, value, fields }) {
  const data = value && typeof value === 'object' ? value : {};
  const visibleFields = fields.filter(field => data[field] !== undefined && data[field] !== null && data[field] !== '');
  if (visibleFields.length === 0) return null;
  return (
    <div className="refinement-stat-block">
      <Text type="secondary">{title}</Text>
      <Descriptions size="small" column={{ xs: 1, md: 3 }}>
        {visibleFields.map(field => (
          <Descriptions.Item key={field} label={field}>
            {sanitizeRefinementText(data[field])}
          </Descriptions.Item>
        ))}
      </Descriptions>
    </div>
  );
}

function FindingRefinementPanel({ overlay }) {
  if (!overlay) return null;
  const retrievalPlan = overlay.retrievalPlan || {};
  const evidenceSummary = overlay.evidenceSummary || {};
  const triggerConditions = overlay.triggerConditions || {};
  const missingContext = safeArray(overlay.missingContext);
  const searches = safeArray(evidenceSummary.searches);
  const completed = String(overlay.status || '').toUpperCase() === 'COMPLETED';
  const failed = String(overlay.status || '').toUpperCase() === 'FAILED';
  const searchColumns = [
    {
      title: 'Signal',
      dataIndex: 'signalTypes',
      width: 220,
      ellipsis: true,
      render: value => safeArray(value).join('、') || '-',
    },
    { title: '查询数', dataIndex: 'queryCount', width: 90, render: value => countText(value) },
    { title: '命中文件', dataIndex: 'matchedFileCount', width: 100, render: value => countText(value) },
    { title: '注入 Snippet', dataIndex: 'includedSnippetCount', width: 120, render: value => countText(value) },
    {
      title: '相对路径摘要',
      dataIndex: 'topMatchedPaths',
      ellipsis: true,
      render: (value, row) => {
        const paths = safeArray(value?.length ? value : row.topRelativePaths);
        return paths.length ? paths.map(sanitizeRefinementText).join('、') : '-';
      },
    },
  ];

  return (
    <div className="finding-refinement-panel">
      <Space direction="vertical" size="middle" className="full-width">
        <Alert
          type={failed ? 'error' : completed ? 'success' : 'info'}
          showIcon
          message={(
            <Space wrap>
              <span>二次补证据覆盖层</span>
              <Tag color={refinementStatusColor(overlay.status)}>{refinementStatusLabel(overlay.status)}</Tag>
            </Space>
          )}
          description="该结果只作为显式覆盖层展示，不会覆盖原 finding 的等级、上下文状态、置信度或原始证据。"
        />
        <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
          <Descriptions.Item label="触发原因">{refinementTriggerReasonLabel(overlay.triggerReason)}</Descriptions.Item>
          <Descriptions.Item label="触发等级">{severityLabel(triggerConditions.severity)}</Descriptions.Item>
          <Descriptions.Item label="触发上下文">{contextStatusLabel(triggerConditions.contextStatus)}</Descriptions.Item>
          <Descriptions.Item label="Context Pack">{sanitizeRefinementText(retrievalPlan.contextPackVersion || '-')}</Descriptions.Item>
          <Descriptions.Item label="Planner Signal">{countText(retrievalPlan.plannerSignalCount)}</Descriptions.Item>
          <Descriptions.Item label="Requested Context">{countText(retrievalPlan.requestedContextCount)}</Descriptions.Item>
          <Descriptions.Item label="开始时间">{overlay.startedAt || '-'}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{overlay.finishedAt || '-'}</Descriptions.Item>
        </Descriptions>
        <RefinementStatDescriptions
          title="本地仓库摘要"
          value={evidenceSummary.localRepository}
          fields={['status', 'enabled', 'failurePhase', 'durationMs', 'sourceIncluded']}
        />
        <RefinementStatDescriptions
          title="引用检索摘要"
          value={evidenceSummary.localReferenceSearch}
          fields={['status', 'queryCount', 'matchedFileCount', 'includedSnippetCount', 'truncated']}
        />
        {searches.length > 0 && (
          <Table
            size="small"
            rowKey={(row, index) => `${safeArray(row.signalTypes).join('-') || 'search'}-${index}`}
            columns={searchColumns}
            dataSource={searches}
            pagination={false}
            scroll={{ x: 760 }}
          />
        )}
        {missingContext.length > 0 && (
          <div>
            <Text type="secondary">仍缺失上下文</Text>
            <div className="refinement-missing-context">
              {missingContext.map((item, index) => {
                const type = item && typeof item === 'object' ? item.type : item;
                const reason = item && typeof item === 'object' ? item.reason : '';
                return (
                  <Tag key={`${type || 'missing'}-${index}`} color="orange">
                    {missingContextLabel(sanitizeRefinementText(type))}
                    {reason ? `：${sanitizeRefinementText(reason)}` : ''}
                  </Tag>
                );
              })}
            </div>
          </div>
        )}
        {overlay.failureReason && (
          <Alert
            type="warning"
            showIcon
            message="补证据失败原因"
            description={sanitizeRefinementText(overlay.failureReason)}
          />
        )}
      </Space>
    </div>
  );
}

function FindingRefinementControl({ taskId, review, finding, findingIndex, onRefresh }) {
  const [loading, setLoading] = useState(false);
  if (!isRefinementCandidate(finding)) return null;
  const overlay = finding?.refinementOverlay;
  const disabled = !taskId || review?.status === 'RUNNING' || (!finding?.fingerprint && findingIndex == null);
  const run = async () => {
    setLoading(true);
    try {
      await fetchApi(`/api/review-tasks/${taskId}/code-quality-refinements`, {
        method: 'POST',
        body: JSON.stringify({
          reviewKey: review?.reviewKey,
          findingIndex,
          fingerprint: finding?.fingerprint,
          forceRegenerate: Boolean(overlay)
        })
      });
      message.success(overlay ? '已重新补证据' : '已完成补证据');
      await onRefresh?.();
    } catch (err) {
      message.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Tooltip title={disabled ? '该 finding 暂不能触发补证据' : '只对当前 finding 做定向补证据，不重跑 Review'}>
      <span>
        <Button
          size="small"
          icon={<FileSearchOutlined />}
          className={`finding-action-button refinement-action ${overlay ? 'refinement-action-regenerate' : ''}`}
          loading={loading}
          disabled={disabled}
          onClick={run}
        >
          {overlay ? '重新补证据' : '补证据'}
        </Button>
      </span>
    </Tooltip>
  );
}

function CodeQualityProgressView({ progress, running = false, reviewStartedAt, reviewFinishedAt }) {
  const events = Array.isArray(progress) ? progress : [];
  const reviewEvents = events.filter(event => !isFixPreviewProgressEvent(event));
  const keyEvents = reviewEvents.filter(isKeyProgressEvent);
  const debugEvents = events.filter(isDebugProgressEvent);
  const hiddenEvents = events.filter(event => !isKeyProgressEvent(event) && !isDebugProgressEvent(event));
  const startedAt = parseEventTime(reviewStartedAt);
  const finishedAt = parseEventTime(reviewFinishedAt);
  const totalDurationText = startedAt && finishedAt
    ? formatDuration(Math.max(0, (finishedAt - startedAt) / 1000))
    : formatDuration(totalProgressDuration(reviewEvents));
  const fallbackStartedAtRef = useRef(Date.now());
  const [elapsedTick, setElapsedTick] = useState(Date.now());
  const latestEvent = reviewEvents.length > 0 ? reviewEvents[reviewEvents.length - 1] : null;
  const latestRunStartAt = latestReviewRunStartAt(reviewEvents);
  const runningStartedAt = (running ? latestRunStartAt : null) || startedAt || parseEventTime(reviewEvents[0]?.createdAt) || fallbackStartedAtRef.current;
  const runningUntil = running ? elapsedTick : (finishedAt || elapsedTick);
  const runningSeconds = Math.max(0, Math.floor((runningUntil - runningStartedAt) / 1000));

  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => setElapsedTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  return (
    <Card title="执行过程">
      {events.length === 0 ? (
        <Empty description="暂无执行过程记录" />
      ) : (
        <Space direction="vertical" size="middle" className="full-width">
          {running && (
            <div className="quality-running-bar">
              <Text strong>AI Review 正在执行</Text>
              <Tag color="processing">{phaseLabel(latestEvent?.phase)}</Tag>
              <Text type="secondary" className="quality-running-elapsed">
                已执行 {runningSeconds} 秒 <LoadingOutlined />
              </Text>
            </div>
          )}
          <Alert
            type="info"
            showIcon
            message={totalDurationText ? `总计耗时 ${totalDurationText}` : '默认只展示关键阶段'}
            description={`已折叠 ${debugEvents.length} 条 stdout/stderr 调试输出${hiddenEvents.length > 0 ? `，以及 ${hiddenEvents.length} 条辅助事件` : ''}。`}
          />
          <Timeline
            items={keyEvents.map(event => ({
              key: event.id,
              color: progressColor(event.level),
              children: <ProgressEventView event={event} showStepDescription />
            }))}
          />
          {(debugEvents.length > 0 || hiddenEvents.length > 0) && (
            <Collapse
              items={[
                debugEvents.length > 0 && {
                  key: 'debug',
                  label: `调试输出 (${debugEvents.length})`,
                  children: (
                    <Timeline
                      items={debugEvents.map(event => ({
                        key: event.id,
                        color: progressColor(event.level),
                        children: <ProgressEventView event={event} />
                      }))}
                    />
                  )
                },
                hiddenEvents.length > 0 && {
                  key: 'auxiliary',
                  label: `辅助事件 (${hiddenEvents.length})`,
                  children: (
                    <Timeline
                      items={hiddenEvents.map(event => ({
                        key: event.id,
                        color: progressColor(event.level),
                        children: <ProgressEventView event={event} />
                      }))}
                    />
                  )
                }
              ].filter(Boolean)}
            />
          )}
        </Space>
      )}
    </Card>
  );
}

function latestReviewRunStartAt(events) {
  const runStartPhases = new Set(['QUEUED', 'STARTED', 'REQUEST_BUILT', 'HTTP_REQUEST_START']);
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (runStartPhases.has(event?.phase)) {
      const parsed = parseEventTime(event?.createdAt);
      if (parsed) return parsed;
    }
  }
  return null;
}

function gateDecisionColor(value) {
  if (value === 'ALLOWED') return 'green';
  if (value === 'REJECTED') return 'red';
  return 'default';
}

function gateDecisionLabel(value) {
  switch (value) {
    case 'ALLOWED':
      return '已放行';
    case 'REJECTED':
      return '已拦截';
    case 'NOT_EVALUATED':
      return '未审核';
    default:
      return value || '-';
  }
}

function gateReasonLabel(value) {
  const labels = {
    RISK_MATCHED: '命中重点风险',
    LARGE_CHANGE: '达到变更规模条件',
    BRANCH_NOT_MATCHED: '分支不匹配',
    DEBOUNCED: '频率保护',
    DIFF_TOO_LARGE: '超过硬上限',
    NO_DIFF_TEXT: '无可审查 diff',
    PROFILE_DISABLED: 'Profile 未开启',
    GLOBAL_DISABLED: '全局未开启',
    NOT_SIGNIFICANT: '未达到变更规模条件',
    NOT_EVALUATED: '未审核'
  };
  return labels[value] || value || '-';
}

function pushLargeChangeMessage(gate, matchedRules) {
  const metrics = gate?.metrics || {};
  const largeChangeRule = matchedRules.find(rule => rule.code === 'largeChange');
  const detail = largeChangeRule?.detail || '';
  const threshold = key => {
    const match = detail.match(new RegExp(`${key}>=(\\d+)`));
    return match ? Number(match[1]) : null;
  };
  const checks = [
    { label: '文件数', value: metrics.changedFileCount, threshold: threshold('files') },
    { label: 'Diff 字节数', value: metrics.diffBytes, threshold: threshold('diffBytes') },
    { label: 'Commit 数', value: metrics.commitCount, threshold: threshold('commits') }
  ];
  const matched = checks
    .filter(item => item.threshold !== null && Number(item.value || 0) >= item.threshold)
    .map(item => `${item.label} ${item.value ?? 0} >= ${item.threshold}`);

  if (matched.length === 0) {
    return gate?.reasonSummary || gateReasonLabel(gate?.reasonCode);
  }
  const allMatched = checks.every(item => item.threshold !== null && Number(item.value || 0) >= item.threshold);
  if (!allMatched) {
    return '命中 Push 策略指标，满足 Review 条件。';
  }
  return `Push 审核策略已满足，允许进入 AI Review：${matched.join('、')}。`;
}

function gateAlertMessage(gate, matchedRules) {
  if (gate?.reasonCode === 'LARGE_CHANGE' && (!gate.reasonSummary || gate.reasonSummary.includes('大变更阈值'))) {
    return pushLargeChangeMessage(gate, matchedRules);
  }
  return gate?.reasonSummary || gateReasonLabel(gate?.reasonCode);
}

function CodeQualityGateView({ gate, detail }) {
  const metrics = gate?.metrics || {};
  const matchedRules = Array.isArray(gate?.matchedRules) ? gate.matchedRules : [];
  if (!gate || gate.decision === 'NOT_EVALUATED') {
    return (
      <Card>
        <Empty description={detail?.triggerType === 'GITLAB_PUSH_WEBHOOK' ? '暂无 Push 审核记录' : '该任务未进入 Push 审核'} />
      </Card>
    );
  }
  const ruleColumns = [
    { title: '规则', dataIndex: 'label', ellipsis: true },
    {
      title: '结果',
      dataIndex: 'matched',
      width: 110,
      render: value => <Tag color={value ? 'green' : 'default'}>{value ? '通过/命中' : '未通过'}</Tag>
    },
    { title: '详情', dataIndex: 'detail', ellipsis: true, render: value => value || '-' }
  ];
  const alertMessage = gateAlertMessage(gate, matchedRules);
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Space direction="vertical" size="middle" className="full-width">
          <Space wrap>
            <Tag color={gateDecisionColor(gate.decision)}>{gateDecisionLabel(gate.decision)}</Tag>
            <Tag>{gateReasonLabel(gate.reasonCode)}</Tag>
            {gate.aiReviewScheduled ? <Tag color="green">已进入 AI Review</Tag> : <Tag>未进入 AI Review</Tag>}
          </Space>
          <Alert
            type={gate.decision === 'ALLOWED' ? 'success' : 'warning'}
            showIcon
            message={alertMessage}
          />
          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
            <Descriptions.Item label="Profile">{gate.profileCode || '-'}</Descriptions.Item>
            <Descriptions.Item label="Provider">{gate.provider || '-'}</Descriptions.Item>
            <Descriptions.Item label="推送分支">{gate.branchName || '-'}</Descriptions.Item>
            <Descriptions.Item label="审核时间">{gate.createdAt || '-'}</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
      <Card title="审核指标">
        <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
          <Descriptions.Item label="文件数">{metrics.changedFileCount ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="Diff 字节">{metrics.diffBytes ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="Commit 数">{metrics.commitCount ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="提醒风险">{metrics.riskLevel || '-'}</Descriptions.Item>
          <Descriptions.Item label="重点提醒数">{metrics.focusRiskItemCount ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="Diff 来源">{metrics.compareSource || '-'}</Descriptions.Item>
          <Descriptions.Item label="新远程分支首次 Push">{metrics.newBranchPush ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="命中类型" span={3}>
            <Space wrap>
              {(metrics.matchedChangeTypes || []).length > 0
                ? metrics.matchedChangeTypes.map(type => <Tag key={type}>{changeTypeLabel(type)}</Tag>)
                : <Text type="secondary">-</Text>}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="判定规则">
        <Table
          rowKey={(row, index) => `${row.code}-${index}`}
          size="small"
          columns={ruleColumns}
          dataSource={matchedRules}
          pagination={false}
        />
      </Card>
    </Space>
  );
}

function DiffCodeCell({ className, language, rowType, text, children }) {
  const shouldHighlight = !['hunk', 'meta'].includes(rowType);
  return (
    <pre className={className}>
      {shouldHighlight ? <SyntaxHighlightedCode text={text} language={language} /> : text}
      {children}
    </pre>
  );
}

function DiffGapRow({ row, onExpand }) {
  return (
    <div className="diff-viewer-row diff-row-gap">
      <div className="diff-context-gap">
        <span>隐藏 {row.hiddenCount} 行上下文</span>
        <div className="diff-context-actions">
          <button type="button" onClick={() => onExpand(row.gap, 'up')}>向上展开 20 行</button>
          <button type="button" onClick={() => onExpand(row.gap, 'down')}>向下展开 20 行</button>
          <button type="button" onClick={() => onExpand(row.gap, 'all')}>展开全部</button>
        </div>
      </div>
    </div>
  );
}

function ExpandableDiffTable({
  taskId,
  filePath,
  diffText,
  viewType = 'DIFF',
  canExpand = false,
  targetStartLine,
  targetEndLine,
  ariaLabel
}) {
  const parsedDiff = useMemo(() => parseUnifiedDiff(diffText), [diffText]);
  const compactRows = useMemo(
    () => buildSideBySideRows(parsedDiff, targetStartLine, targetEndLine),
    [parsedDiff, targetStartLine, targetEndLine]
  );
  const [sourceContext, setSourceContext] = useState(null);
  const [contextError, setContextError] = useState(null);
  const [loadingContext, setLoadingContext] = useState(false);
  const [gapExpansions, setGapExpansions] = useState({});
  const [theme, setTheme] = useState('light');

  useEffect(() => {
    setSourceContext(null);
    setContextError(null);
    setLoadingContext(false);
    setGapExpansions({});
  }, [taskId, filePath, diffText, viewType]);

  const expandedResult = useMemo(() => (
    sourceContext
      ? buildExpandedRows(parsedDiff, sourceContext, viewType, gapExpansions, targetStartLine, targetEndLine)
      : null
  ), [parsedDiff, sourceContext, viewType, gapExpansions, targetStartLine, targetEndLine]);
  const rows = expandedResult?.rows || compactRows;
  const language = sourceContext?.language || diffLanguageForPath(filePath);
  const fallbackMessage = contextError || expandedResult?.error;

  const loadContext = async () => {
    if (!canExpand || !taskId || !filePath || loadingContext || sourceContext) return;
    setLoadingContext(true);
    setContextError(null);
    try {
      const context = await fetchApi(
        `/api/review-tasks/${taskId}/diff-context?filePath=${encodeURIComponent(filePath)}&viewType=${viewType}`
      );
      setSourceContext(context);
    } catch (err) {
      setContextError(err.message);
    } finally {
      setLoadingContext(false);
    }
  };

  const expandGap = (gap, direction) => {
    setGapExpansions(current => {
      const previous = current[gap.id] || {};
      const top = previous.top || 0;
      const bottom = previous.bottom || 0;
      const hidden = Math.max(0, gap.count - top - bottom);
      if (direction === 'all') return { ...current, [gap.id]: { top: gap.count, bottom: 0 } };
      if (direction === 'up') {
        return { ...current, [gap.id]: { top, bottom: bottom + Math.min(20, hidden) } };
      }
      return { ...current, [gap.id]: { top: top + Math.min(20, hidden), bottom } };
    });
  };

  return (
    <Space direction="vertical" size="small" className="full-width">
      {fallbackMessage && (
        <Alert
          type="warning"
          showIcon
          message="完整上下文暂不可用，已保留紧凑 Diff"
          description={fallbackMessage}
        />
      )}
      <div className="diff-viewer-toolbar">
        {canExpand && !sourceContext && (
          <button
            type="button"
            className="diff-context-load"
            disabled={loadingContext}
            onClick={loadContext}
          >
            {loadingContext ? '读取上下文中...' : '展开上下文'}
          </button>
        )}
        <Tooltip title={theme === 'dark' ? '切换为明亮主题' : '切换为暗黑主题'}>
          <button
            type="button"
            className="diff-theme-toggle"
            aria-label={theme === 'dark' ? '切换为明亮主题' : '切换为暗黑主题'}
            onClick={() => setTheme(current => (current === 'dark' ? 'light' : 'dark'))}
          >
            {theme === 'dark' ? <SunOutlined /> : <MoonOutlined />}
          </button>
        </Tooltip>
      </div>
      <div className={`diff-viewer-table diff-theme-${theme}`} role="table" aria-label={ariaLabel}>
        {rows.map(row => (
          row.type === 'gap' ? (
            <DiffGapRow key={row.id} row={row} onExpand={expandGap} />
          ) : (
            <div
              key={row.id}
              className={[
                'diff-viewer-row',
                `diff-row-${row.type}`,
                row.highlight ? 'diff-row-highlight' : ''
              ].filter(Boolean).join(' ')}
            >
              <div className="diff-line-number">{row.oldLine}</div>
              <DiffCodeCell className="diff-code-cell diff-code-old" language={language} rowType={row.type} text={row.oldText} />
              <div className="diff-line-number">{row.newLine}</div>
              <DiffCodeCell className="diff-code-cell diff-code-new" language={language} rowType={row.type} text={row.newText} />
            </div>
          )
        ))}
      </div>
    </Space>
  );
}

function DiffViewerModal({ open, taskId, finding, changedFile, canExpand, onClose }) {
  const diffText = changedFile?.diffText;
  const matchedPath = changedFile?.path || changedFile?.newPath || changedFile?.oldPath || finding?.filePath;

  return (
    <Modal
      title="查看 Diff"
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(1180px, calc(100vw - 32px))"
      className="diff-viewer-modal"
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" className="full-width">
        <div className="diff-viewer-meta">
          <Text strong>{matchedPath || '-'}</Text>
          <Space wrap>
            {changedFile?.changeType && <Tag>{changedFile.changeType}</Tag>}
            {changedFile?.source && <Tag color="blue">{changedFile.source}</Tag>}
            {finding?.startLine != null && <Tag color="gold">定位 {codeLocationText(finding.filePath, finding.startLine, finding.endLine)}</Tag>}
          </Space>
        </div>
        {!changedFile ? (
          <Empty description="没有找到与该问题匹配的变更文件" />
        ) : !diffText ? (
          <Empty description="当前任务未保存该文件 diff" />
        ) : (
          <ExpandableDiffTable
            taskId={taskId}
            filePath={matchedPath}
            diffText={diffText}
            canExpand={canExpand}
            targetStartLine={finding?.startLine}
            targetEndLine={finding?.endLine}
            ariaLabel="Side by side diff"
          />
        )}
      </Space>
    </Modal>
  );
}

function PatchPreviewTable({ filePath, patchText }) {
  return (
    <ExpandableDiffTable
      filePath={filePath}
      diffText={patchText}
      viewType="FIX_PREVIEW"
      ariaLabel="Fix preview patch"
    />
  );
}

function FixPreviewModal({ open, preview, onClose }) {
  return (
    <Modal
      title="AI 修复 Patch 预览"
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(1180px, calc(100vw - 32px))"
      className="diff-viewer-modal"
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" className="full-width">
        <div className="diff-viewer-meta">
          <Text strong>{preview?.filePath || '-'}</Text>
          <Space wrap>
            {preview?.provider && <Tag color="blue">{preview.provider}</Tag>}
            {preview?.model && <Tag>{preview.model}</Tag>}
            {preview?.status && <Tag color={statusColor(preview.status)}>{preview.status}</Tag>}
          </Space>
        </div>
        {preview?.status === 'FAILED' ? (
          <Alert
            type="error"
            showIcon
            message="修复预览生成失败"
            description={preview.errorMessage || '模型没有返回可展示的 unified diff patch。'}
          />
        ) : preview?.patchText ? (
          <>
            {preview.summary && <Alert type="info" showIcon message={preview.summary} />}
            <PatchPreviewTable
              filePath={preview.filePath}
              patchText={preview.patchText}
            />
          </>
        ) : (
          <Empty description="暂无修复预览" />
        )}
      </Space>
    </Modal>
  );
}

function fixPreviewActionText(status) {
  if (status === 'SUCCESS') return '查看修复预览';
  if (status === 'RUNNING') return '修复预览生成中';
  if (status === 'QUEUED') return '修复预览排队中';
  if (status === 'FAILED' || status === 'SKIPPED') return '重新生成修复预览';
  return '生成修复预览';
}

function fixPreviewActionClass(status) {
  if (status === 'SUCCESS') return 'fix-preview-action-success';
  if (status === 'RUNNING' || status === 'QUEUED') return 'fix-preview-action-pending';
  if (status === 'FAILED' || status === 'SKIPPED') return 'fix-preview-action-failed';
  return 'fix-preview-action-idle';
}

const codeQualityViewOptions = [
  { label: 'AI Review 结果', value: 'result' },
  { label: '高准确模式流转', value: 'accuracy-flow' },
  { label: '执行过程', value: 'progress' },
];

function CodeQualityViewSwitcher({ value, onChange }) {
  return (
    <div className="quality-subnav">
      <Segmented
        size="middle"
        value={value}
        options={codeQualityViewOptions}
        onChange={next => onChange(String(next))}
      />
    </div>
  );
}

function CodeQualityReviewView({
  taskId,
  review,
  progress,
  changedFilesSummary,
  diffContextCapabilities,
  initialFixPreviews,
  onRefresh,
  onRetry,
  retrying,
  onCancelReview,
  onCancelFixPreview
}) {
  const location = useLocation();
  const [diffTarget, setDiffTarget] = useState(null);
  const [fixPreviewTarget, setFixPreviewTarget] = useState(null);
  const [fixPreviewByIndex, setFixPreviewByIndex] = useState({});
  const [fixPreviewLoadingIndex, setFixPreviewLoadingIndex] = useState(null);
  const [cancelingAction, setCancelingAction] = useState(null);
  const [activeFindingKeys, setActiveFindingKeys] = useState([]);
  const [qualityView, setQualityView] = useState('result');
  useEffect(() => {
    const previews = Array.isArray(initialFixPreviews) ? initialFixPreviews : [];
    setFixPreviewByIndex(Object.fromEntries(previews.map(item => [item.findingIndex, item])));
  }, [initialFixPreviews]);
  useEffect(() => {
    const match = /^#fix-preview-(\d+)$/.exec(location.hash || '');
    if (!match) return;
    const key = `finding-${match[1]}`;
    setActiveFindingKeys(current => current.includes(key) ? current : [...current, key]);
    window.setTimeout(() => {
      document.getElementById(`fix-preview-${match[1]}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 180);
  }, [location.hash, review?.id]);
  if (!review) {
    const emptyResultContent = (
      <Card>
        <Empty description="暂无代码质量 Review 结果" />
        <div className="empty-action-row">
          <Button type="primary" loading={retrying} onClick={() => onRetry?.()}>重试 AI Review</Button>
        </div>
      </Card>
    );
    return (
      <Space direction="vertical" size="large" className="full-width">
        <CodeQualityViewSwitcher value={qualityView} onChange={setQualityView} />
        {qualityView === 'result' && emptyResultContent}
        {qualityView === 'accuracy-flow' && <HighAccuracyFlowView progress={progress} review={review} />}
        {qualityView === 'progress' && <CodeQualityProgressView progress={progress} />}
      </Space>
    );
  }

  const findings = Array.isArray(review.findings) ? review.findings : [];
  const summaryText = codeQualitySummary(review, findings);
  const activeChangedFile = diffTarget?.changedFile || null;
  const generateFixPreview = async index => {
    const cached = fixPreviewByIndex[index];
    if (cached?.status === 'SUCCESS') {
      setFixPreviewTarget(cached);
      return;
    }
    setFixPreviewLoadingIndex(index);
    try {
      const preview = await fetchApi(`/api/review-tasks/${taskId}/code-quality-fix-preview`, {
        method: 'POST',
        body: JSON.stringify({
          findingIndex: index,
          reviewKey: review?.reviewKey,
          forceRegenerate: cached?.status === 'FAILED' || cached?.status === 'SKIPPED'
        })
      });
      setFixPreviewByIndex(current => ({ ...current, [index]: preview }));
      if (preview?.status === 'SUCCESS') {
        setFixPreviewTarget(preview);
      } else if (preview?.status === 'QUEUED') {
        requestJobQueueRefresh();
        message.info('修复预览已进入队列');
      }
    } catch (err) {
      message.error(err.message);
    } finally {
      setFixPreviewLoadingIndex(null);
    }
  };
  const cancelReview = async () => {
    const key = `review-${review?.reviewKey || 'default'}`;
    setCancelingAction(key);
    try {
      await onCancelReview?.({ jobType: 'AI_REVIEW', reviewKey: review?.reviewKey });
      message.success('AI Review 已中断');
    } catch (err) {
      message.error(err.message);
    } finally {
      setCancelingAction(null);
    }
  };
  const cancelFixPreview = async index => {
    const key = `fix-${index}`;
    setCancelingAction(key);
    try {
      await onCancelFixPreview?.({ jobType: 'FIX_PREVIEW', reviewKey: review?.reviewKey, findingIndex: index });
      message.success('修复预览已中断');
    } catch (err) {
      message.error(err.message);
    } finally {
      setCancelingAction(null);
    }
  };
  const resultContent = (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Space direction="vertical" size="small" className="full-width">
          <div className="quality-result-head">
            <Space wrap>
              <Tag color={statusColor(review.status)}>{review.status || '-'}</Tag>
              <Tag color="blue">{review.provider || '-'}</Tag>
              {review.model && <Tag>{review.model}</Tag>}
              {review.overallLevel && <Tag color={riskColor(review.overallLevel)}>{severityLabel(review.overallLevel)}</Tag>}
              <Tag>{review.findingCount ?? findings.length} 个问题</Tag>
            </Space>
            <Space>
              {review.status === 'RUNNING' && (
                <Button
                  danger
                  icon={<CloseOutlined />}
                  loading={cancelingAction === `review-${review?.reviewKey || 'default'}`}
                  onClick={cancelReview}
                >
                  中断 AI Review
                </Button>
              )}
              <Button loading={retrying} disabled={review.status === 'RUNNING'} onClick={() => onRetry?.(review?.reviewKey)}>重试 AI Review</Button>
            </Space>
          </div>
          <Alert type={findings.length > 0 ? 'warning' : 'info'} showIcon message={summaryText} />
          {review.status === 'RUNNING' && <Alert type="info" showIcon message="AI Review 正在执行" description="模型 Provider 正在分析代码变更，完成后结果会自动刷新。" />}
          {review.errorMessage && review.status === 'SKIPPED' && <Alert type="warning" showIcon message="AI Review 未执行" description={review.errorMessage} />}
          {review.errorMessage && review.status !== 'SKIPPED' && <Alert type="error" showIcon message="AI Review 执行失败" description={review.errorMessage} />}
          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
            <Descriptions.Item label="Profile">{review.profileCode || '-'}</Descriptions.Item>
            <Descriptions.Item label="开始时间">{review.startedAt || '-'}</Descriptions.Item>
            <Descriptions.Item label="结束时间">{review.finishedAt || '-'}</Descriptions.Item>
            <Descriptions.Item label="Exit Code">{review.exitCode ?? '-'}</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
      <Card title="质量问题">
        {findings.length === 0 ? (
          <Empty description="暂无结构化问题" />
        ) : (
          <Collapse
            activeKey={activeFindingKeys}
            onChange={keys => setActiveFindingKeys(Array.isArray(keys) ? keys : [keys])}
            items={findings.map((finding, index) => {
              const fixPreviewStatus = fixPreviewByIndex[index]?.status;
              const fixPreviewBusy = fixPreviewStatus === 'RUNNING' || fixPreviewStatus === 'QUEUED';
              const fixPreviewLoading = fixPreviewLoadingIndex === index || fixPreviewStatus === 'RUNNING';
              return {
                key: `finding-${index}`,
                label: (
                  <Space className="risk-item-heading" wrap>
                    <Tag color={severityColor(finding.severity)}>{severityLabel(finding.severity)}</Tag>
                    {finding.category && <Tag color="blue">{categoryLabel(finding.category)}</Tag>}
                    {finding.confidence && <Tag color={confidenceColor(finding.confidence)}>置信度 {confidenceLabel(finding.confidence)}</Tag>}
                    {finding.contextStatus && <Tag color={contextStatusColor(finding.contextStatus)}>上下文 {contextStatusLabel(finding.contextStatus)}</Tag>}
                    <Text strong>{cleanAiMarkdown(finding.title) || '未命名问题'}</Text>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" className="full-width" id={`fix-preview-${index}`}>
                    <Descriptions size="small" className="quality-finding-meta" column={{ xs: 1, md: 6 }}>
                      <Descriptions.Item label="位置" span={4}>
                        <Space className="code-location-row" wrap>
                          <Text code className="code-location-text">
                            {codeLocationText(finding.filePath, finding.startLine, finding.endLine)}
                          </Text>
                          <Button
                            size="small"
                            icon={<FileSearchOutlined />}
                            className="finding-action-button finding-diff-action"
                            disabled={!finding.filePath}
                            onClick={() => setDiffTarget({
                              finding,
                              changedFile: findChangedFileForFinding(finding, changedFilesSummary)
                            })}
                          >
                            查看 Diff
                          </Button>
                          <Button
                            size="small"
                            className={`finding-action-button fix-preview-action ${fixPreviewActionClass(fixPreviewStatus)}`}
                            loading={fixPreviewLoading}
                            disabled={!taskId || review.status === 'RUNNING' || !finding.filePath || fixPreviewBusy}
                            onClick={() => generateFixPreview(index)}
                          >
                            {fixPreviewActionText(fixPreviewStatus)}
                          </Button>
                          {fixPreviewBusy && (
                            <Button
                              danger
                              size="small"
                              icon={<CloseOutlined />}
                              loading={cancelingAction === `fix-${index}`}
                              onClick={() => cancelFixPreview(index)}
                            >
                              中断
                            </Button>
                          )}
                          <FindingRefinementControl
                            taskId={taskId}
                            review={review}
                            finding={finding}
                            findingIndex={index}
                            onRefresh={onRefresh}
                          />
                        </Space>
                      </Descriptions.Item>
                      <Descriptions.Item label="来源">{sourceLabel(finding.source || review.provider)}</Descriptions.Item>
                      <Descriptions.Item label="分类">{categoryLabel(finding.category)}</Descriptions.Item>
                    </Descriptions>
                    {finding.body && <Paragraph>{cleanAiMarkdown(finding.body)}</Paragraph>}
                    {finding.suggestion && <Alert type="info" showIcon message="建议" description={finding.suggestion} />}
                    <FindingContext finding={finding} />
                    <FindingRefinementPanel overlay={finding.refinementOverlay} />
                    <ReviewFeedbackControl
                      taskId={taskId}
                      sourceType="AI_FINDING"
                      itemFingerprint={finding.fingerprint}
                      feedback={finding.feedback}
                      compact
                      payload={{
                        reviewKey: review?.reviewKey,
                        findingIndex: index,
                        riskType: finding.category,
                        riskTitle: finding.title,
                        originalRiskLevel: finding.severity
                      }}
                    />
                    <EvaluationCaseControl
                      taskId={taskId}
                      review={review}
                      finding={finding}
                      compact
                    />
                  </Space>
                )
              };
            })}
          />
        )}
      </Card>
    </Space>
  );

  return (
    <Space direction="vertical" size="large" className="full-width">
      <CodeQualityViewSwitcher value={qualityView} onChange={setQualityView} />
      {qualityView === 'result' && resultContent}
      {qualityView === 'accuracy-flow' && <HighAccuracyFlowView progress={progress} review={review} />}
      {qualityView === 'progress' && (
        <CodeQualityProgressView
          progress={progress}
          running={review.status === 'RUNNING'}
          reviewStartedAt={review.startedAt}
          reviewFinishedAt={review.finishedAt}
        />
      )}
      <DiffViewerModal
        open={Boolean(diffTarget)}
        taskId={taskId}
        finding={diffTarget?.finding}
        changedFile={activeChangedFile}
        canExpand={diffContextCapabilities?.diff}
        onClose={() => setDiffTarget(null)}
      />
      <FixPreviewModal
        open={Boolean(fixPreviewTarget)}
        preview={fixPreviewTarget}
        onClose={() => setFixPreviewTarget(null)}
      />
    </Space>
  );
}

function codeQualityReviewTabLabel(review) {
  const providerLabel = sourceLabel(review?.provider);
  if (providerLabel && providerLabel !== '-') return providerLabel;
  return review?.displayName || review?.model || '-';
}

function CodeQualityReviewsPanel({
  taskId,
  reviews,
  progress,
  changedFilesSummary,
  diffContextCapabilities,
  fixPreviews,
  selectedReviewKey,
  onRefresh,
  onRetry,
  retrying,
  onCancelReview,
  onCancelFixPreview
}) {
  const reviewItems = Array.isArray(reviews) ? reviews : [];
  const requestedReviewKey = reviewItems.some(review => review.reviewKey === selectedReviewKey)
    ? selectedReviewKey
    : undefined;
  if (reviewItems.length <= 1) {
    const review = reviewItems[0] || null;
    return (
      <CodeQualityReviewView
        taskId={taskId}
        review={review}
        progress={progress}
        changedFilesSummary={changedFilesSummary}
        diffContextCapabilities={diffContextCapabilities}
        initialFixPreviews={fixPreviews}
        onRefresh={onRefresh}
        onRetry={onRetry}
        retrying={retrying}
        onCancelReview={onCancelReview}
        onCancelFixPreview={onCancelFixPreview}
      />
    );
  }
  return (
    <Tabs
      defaultActiveKey={requestedReviewKey}
      items={reviewItems.map((review, index) => ({
        key: review.reviewKey || String(review.id || index),
        label: codeQualityReviewTabLabel(review),
        children: (
          <CodeQualityReviewView
            taskId={taskId}
            review={review}
            progress={(progress || []).filter(item => review.reviewKey ? item.reviewKey === review.reviewKey : !item.reviewKey)}
            changedFilesSummary={changedFilesSummary}
            diffContextCapabilities={diffContextCapabilities}
            initialFixPreviews={(fixPreviews || []).filter(item => item.reviewKey === review.reviewKey)}
            onRefresh={onRefresh}
            onRetry={onRetry}
            retrying={retrying}
            onCancelReview={onCancelReview}
            onCancelFixPreview={onCancelFixPreview}
          />
        )
      }))}
    />
  );
}

function deterministicCheckStatusColor(status) {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'COMPLETED') return 'green';
  if (normalized === 'FAILED') return 'red';
  if (normalized === 'NOT_APPLICABLE') return 'default';
  if (normalized === 'RUNNING') return 'blue';
  return 'default';
}

function deterministicCheckStatusText(status) {
  const normalized = String(status || '').toUpperCase();
  return {
    COMPLETED: '已完成',
    FAILED: '失败',
    NOT_APPLICABLE: '不适用',
    NOT_RUN: '未运行',
    RUNNING: '运行中',
  }[normalized] || (status || '未运行');
}

function DeterministicChecksPanel({ checks, running, onRun }) {
  const latest = checks?.latestRun || null;
  const status = latest?.status || checks?.status || 'NOT_RUN';
  const summary = latest?.resultSummary || {};
  const config = latest?.configSnapshot || {};
  const findings = safeArray(latest?.findings);
  const ruleTypeCounts = summary.ruleTypeCounts || {};
  const findingColumns = [
    { title: '规则类型', dataIndex: 'ruleType', width: 220, render: value => <Tag color="orange">{value || '-'}</Tag> },
    { title: '文件', dataIndex: 'filePath', ellipsis: true, render: value => value || '-' },
    { title: '行号', dataIndex: 'lineNumber', width: 90, render: value => value || '-' },
    { title: 'Hunk 位置', dataIndex: 'hunkPosition', width: 110, render: value => value || '-' },
    { title: '脱敏证据', dataIndex: 'evidence', ellipsis: true, render: value => <Text code>{value || '-'}</Text> },
  ];
  return (
    <Space direction="vertical" size="middle" className="full-width">
      <Card
        title="确定性检查 · 敏感信息扫描"
        extra={(
          <Button icon={<ReloadOutlined />} loading={running} onClick={onRun}>
            {latest ? '重新运行敏感信息扫描' : '运行敏感信息扫描'}
          </Button>
        )}
      >
        <Space direction="vertical" size="middle" className="full-width">
          <Alert
            type={status === 'FAILED' ? 'error' : 'info'}
            showIcon
            message={latest ? '检查结果仅作为结构化证据' : '当前任务暂无确定性检查记录'}
            description={latest
              ? '敏感信息扫描只检查当前任务 diff 新增行，命中项已脱敏；结果不会自动阻塞合并、修改 AI Review 或生成项目策略。'
              : (checks?.explanation || '点击运行后，会扫描当前任务 changed files / diff 的新增行。')}
          />
          <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
            <Descriptions.Item label="状态">
              <Tag color={deterministicCheckStatusColor(status)}>{deterministicCheckStatusText(status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="检查类型">{latest?.checkType || 'SECRET_SCAN'}</Descriptions.Item>
            <Descriptions.Item label="规则集">{config.rulesetVersion || '-'}</Descriptions.Item>
            <Descriptions.Item label="扫描范围">{config.scope || 'DIFF_ADDED_LINES'}</Descriptions.Item>
            <Descriptions.Item label="扫描文件数"><Text strong>{countText(summary.scannedFileCount)}</Text></Descriptions.Item>
            <Descriptions.Item label="新增行数"><Text strong>{countText(summary.addedLineCount)}</Text></Descriptions.Item>
            <Descriptions.Item label="命中数"><Text strong>{countText(summary.findingCount)}</Text></Descriptions.Item>
            <Descriptions.Item label="耗时">{latest?.durationMs != null ? `${latest.durationMs} ms` : '-'}</Descriptions.Item>
            <Descriptions.Item label="结果截断">
              {summary.truncated ? <Tag color="orange">已截断</Tag> : <Tag>未截断</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="配置来源">{config.configSource || '-'}</Descriptions.Item>
            <Descriptions.Item label="最大命中数">{config.maxFindings ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="完成时间">{latest?.finishedAt || '-'}</Descriptions.Item>
          </Descriptions>
          {latest?.failureReason && (
            <Alert type="warning" showIcon message="失败原因" description={latest.failureReason} />
          )}
          <Card size="small" title="规则命中摘要">
            {Object.keys(ruleTypeCounts).length === 0 ? (
              <Empty description="暂无规则命中" />
            ) : (
              <Space wrap>
                {Object.entries(ruleTypeCounts).map(([ruleType, count]) => (
                  <Tag key={ruleType} color="orange">{ruleType}: {countText(count)}</Tag>
                ))}
              </Space>
            )}
          </Card>
          <Card size="small" title="命中项">
            {findings.length === 0 ? (
              <Empty description="暂无命中项" />
            ) : (
              <Table
                rowKey={(row, index) => `${row.ruleType}-${row.filePath}-${row.lineNumber || row.hunkPosition}-${index}`}
                size="small"
                columns={findingColumns}
                dataSource={findings}
                pagination={false}
                scroll={{ x: 900 }}
              />
            )}
          </Card>
        </Space>
      </Card>
    </Space>
  );
}

function TaskDetail({ taskId, onBack, onOpen }) {
  const location = useLocation();
  const selectedReviewKey = new URLSearchParams(location.search).get('reviewKey');
  const [detail, setDetail] = useState(null);
  const [result, setResult] = useState(null);
  const [codeQualityResult, setCodeQualityResult] = useState(null);
  const [codeQualityResults, setCodeQualityResults] = useState([]);
  const [codeQualityProgress, setCodeQualityProgress] = useState([]);
  const [codeQualityGate, setCodeQualityGate] = useState(null);
  const [fixPreviews, setFixPreviews] = useState([]);
  const [deterministicChecks, setDeterministicChecks] = useState(null);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [runningDeterministicCheck, setRunningDeterministicCheck] = useState(false);
  const [error, setError] = useState(null);
  const [activeTabKey, setActiveTabKey] = useState('quality');

  const load = async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const taskDetail = await fetchApi(`/api/review-tasks/${taskId}`);
      setDetail(taskDetail);
      try {
        const taskResult = await fetchApi(`/api/review-tasks/${taskId}/result`);
        setResult(taskResult);
      } catch {
        setResult(null);
      }
      try {
        const qualityResults = await fetchApi(`/api/review-tasks/${taskId}/code-quality-results`);
        const normalizedResults = Array.isArray(qualityResults) ? qualityResults : [];
        setCodeQualityResults(normalizedResults);
        setCodeQualityResult(normalizedResults[0] || null);
      } catch {
        try {
          const qualityResult = await fetchApi(`/api/review-tasks/${taskId}/code-quality-result`);
          setCodeQualityResult(qualityResult);
          setCodeQualityResults(qualityResult ? [qualityResult] : []);
        } catch {
          setCodeQualityResult(null);
          setCodeQualityResults([]);
        }
      }
      try {
        const gate = await fetchApi(`/api/review-tasks/${taskId}/code-quality-gate`);
        setCodeQualityGate(gate);
      } catch {
        setCodeQualityGate(null);
      }
      try {
        const progress = await fetchApi(`/api/review-tasks/${taskId}/code-quality-progress`);
        setCodeQualityProgress(Array.isArray(progress) ? progress : []);
      } catch {
        setCodeQualityProgress([]);
      }
      try {
        const previews = await fetchApi(`/api/review-tasks/${taskId}/code-quality-fix-previews`);
        setFixPreviews(Array.isArray(previews) ? previews : []);
      } catch {
        setFixPreviews([]);
      }
      try {
        const checks = await fetchApi(`/api/review-tasks/${taskId}/deterministic-checks`);
        setDeterministicChecks(checks);
      } catch {
        setDeterministicChecks(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    load();
  }, [taskId]);

  useEffect(() => {
    if (/^#risk-item-/.test(location.hash || '')) {
      setActiveTabKey('risk');
      return;
    }
    if (/^#fix-preview-/.test(location.hash || '')) {
      setActiveTabKey('quality');
    }
  }, [location.hash, taskId]);

  useEffect(() => {
    const hasRunningFixPreview = fixPreviews.some(item => ['QUEUED', 'RUNNING'].includes(item?.status));
    const hasRunningReview = codeQualityResults.some(item => item?.status === 'RUNNING');
    if (!hasRunningReview && codeQualityResult?.status !== 'RUNNING' && !hasRunningFixPreview) return undefined;
    const timer = window.setInterval(() => load({ silent: true }), 5000);
    return () => window.clearInterval(timer);
  }, [taskId, codeQualityResult?.status, codeQualityResults, fixPreviews]);

  const retryCodeQualityReview = async reviewKey => {
    setRetrying(true);
    setError(null);
    try {
      const retryResult = await fetchApi(`/api/code-quality-reviews/tasks/${taskId}/retry`, {
        method: 'POST',
        body: reviewKey ? JSON.stringify({ reviewKey }) : undefined
      });
      const optimisticReviews = (retryResult.reviews || [retryResult]).map(item => ({
        taskId: retryResult.taskId,
        projectId: detail?.projectId,
        reviewKey: item.reviewKey,
        profileCode: item.profileCode || retryResult.profileCode,
        provider: item.provider || retryResult.provider,
        model: item.model,
        displayName: item.displayName,
        status: item.status || retryResult.status,
        overallLevel: item.overallLevel || retryResult.overallLevel,
        summary: 'AI code review is running',
        findingCount: item.findingCount ?? retryResult.findingCount,
        findings: []
      }));
      setCodeQualityResults(current => {
        if (!reviewKey) return optimisticReviews;
        const byKey = new Map(optimisticReviews.map(item => [item.reviewKey, item]));
        const merged = current.map(item => byKey.get(item.reviewKey) || item);
        const knownKeys = new Set(current.map(item => item.reviewKey));
        return [...merged, ...optimisticReviews.filter(item => !knownKeys.has(item.reviewKey))];
      });
      setCodeQualityResult(current => (
        reviewKey
          ? optimisticReviews.find(item => item.reviewKey === current?.reviewKey) || current
          : optimisticReviews[0] || null
      ));
      setCodeQualityProgress(current => {
        const localQueued = {
          id: `local-queued-${reviewKey || 'all'}`,
          taskId,
          reviewKey: reviewKey || retryResult.reviewKey,
          phase: 'QUEUED',
          level: 'INFO',
          message: 'AI Review 已重新进入执行队列',
          detail: `provider=${retryResult.provider}, profile=${retryResult.profileCode}`,
          createdAt: new Date().toISOString()
        };
        if (!reviewKey) return [localQueued];
        return [...current.filter(item => item.reviewKey !== reviewKey), localQueued];
      });
      setFixPreviews(current => (
        reviewKey ? current.filter(item => item.reviewKey !== reviewKey) : []
      ));
      requestJobQueueRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRetrying(false);
    }
  };

  const cancelCodeQualityJob = async request => {
    setError(null);
    try {
      await fetchApi(`/api/code-quality-reviews/tasks/${taskId}/cancel`, {
        method: 'POST',
        body: JSON.stringify(request || {})
      });
      requestJobQueueRefresh();
      await load({ silent: true });
    } catch (err) {
      setError(err.message);
      throw err;
    }
  };

  const runDeterministicCheck = async () => {
    setRunningDeterministicCheck(true);
    setError(null);
    try {
      const run = await fetchApi(`/api/review-tasks/${taskId}/deterministic-checks/run`, {
        method: 'POST',
        body: JSON.stringify({ checkType: 'SECRET_SCAN' })
      });
      setDeterministicChecks(current => ({
        taskId,
        status: run.status,
        latestRun: run,
        runs: [run, ...safeArray(current?.runs).filter(item => item.id !== run.id)].slice(0, 10),
        explanation: null,
      }));
      message.success('敏感信息扫描已完成');
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningDeterministicCheck(false);
    }
  };

  const rerunReviewTask = async () => {
    setRerunning(true);
    setError(null);
    try {
      const rerunResult = await fetchApi(`/api/review-tasks/${taskId}/rerun-in-place`, { method: 'POST' });
      requestJobQueueRefresh();
      await load();
      if (rerunResult?.status === 'SUCCESS' || rerunResult?.status === 'RUNNING') {
        message.success('已在当前任务重新执行审阅');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setRerunning(false);
    }
  };

  const cloneAndRerunReviewTask = async () => {
    setRerunning(true);
    setError(null);
    try {
      const rerunResult = await fetchApi(`/api/review-tasks/${taskId}/rerun`, { method: 'POST' });
      requestJobQueueRefresh();
      if (rerunResult?.taskId) {
        onOpen(rerunResult.taskId);
      } else {
        await load();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setRerunning(false);
    }
  };

  const tabItems = useMemo(() => [
    { key: 'quality', label: '代码质量 Review', children: <CodeQualityReviewsPanel taskId={taskId} reviews={codeQualityResults} progress={codeQualityProgress} changedFilesSummary={detail?.changedFilesSummary} diffContextCapabilities={detail?.diffContextCapabilities} fixPreviews={fixPreviews} selectedReviewKey={selectedReviewKey} onRefresh={() => load({ silent: true })} onRetry={retryCodeQualityReview} retrying={retrying} onCancelReview={cancelCodeQualityJob} onCancelFixPreview={cancelCodeQualityJob} /> },
    { key: 'deterministic', label: '确定性检查', children: <DeterministicChecksPanel checks={deterministicChecks} running={runningDeterministicCheck} onRun={runDeterministicCheck} /> },
    ...(detail?.triggerType === 'GITLAB_PUSH_WEBHOOK'
      ? [{ key: 'gate', label: 'Push 审核', children: <CodeQualityGateView gate={codeQualityGate} detail={detail} /> }]
      : []),
    ...(result?.reminderCardEnabled !== false
      ? [{ key: 'risk', label: '提醒卡片', children: <RiskCardView taskId={taskId} riskCard={result?.riskCard} changedFilesSummary={detail?.changedFilesSummary} /> }]
      : []),
    { key: 'analysis', label: '分析结果', children: <AnalysisView changeAnalysis={result?.changeAnalysis} /> },
    { key: 'event', label: '原始事件摘要', children: <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card title="changedFiles 摘要"><JsonBlock value={detail?.changedFilesSummary} /></Card></Col><Col xs={24} lg={12}><Card title="raw payload"><JsonBlock value={detail?.rawPayload} /></Card></Col></Row> }
  ], [taskId, detail, result, codeQualityResults, codeQualityProgress, codeQualityGate, fixPreviews, deterministicChecks, selectedReviewKey, retrying, runningDeterministicCheck]);
  const displayedActiveTabKey = tabItems.some(item => item.key === activeTabKey)
    ? activeTabKey
    : tabItems[0]?.key;

  return (
    <div className="page-shell">
      <Space className="detail-toolbar">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回上一层</Button>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={rerunning}
          disabled={!detail || !['GITLAB_MR_WEBHOOK', 'GITLAB_PUSH_WEBHOOK'].includes(detail.triggerType)}
          onClick={rerunReviewTask}
        >
          重新执行审阅
        </Button>
        <Button
          disabled={!detail || rerunning || !['GITLAB_MR_WEBHOOK', 'GITLAB_PUSH_WEBHOOK'].includes(detail.triggerType)}
          onClick={cloneAndRerunReviewTask}
        >
          复制为新任务重跑
        </Button>
      </Space>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        {detail ? (
          <Space direction="vertical" size="large" className="full-width">
            <Card>
              <div className="detail-title-row">
                <div>
                  <Title level={3}>{taskTitle(detail)}</Title>
                  <Text type="secondary">{branchSummary(detail)}</Text>
                </div>
                <Space>
                  <Tag color={taskReviewStatusColor(detail.reviewStatus)}>{taskReviewStatusLabel(detail.reviewStatus)}</Tag>
                </Space>
              </div>
              <Divider />
              <Descriptions column={{ xs: 1, md: 2, xl: 3 }} size="small">
                <Descriptions.Item label="任务 ID">{detail.id}</Descriptions.Item>
                <Descriptions.Item label="GitLab 项目">
                  <Space size={4}>
                    <span>{detail.gitProjectId}</span>
                    {detail.externalUrl && (
                      <Button
                        type="link"
                        size="small"
                        icon={<ExportOutlined />}
                        href={detail.externalUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        跳转 GitLab
                      </Button>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="触发类型">{detail.triggerType}</Descriptions.Item>
                <Descriptions.Item label="作者">{detail.authorName || detail.authorUsername || '-'}</Descriptions.Item>
                <Descriptions.Item label="模板">{detail.templateCode}</Descriptions.Item>
                <Descriptions.Item label="端类型">{targetTypeLabel(detail.targetType)}</Descriptions.Item>
                <Descriptions.Item label="Profile">{detail.codeQualityProfileCode || '-'}</Descriptions.Item>
                <Descriptions.Item label="底层任务状态">{detail.status || '-'}</Descriptions.Item>
                <Descriptions.Item label="事件时间">{detail.eventTime || '-'}</Descriptions.Item>
              </Descriptions>
              {detail.errorMessage && (
                <Alert className="section-gap" type="error" showIcon message="任务执行失败" description={detail.errorMessage} />
              )}
            </Card>
            <Tabs activeKey={displayedActiveTabKey} onChange={setActiveTabKey} items={tabItems} />
          </Space>
        ) : !loading ? <Empty description="任务不存在" /> : null}
      </Spin>
    </div>
  );
}


function TemplateConfig() {
  const [groups, setGroups] = useState([]);
  const [groupDraft, setGroupDraft] = useState({ groupName: '', groupCode: '', description: '', defaultCodeQualityProfileCode: null, defaultProviderCode: null, aiReviewModels: [], dingtalkWebhooks: [] });
  const [editingGroupId, setEditingGroupId] = useState(null);
  const [editingGroupDraft, setEditingGroupDraft] = useState(null);
  const [projectGroupFilter, setProjectGroupFilter] = useState(null);
  const [projectDraft, setProjectDraft] = useState({
    name: '',
    gitProjectId: '',
    repositoryUrl: '',
    groupId: null,
    targetType: 'BACKEND'
  });
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [projectConfigDraft, setProjectConfigDraft] = useState(null);
  const [projectTargetConfigs, setProjectTargetConfigs] = useState([]);
  const [targetPathMappings, setTargetPathMappings] = useState([]);
  const [selectedTargetType, setSelectedTargetType] = useState(null);
  const [targetConfigDraft, setTargetConfigDraft] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [providers, setProviders] = useState([]);
  const [selectedProviderCode, setSelectedProviderCode] = useState('DEEPSEEK');
  const [providerDraft, setProviderDraft] = useState(null);
  const [selectedProfileCode, setSelectedProfileCode] = useState(null);
  const [profileDraft, setProfileDraft] = useState(null);
  const [selectedPushPolicyGroupId, setSelectedPushPolicyGroupId] = useState(null);
  const [pushPolicyDraft, setPushPolicyDraft] = useState(null);
  const [promptPreview, setPromptPreview] = useState(null);
  const [aiSettings, setAiSettings] = useState(null);
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [providerApiKeyDraft, setProviderApiKeyDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [projectGroupCreating, setProjectGroupCreating] = useState(false);
  const [projectGroupSavingId, setProjectGroupSavingId] = useState(null);
  const [projectGroupDisablingId, setProjectGroupDisablingId] = useState(null);
  const [projectCreating, setProjectCreating] = useState(false);
  const [projectConfigSaving, setProjectConfigSaving] = useState(false);
  const [targetPathMappingSaving, setTargetPathMappingSaving] = useState(false);
  const [projectConfigReloading, setProjectConfigReloading] = useState(false);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerTesting, setProviderTesting] = useState(false);
  const [providerTestResult, setProviderTestResult] = useState(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [pushPolicySaving, setPushPolicySaving] = useState(false);
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false);
  const [error, setError] = useState(null);
  const [messageApi, contextHolder] = message.useMessage();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsData, profileData, providerData, groupData, projectData, pathMappingData] = await Promise.all([
        fetchApi('/api/code-quality-reviews/settings'),
        fetchApi('/api/code-quality-review-profiles'),
        fetchApi('/api/code-quality-review-providers'),
        fetchApi('/api/project-groups'),
        fetchApi('/api/projects?includeDisabled=true'),
        fetchApi('/api/target-type-path-mappings')
      ]);
      const profileItems = Array.isArray(profileData) ? profileData : (profileData.items || []);
      const selectableProfileItems = selectableReviewProfiles(profileItems);
      const providerItems = Array.isArray(providerData) ? providerData : (providerData.items || []);
      const nextSelectedProfileCode = (
        selectedProfileCode && selectableProfileItems.some(profile => profile.profileCode === selectedProfileCode)
      )
        ? selectedProfileCode
        : selectableProfileItems[0]?.profileCode || null;
      const nextSelectedProviderCode = settingsData?.defaultProviderCode || selectedProviderCode || providerItems[0]?.providerCode || 'DEEPSEEK';
      const projectItems = projectData.items || [];
      const groupItems = groupData.items || [];
      const nextPushPolicyGroupId = selectedPushPolicyGroupId && groupItems.some(group => group.id === selectedPushPolicyGroupId)
        ? selectedPushPolicyGroupId
        : groupItems[0]?.id || null;
      const nextSelectedProjectId = projectGroupFilter
        ? (projectItems.some(project => project.id === selectedProjectId && project.groupId === projectGroupFilter)
          ? selectedProjectId
          : projectItems.find(project => project.groupId === projectGroupFilter)?.id || null)
        : null;
      setAiSettings(settingsData);
      setSettingsDraft({
        reviewEnabled: settingsData?.reviewEnabled ?? false,
        dingtalkNotificationEnabled: settingsData?.dingtalkNotificationEnabled ?? true,
        autoFixPreviewEnabled: settingsData?.autoFixPreviewEnabled ?? false,
        autoFixPreviewSeverities: normalizeAutoFixPreviewSeverities(settingsData?.autoFixPreviewSeverities)
      });
      setGroups(groupItems);
      setTargetPathMappings(Array.isArray(pathMappingData) ? pathMappingData : []);
      setSelectedPushPolicyGroupId(nextPushPolicyGroupId);
      setPushPolicyDraft(pushPolicyFromGroup(groupItems.find(group => group.id === nextPushPolicyGroupId)));
      setProjects(projectItems);
      setSelectedProjectId(nextSelectedProjectId);
      if (nextSelectedProjectId) {
        const nextProject = projectItems.find(project => project.id === nextSelectedProjectId);
        const configs = await fetchApi(`/api/projects/${nextSelectedProjectId}/target-configs`);
        setProjectTargetConfigs(configs || []);
        const enabledTarget = (configs || []).find(item => item.enabled !== false)?.targetType;
        const target = selectedTargetType || enabledTarget || configs?.[0]?.targetType || nextProject?.supportedTargetTypes?.[0] || 'BACKEND';
        setProjectConfigDraft({ groupId: nextProject?.groupId || null, targetType: target });
        setSelectedTargetType(target);
        setTargetConfigDraft((configs || []).find(item => item.targetType === target) || null);
      } else {
        setProjectConfigDraft(null);
        setProjectTargetConfigs([]);
        setSelectedTargetType(null);
        setTargetConfigDraft(null);
      }
      setProviders(providerItems);
      setSelectedProviderCode(nextSelectedProviderCode);
      setProviderDraft(providerItems.find(item => item.providerCode === nextSelectedProviderCode) || providerItems[0] || null);
      setProviderApiKeyDraft('');
      setProfiles(profileItems);
      setSelectedProfileCode(nextSelectedProfileCode);
      setProfileDraft(profileItems.find(item => item.profileCode === nextSelectedProfileCode) || selectableProfileItems[0] || null);
      setPromptPreview(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const loadProjectTargetConfigs = async (projectId, targetType = selectedTargetType, projectList = projects) => {
    if (!projectId) {
      setSelectedProjectId(null);
      setProjectConfigDraft(null);
      setSelectedTargetType(null);
      setProjectTargetConfigs([]);
      setTargetConfigDraft(null);
      return;
    }
    const configs = await fetchApi(`/api/projects/${projectId}/target-configs`);
    setProjectTargetConfigs(configs || []);
    const project = projectList.find(item => item.id === projectId);
    const enabledTarget = (configs || []).find(item => item.enabled !== false)?.targetType;
    const nextTargetType = targetType || enabledTarget || configs?.[0]?.targetType || project?.supportedTargetTypes?.[0] || 'BACKEND';
    setProjectConfigDraft({ groupId: project?.groupId || null, targetType: nextTargetType });
    setSelectedTargetType(nextTargetType);
    setTargetConfigDraft((configs || []).find(item => item.targetType === nextTargetType) || null);
  };

  const reloadProjectGroupsAndProjects = async (
    preferredProjectId = selectedProjectId,
    preferredTargetType = selectedTargetType,
    groupFilterOverride = projectGroupFilter
  ) => {
    const [groupData, projectData] = await Promise.all([
      fetchApi('/api/project-groups'),
      fetchApi('/api/projects?includeDisabled=true')
    ]);
    const groupItems = groupData.items || [];
    const projectItems = projectData.items || [];
    const activeGroupFilter = groupFilterOverride || null;
    const nextSelectedProjectId = activeGroupFilter && projectItems.some(project => project.id === preferredProjectId && project.groupId === activeGroupFilter)
      ? preferredProjectId
      : (activeGroupFilter ? projectItems.find(project => project.groupId === activeGroupFilter)?.id || null : null);
    setGroups(groupItems);
    setProjects(projectItems);
    setSelectedProjectId(nextSelectedProjectId);
    if (nextSelectedProjectId) {
      await loadProjectTargetConfigs(nextSelectedProjectId, preferredTargetType, projectItems);
    } else {
      setProjectConfigDraft(null);
      setProjectTargetConfigs([]);
      setSelectedTargetType(null);
      setTargetConfigDraft(null);
    }
  };

  const refreshProjectConfigData = async () => {
    setProjectConfigReloading(true);
    try {
      const mappings = await fetchApi('/api/target-type-path-mappings');
      setTargetPathMappings(Array.isArray(mappings) ? mappings : []);
      await reloadProjectGroupsAndProjects();
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectConfigReloading(false);
    }
  };

  const selectProjectForTargetConfig = async (projectId) => {
    setSelectedProjectId(projectId);
    try {
      await loadProjectTargetConfigs(projectId, null);
    } catch (err) {
      messageApi.error(err.message);
    }
  };

  const clearSelectedProjectConfig = () => {
    setSelectedProjectId(null);
    setProjectConfigDraft(null);
    setProjectTargetConfigs([]);
    setSelectedTargetType(null);
    setTargetConfigDraft(null);
  };

  const selectProjectGroupFilter = async (groupId) => {
    const nextGroupId = groupId || null;
    setProjectGroupFilter(nextGroupId);
    if (!nextGroupId) {
      clearSelectedProjectConfig();
      return;
    }
    const nextProject = projects.find(project => project.groupId === nextGroupId);
    if (nextProject) {
      await selectProjectForTargetConfig(nextProject.id);
    } else {
      clearSelectedProjectConfig();
    }
  };

  const updateProjectConfigDraft = (field, value) => {
    setProjectConfigDraft(current => ({ ...(current || {}), [field]: value }));
    if (field === 'targetType' && value) {
      selectTargetTypeForConfig(value);
    }
  };

  const selectTargetTypeForConfig = (targetType) => {
    setSelectedTargetType(targetType);
    setProjectConfigDraft(current => current ? { ...current, targetType } : current);
    setTargetConfigDraft(projectTargetConfigs.find(item => item.targetType === targetType) || {
      targetType,
      templateCode: defaultTemplateCodeForTargetType(targetType),
      providerCode: null,
      pathPatterns: defaultPathPatternsForTargetType(targetType),
      reminderCardEnabled: defaultReminderCardEnabledForTargetType(targetType),
      enabled: true
    });
  };

  const updateTargetConfigDraft = (field, value) => {
    setTargetConfigDraft(current => current ? { ...current, [field]: value } : current);
  };

  const updateGroupDraft = (field, value) => {
    setGroupDraft(current => ({ ...current, [field]: value }));
  };

  const startEditGroup = (group) => {
    setEditingGroupId(group.id);
    setEditingGroupDraft({ ...group, aiReviewModels: normalizeAiReviewModels(group) });
  };

  const updateEditingGroupDraft = (field, value) => {
    setEditingGroupDraft(current => current ? { ...current, [field]: value } : current);
  };

  const normalizeWebhookPayload = (webhooks = []) => webhooks.map(item => ({
    id: item.id || undefined,
    name: (item.name || '').trim(),
    channel: 'DINGTALK',
    webhookUrl: (item.webhookUrl || '').trim(),
    enabled: item.enabled !== false
  }));

  const validateWebhookDrafts = (webhooks = []) => {
    const enabledUrls = new Set();
    for (const item of webhooks) {
      const name = (item.name || '').trim();
      const webhookUrl = (item.webhookUrl || '').trim();
      if (!name) return 'Webhook 名称不能为空';
      if (!webhookUrl) return 'Webhook 地址不能为空';
      try {
        const parsed = new URL(webhookUrl);
        if (!['http:', 'https:'].includes(parsed.protocol)) return 'Webhook 地址必须以 http:// 或 https:// 开头';
      } catch {
        return 'Webhook 地址格式不正确';
      }
      if (item.enabled !== false) {
        const normalized = webhookUrl.toLowerCase();
        if (enabledUrls.has(normalized)) return '同一项目组内已启用的 webhook 地址不能重复';
        enabledUrls.add(normalized);
      }
    }
    return null;
  };

  const updateGroupWebhookDraft = (target, index, field, value) => {
    const updater = current => {
      if (!current) return current;
      const dingtalkWebhooks = (current.dingtalkWebhooks || []).map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      ));
      return { ...current, dingtalkWebhooks };
    };
    if (target === 'editing') {
      setEditingGroupDraft(updater);
    } else {
      setGroupDraft(updater);
    }
  };

  const addGroupWebhookDraft = (target) => {
    const updater = current => ({
      ...(current || {}),
      dingtalkWebhooks: [
        ...((current || {}).dingtalkWebhooks || []),
        { id: null, name: '', channel: 'DINGTALK', webhookUrl: '', enabled: true, status: 'ENABLED' }
      ]
    });
    if (target === 'editing') {
      setEditingGroupDraft(updater);
    } else {
      setGroupDraft(updater);
    }
  };

  const normalizeAiReviewModels = (group) => {
    const rawItems = Array.isArray(group?.aiReviewModels) ? group.aiReviewModels : [];
    if (rawItems.length > 0) {
      return rawItems.map((item, index) => ({
        id: item.id || null,
        reviewKey: item.reviewKey || null,
        providerCode: item.providerCode || group?.defaultProviderCode || '',
        modelName: item.modelName || '',
        displayName: item.displayName || '',
        enabled: item.enabled !== false,
        sortOrder: item.sortOrder ?? (index + 1) * 10
      }));
    }
    if (group?.defaultProviderCode) {
      return [{
        id: null,
        reviewKey: null,
        providerCode: group.defaultProviderCode,
        modelName: '',
        displayName: '',
        enabled: true,
        sortOrder: 10
      }];
    }
    return [];
  };

  const normalizeAiReviewModelPayload = (items = []) => (items || [])
    .filter(item => item?.providerCode && isProviderKeyConfigured(item.providerCode))
    .map((item, index) => ({
      id: item.id || undefined,
      reviewKey: item.reviewKey || undefined,
      providerCode: item.providerCode,
      modelName: item.modelName?.trim() || null,
      displayName: item.displayName?.trim() || null,
      enabled: item.enabled !== false,
      sortOrder: item.sortOrder ?? (index + 1) * 10
    }));

  const selectedAiReviewProviderCodes = (group) => normalizeAiReviewModels(group)
    .filter(item => item.enabled !== false && item.providerCode)
    .map(item => item.providerCode);

  const isProviderKeyConfigured = (providerCode) => {
    const provider = providers.find(item => item.providerCode === providerCode);
    return Boolean(provider?.apiKeyConfigured);
  };

  const aiReviewProviderLabel = (providerCode) => {
    return sourceLabel(providerCode);
  };

  const aiReviewProviderDisplay = (group) => {
    const codes = selectedAiReviewProviderCodes(group);
    if (codes.length === 0) return group?.defaultProviderCode || '-';
    return codes.map(aiReviewProviderLabel).join(' / ');
  };

  const updateGroupAiReviewProviders = (target, providerCodes = []) => {
    const selectableProviderCodes = providerCodes.filter(isProviderKeyConfigured);
    const updater = current => current ? {
      ...current,
      defaultProviderCode: selectableProviderCodes[0] || null,
      aiReviewModels: selectableProviderCodes.map((providerCode, index) => {
        const existing = normalizeAiReviewModels(current).find(item => item.providerCode === providerCode);
        return {
          ...(existing || {}),
          providerCode,
          modelName: '',
          displayName: '',
          enabled: true,
          sortOrder: (index + 1) * 10
        };
      })
    } : current;
    if (target === 'editing') {
      setEditingGroupDraft(updater);
    } else {
      setGroupDraft(updater);
    }
  };

  const removeGroupWebhookDraft = (target, index) => {
    const updater = current => current ? {
      ...current,
      dingtalkWebhooks: (current.dingtalkWebhooks || []).filter((_, itemIndex) => itemIndex !== index)
    } : current;
    if (target === 'editing') {
      setEditingGroupDraft(updater);
    } else {
      setGroupDraft(updater);
    }
  };

  const createProjectGroup = async () => {
    const groupName = groupDraft.groupName.trim();
    const groupCode = groupDraft.groupCode.trim();
    if (!groupName || !groupCode) {
      messageApi.error('项目组名称和编码不能为空');
      return;
    }
    const validationError = validateWebhookDrafts(groupDraft.dingtalkWebhooks || []);
    if (validationError) {
      messageApi.error(validationError);
      return;
    }
    setProjectGroupCreating(true);
    try {
      await fetchApi('/api/project-groups', {
        method: 'POST',
        body: JSON.stringify({
          groupName,
          groupCode,
          description: groupDraft.description?.trim() || null,
          defaultCodeQualityProfileCode: groupDraft.defaultCodeQualityProfileCode || null,
          defaultProviderCode: groupDraft.defaultProviderCode || null,
          aiReviewModels: normalizeAiReviewModelPayload(groupDraft.aiReviewModels || []),
          dingtalkWebhooks: normalizeWebhookPayload(groupDraft.dingtalkWebhooks || [])
        })
      });
      setGroupDraft({ groupName: '', groupCode: '', description: '', defaultCodeQualityProfileCode: null, defaultProviderCode: null, aiReviewModels: [], dingtalkWebhooks: [] });
      await reloadProjectGroupsAndProjects();
      messageApi.success('项目组已创建');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectGroupCreating(false);
    }
  };

  const saveEditingProjectGroup = async () => {
    if (!editingGroupDraft) return;
    const groupName = editingGroupDraft.groupName.trim();
    const groupCode = editingGroupDraft.groupCode.trim();
    if (!groupName || !groupCode) {
      messageApi.error('项目组名称和编码不能为空');
      return;
    }
    const validationError = validateWebhookDrafts(editingGroupDraft.dingtalkWebhooks || []);
    if (validationError) {
      messageApi.error(validationError);
      return;
    }
    setProjectGroupSavingId(editingGroupDraft.id);
    try {
      await fetchApi(`/api/project-groups/${editingGroupDraft.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          groupName,
          groupCode,
          description: editingGroupDraft.description?.trim() || null,
          defaultCodeQualityProfileCode: editingGroupDraft.defaultCodeQualityProfileCode || null,
          defaultProviderCode: editingGroupDraft.defaultProviderCode || null,
          aiReviewModels: normalizeAiReviewModelPayload(editingGroupDraft.aiReviewModels || []),
          status: editingGroupDraft.status || 'ENABLED',
          dingtalkWebhooks: normalizeWebhookPayload(editingGroupDraft.dingtalkWebhooks || [])
        })
      });
      setEditingGroupId(null);
      setEditingGroupDraft(null);
      await reloadProjectGroupsAndProjects();
      messageApi.success('项目组已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectGroupSavingId(null);
    }
  };

  const disableProjectGroup = async (group) => {
    setProjectGroupDisablingId(group.id);
    try {
      await fetchApi(`/api/project-groups/${group.id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: 'DISABLED' })
      });
      if (projectGroupFilter === group.id) setProjectGroupFilter(null);
      await reloadProjectGroupsAndProjects();
      messageApi.success('项目组已停用');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectGroupDisablingId(null);
    }
  };

  const saveSelectedProjectConfig = async () => {
    if (!selectedProjectId || !projectConfigDraft?.groupId || !projectConfigDraft?.targetType) {
      messageApi.error('请选择项目组、项目和所属端类型');
      return;
    }
    setProjectConfigSaving(true);
    try {
      const updatedProject = await fetchApi(`/api/projects/${selectedProjectId}/group`, {
        method: 'PUT',
        body: JSON.stringify({ groupId: projectConfigDraft.groupId })
      });
      const normalizedTargetType = projectConfigDraft.targetType;
      const existing = projectTargetConfigs.find(item => item.targetType === normalizedTargetType);
      const updated = await fetchApi(`/api/projects/${selectedProjectId}/target-configs/${normalizedTargetType}`, {
        method: 'PUT',
        body: JSON.stringify({
          templateCode: defaultTemplateCodeForTargetType(normalizedTargetType),
          providerCode: targetConfigDraft?.providerCode || existing?.providerCode || null,
          pathPatterns: existing?.pathPatterns?.length ? existing.pathPatterns : ['**/*'],
          reminderCardEnabled: existing?.reminderCardEnabled ?? defaultReminderCardEnabledForTargetType(normalizedTargetType),
          enabled: true
        })
      });
      setProjects(current => current.map(project => project.id === updatedProject.id ? updatedProject : project));
      setSelectedTargetType(normalizedTargetType);
      setTargetConfigDraft(updated);
      setProjectConfigDraft({ groupId: updatedProject.groupId || null, targetType: normalizedTargetType });
      setProjectGroupFilter(updatedProject.groupId || null);
      await reloadProjectGroupsAndProjects(selectedProjectId, normalizedTargetType, updatedProject.groupId || null);
      messageApi.success('项目配置已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectConfigSaving(false);
    }
  };

  const updateProjectDraft = (field, value) => {
    setProjectDraft(current => ({ ...current, [field]: value }));
  };

  const createProjectRecord = async () => {
    const name = projectDraft.name.trim();
    const gitProjectId = projectDraft.gitProjectId.trim();
    if (!name || !gitProjectId) {
      messageApi.error('项目名称和 GitLab 项目 ID 不能为空');
      return;
    }
    setProjectCreating(true);
    try {
      const created = await fetchApi('/api/projects', {
        method: 'POST',
        body: JSON.stringify({
          name,
          gitProvider: 'GITLAB',
          gitProjectId,
          repositoryUrl: projectDraft.repositoryUrl.trim() || null,
          groupId: projectDraft.groupId || groups[0]?.id || null,
          targetType: projectDraft.targetType || 'BACKEND'
        })
      });
      setProjectDraft({ name: '', gitProjectId: '', repositoryUrl: '', groupId: created.groupId || null, targetType: 'BACKEND' });
      await reloadProjectGroupsAndProjects(created.id);
      messageApi.success('项目已预创建，后续 webhook 会复用该 GitLab 项目 ID');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProjectCreating(false);
    }
  };

  const buildTargetPathMappingDrafts = (source = targetPathMappings) => TARGET_TYPE_PATH_MAPPING_OPTIONS
    .map((option, index) => {
      const existing = source.find(item => item.targetType === option.value);
      return existing || {
        targetType: option.value,
        pathPatterns: defaultPathPatternsForTargetType(option.value),
        enabled: true,
        sortOrder: (index + 1) * 10,
        description: '系统默认端类型路径映射'
      };
    });
  const targetPathMappingDrafts = buildTargetPathMappingDrafts();

  const updateTargetPathMappingDraft = (targetType, field, value) => {
    setTargetPathMappings(current => {
      const drafts = buildTargetPathMappingDrafts(current);
      return drafts.map(item => item.targetType === targetType ? { ...item, [field]: value } : item);
    });
  };

  const resetTargetPathMappingDraft = (targetType) => {
    setTargetPathMappings(current => {
      const drafts = buildTargetPathMappingDrafts(current);
      return drafts.map(item => item.targetType === targetType ? {
        ...item,
        pathPatterns: defaultPathPatternsForTargetType(targetType),
        enabled: true
      } : item);
    });
    messageApi.info(`已恢复 ${targetTypeLabel(targetType)} 的默认匹配路径，请点击“保存路径映射”生效`);
  };

  const saveTargetPathMappings = async () => {
    setTargetPathMappingSaving(true);
    try {
      const updated = await fetchApi('/api/target-type-path-mappings', {
        method: 'PUT',
        body: JSON.stringify({
          items: targetPathMappingDrafts.map((item, index) => ({
            targetType: item.targetType,
            pathPatterns: item.pathPatterns || [],
            enabled: item.enabled !== false,
            sortOrder: item.sortOrder ?? (index + 1) * 10,
            description: item.description || null
          }))
        })
      });
      setTargetPathMappings(Array.isArray(updated) ? updated : []);
      messageApi.success('端类型路径映射已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setTargetPathMappingSaving(false);
    }
  };

  const saveAiSettings = async (nextSettings = settingsDraft, successText = '设置已保存') => {
    if (!nextSettings) return;
    setSettingsSaving(true);
    try {
      const settings = await fetchApi('/api/code-quality-reviews/settings', {
        method: 'PUT',
        body: JSON.stringify({
          reviewEnabled: nextSettings.reviewEnabled,
          dingtalkNotificationEnabled: nextSettings.dingtalkNotificationEnabled,
          autoFixPreviewEnabled: nextSettings.autoFixPreviewEnabled,
          autoFixPreviewSeverities: normalizeAutoFixPreviewSeverities(nextSettings.autoFixPreviewSeverities)
        })
      });
      setAiSettings(settings);
      setSettingsDraft({
        reviewEnabled: settings?.reviewEnabled ?? false,
        dingtalkNotificationEnabled: settings?.dingtalkNotificationEnabled ?? true,
        autoFixPreviewEnabled: settings?.autoFixPreviewEnabled ?? false,
        autoFixPreviewSeverities: normalizeAutoFixPreviewSeverities(settings?.autoFixPreviewSeverities)
      });
      messageApi.success(successText);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  const commitSettingsChange = (field, value, successText) => {
    if (!settingsDraft || settingsSaving) return;
    const nextSettings = { ...settingsDraft, [field]: value };
    setSettingsDraft(nextSettings);
    saveAiSettings(nextSettings, successText);
  };

  const selectProvider = (providerCode) => {
    setSelectedProviderCode(providerCode);
    setProviderDraft(providers.find(provider => provider.providerCode === providerCode) || null);
    setProviderApiKeyDraft('');
    setProviderTestResult(null);
  };

  const updateProviderDraft = (field, value) => {
    setProviderDraft(current => current ? { ...current, [field]: value } : current);
    setProviderTestResult(null);
  };

  const saveProviderSettings = async () => {
    if (!providerDraft) return;
    setProviderSaving(true);
    try {
      const providerCode = providerDraft.providerCode;
      const body = {
        providerName: providerDraft.providerName,
        endpointUrl: providerDraft.endpointUrl,
        modelName: providerDraft.modelName,
        timeoutSeconds: providerDraft.timeoutSeconds || null,
        enabled: providerDraft.enabled
      };
      if (providerApiKeyDraft.trim()) body.apiKey = providerApiKeyDraft.trim();
      await fetchApi(`/api/code-quality-review-providers/${providerCode}`, {
        method: 'PUT',
        body: JSON.stringify(body)
      });
      const settings = await fetchApi(`/api/code-quality-review-providers/${providerCode}/set-default`, { method: 'POST' });
      setAiSettings(current => current ? { ...current, ...settings } : settings);
      const providerData = await fetchApi('/api/code-quality-review-providers');
      const providerItems = Array.isArray(providerData) ? providerData : (providerData.items || []);
      setProviders(providerItems);
      setSelectedProviderCode(providerCode);
      setProviderDraft(providerItems.find(item => item.providerCode === providerCode) || null);
      setProviderApiKeyDraft('');
      setProviderTestResult(null);
      messageApi.success(`${sourceLabel(providerCode)} Provider 已保存`);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProviderSaving(false);
    }
  };

  const clearProviderApiKey = async () => {
    if (!providerDraft) return;
    setProviderSaving(true);
    try {
      const providerData = await fetchApi(`/api/code-quality-review-providers/${providerDraft.providerCode}`, {
        method: 'PUT',
        body: JSON.stringify({ clearApiKey: true })
      });
      const providerItems = Array.isArray(providerData) ? providerData : (providerData.items || []);
      setProviders(providerItems);
      setProviderDraft(providerItems.find(item => item.providerCode === providerDraft.providerCode) || null);
      setProviderApiKeyDraft('');
      setProviderTestResult(null);
      messageApi.success(`${sourceLabel(providerDraft.providerCode)} Key 已清除`);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProviderSaving(false);
    }
  };

  const testProviderConnection = async () => {
    if (!providerDraft || providerTesting) return;
    setProviderTesting(true);
    setProviderTestResult(null);
    try {
      const body = {
        endpointUrl: providerDraft.endpointUrl,
        modelName: providerDraft.modelName
      };
      if (providerApiKeyDraft.trim()) body.apiKey = providerApiKeyDraft.trim();
      const result = await fetchApi(`/api/code-quality-review-providers/${providerDraft.providerCode}/test`, {
        method: 'POST',
        body: JSON.stringify(body)
      });
      setProviderTestResult(result);
      if (result?.success) {
        messageApi.success(`${sourceLabel(providerDraft.providerCode)} 联通性测试成功`);
      } else {
        messageApi.error(result?.errorMessage || `${sourceLabel(providerDraft.providerCode)} 联通性测试失败`);
      }
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProviderTesting(false);
    }
  };

  const selectProfile = (profileCode) => {
    setSelectedProfileCode(profileCode);
    setProfileDraft(profiles.find(profile => profile.profileCode === profileCode) || null);
    setPromptPreview(null);
  };

  const updateProfileDraft = (field, value) => {
    setProfileDraft(current => current ? { ...current, [field]: value } : current);
  };

  const selectPushPolicyGroup = (groupId) => {
    setSelectedPushPolicyGroupId(groupId);
    setPushPolicyDraft(pushPolicyFromGroup(groups.find(group => group.id === groupId)));
  };

  const updatePushPolicyDraft = (field, value) => {
    setPushPolicyDraft(current => current ? { ...current, [field]: value } : current);
  };

  const saveProfilePrompt = async () => {
    if (!profileDraft) return;
    setProfileSaving(true);
    try {
      const updated = await fetchApi(`/api/code-quality-review-profiles/${profileDraft.profileCode}`, {
        method: 'PUT',
        body: JSON.stringify({
          providerCode: profileDraft.providerCode || null,
          reviewInstructions: profileDraft.reviewInstructions,
          model: profileDraft.model
        })
      });
      setProfiles(current => current.map(item => item.profileCode === updated.profileCode ? updated : item));
      setProfileDraft(updated);
      setPromptPreview(null);
      messageApi.success('AI Review 配置已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const savePushReviewPolicy = async () => {
    if (!selectedPushPolicyGroupId || !pushPolicyDraft) return;
    setPushPolicySaving(true);
    try {
      const updated = await fetchApi(`/api/project-groups/${selectedPushPolicyGroupId}`, {
        method: 'PUT',
        body: JSON.stringify({
          aiReviewEnabled: pushPolicyDraft.aiReviewEnabled !== false,
          triggerOnManual: pushPolicyDraft.triggerOnManual !== false,
          triggerOnMr: pushPolicyDraft.triggerOnMr !== false,
          triggerOnPush: pushPolicyDraft.triggerOnPush === true,
          triggerOnlyWhenRiskMatched: false,
          autoFixPreviewEnabled: pushPolicyDraft.autoFixPreviewEnabled === true,
          autoFixPreviewSeverities: normalizeAutoFixPreviewSeverities(pushPolicyDraft.autoFixPreviewSeverities),
          pushBranchPatterns: pushPolicyDraft.pushBranchPatterns || [],
          pushMinChangedFiles: pushPolicyDraft.pushMinChangedFiles ?? null,
          pushMinDiffBytes: pushPolicyDraft.pushMinDiffBytes ?? null,
          pushMinCommitCount: pushPolicyDraft.pushMinCommitCount ?? null,
          pushMaxChangedFiles: pushPolicyDraft.pushMaxChangedFiles ?? null,
          pushMaxDiffBytes: pushPolicyDraft.pushMaxDiffBytes ?? null,
          pushDebounceSeconds: pushPolicyDraft.pushDebounceSeconds ?? null
        })
      });
      setGroups(current => current.map(item => item.id === updated.id ? updated : item));
      setPushPolicyDraft(pushPolicyFromGroup(updated));
      messageApi.success('项目组 AI Review 策略已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setPushPolicySaving(false);
    }
  };

  const previewRenderedPrompt = async () => {
    if (!profileDraft) return;
    setPromptPreviewLoading(true);
    try {
      const preview = await fetchApi(`/api/code-quality-review-profiles/${profileDraft.profileCode}/rendered-prompt`);
      setPromptPreview(preview);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setPromptPreviewLoading(false);
    }
  };

  const resetProfilePrompt = async () => {
    if (!profileDraft) return;
    const profileCode = selectedProfileCode || profileDraft.profileCode;
    setProfileSaving(true);
    try {
      const updated = await fetchApi(`/api/code-quality-review-profiles/${profileCode}/reset-default-prompt`, {
        method: 'POST'
      });
      setProfiles(current => current.map(item => item.profileCode === updated.profileCode ? updated : item));
      setSelectedProfileCode(updated.profileCode);
      setProfileDraft(updated);
      setPromptPreview(null);
      messageApi.success(`${updated.profileName || updated.profileCode} 已恢复默认 Prompt`);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const profileOptions = selectableReviewProfiles(profiles).map(profile => ({
    label: profileLabel(profile),
    value: profile.profileCode
  }));
  const providerOptions = providers.map(provider => ({
    label: provider.providerName || sourceLabel(provider.providerCode),
    value: provider.providerCode
  }));
  const groupModelOptions = providers.map(provider => ({
    label: provider.apiKeyConfigured
      ? sourceLabel(provider.providerCode)
      : `${sourceLabel(provider.providerCode)}（未配置 Key）`,
    value: provider.providerCode,
    disabled: !provider.apiKeyConfigured
  }));
  const groupProfileOptions = [{ label: '不指定', value: '' }, ...profileOptions];
  const profileProviderOptions = [{ label: '使用项目组模型配置', value: '' }, ...providerOptions];
  const providerApiKeyPlaceholder = '留空表示不更新当前 API Key';
  const filteredProjects = projectGroupFilter
    ? projects.filter(project => project.groupId === projectGroupFilter)
    : [];
  const renderWebhookDraftList = (webhooks, target) => (
    <Space direction="vertical" size="middle" className="full-width webhook-list">
      {(webhooks || []).length > 0 ? (
        (webhooks || []).map((item, index) => (
          <div key={item.id || `${target}-draft-${index}`} className="webhook-item">
            <Row gutter={[12, 12]} align="middle">
              <Col xs={24} lg={6}>
                <Text strong>名称</Text>
                <Input
                  className="prompt-field"
                  value={item.name || ''}
                  placeholder="例如 移动业务群"
                  onChange={event => updateGroupWebhookDraft(target, index, 'name', event.target.value)}
                />
              </Col>
              <Col xs={24} lg={13}>
                <Text strong>Webhook URL</Text>
                <Input
                  className="prompt-field"
                  value={item.webhookUrl || ''}
                  placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
                  onChange={event => updateGroupWebhookDraft(target, index, 'webhookUrl', event.target.value)}
                />
              </Col>
              <Col xs={12} lg={3}>
                <Text strong>启用</Text>
                <div className="prompt-field">
                  <Switch
                    checked={item.enabled !== false}
                    checkedChildren="开启"
                    unCheckedChildren="关闭"
                    onChange={checked => updateGroupWebhookDraft(target, index, 'enabled', checked)}
                  />
                </div>
              </Col>
              <Col xs={12} lg={2}>
                <Text strong>操作</Text>
                <div className="prompt-field webhook-remove-cell">
                  <Button
                    danger
                    type="text"
                    size="small"
                    className="webhook-remove-button"
                    icon={<CloseOutlined />}
                    onClick={() => removeGroupWebhookDraft(target, index)}
                  />
                </div>
              </Col>
            </Row>
          </div>
        ))
      ) : (
        <Empty description="暂未配置钉钉机器人" />
      )}
    </Space>
  );
  const groupColumns = [
    {
      title: '项目组',
      dataIndex: 'groupName',
      width: 190,
      render: (_, group) => editingGroupId === group.id ? (
        <Input value={editingGroupDraft?.groupName || ''} onChange={event => updateEditingGroupDraft('groupName', event.target.value)} />
      ) : (
        <Space wrap>
          <Text strong>{group.groupName}</Text>
          {group.groupCode === 'default' && <Tag>默认</Tag>}
        </Space>
      )
    },
    {
      title: '编码',
      dataIndex: 'groupCode',
      width: 160,
      render: (_, group) => editingGroupId === group.id ? (
        <Input disabled={group.groupCode === 'default'} value={editingGroupDraft?.groupCode || ''} onChange={event => updateEditingGroupDraft('groupCode', event.target.value)} />
      ) : group.groupCode
    },
    {
      title: 'AI Review 模板',
      dataIndex: 'defaultCodeQualityProfileCode',
      width: 220,
      render: (_, group) => editingGroupId === group.id ? (
        <Select className="full-width" value={editingGroupDraft?.defaultCodeQualityProfileCode || ''} options={groupProfileOptions} onChange={value => updateEditingGroupDraft('defaultCodeQualityProfileCode', value || null)} />
      ) : (() => {
        const profile = profiles.find(item => item.profileCode === group.defaultCodeQualityProfileCode);
        return profile ? profileLabel(profile) : (group.defaultCodeQualityProfileCode || '-');
      })()
    },
    {
      title: 'Review 模型',
      dataIndex: 'defaultProviderCode',
      width: 260,
      render: (_, group) => editingGroupId === group.id ? (
        <Select
          mode="multiple"
          allowClear
          className="full-width"
          placeholder="选择一个或多个模型"
          value={selectedAiReviewProviderCodes(editingGroupDraft)}
          options={groupModelOptions}
          onChange={value => updateGroupAiReviewProviders('editing', value)}
        />
      ) : aiReviewProviderDisplay(group)
    },
    {
      title: '钉钉机器人',
      dataIndex: 'enabledDingtalkWebhookCount',
      width: 140,
      render: value => <Tag color={value > 0 ? 'blue' : 'default'}>{value || 0} 个启用</Tag>
    },
    {
      title: '描述',
      dataIndex: 'description',
      render: (_, group) => editingGroupId === group.id ? (
        <Input value={editingGroupDraft?.description || ''} onChange={event => updateEditingGroupDraft('description', event.target.value)} />
      ) : (group.description || '-')
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: value => <Tag color={value === 'ENABLED' ? 'green' : 'default'}>{value === 'ENABLED' ? '启用' : '停用'}</Tag>
    },
    {
      title: '操作',
      width: 190,
      render: (_, group) => editingGroupId === group.id ? (
        <Space wrap>
          <Button type="primary" size="small" loading={projectGroupSavingId === group.id} onClick={saveEditingProjectGroup}>保存</Button>
          <Button size="small" onClick={() => { setEditingGroupId(null); setEditingGroupDraft(null); }}>取消</Button>
        </Space>
      ) : (
        <Space wrap>
          <Button size="small" onClick={() => startEditGroup(group)}>编辑</Button>
          <Button
            danger
            size="small"
            disabled={group.groupCode === 'default'}
            loading={projectGroupDisablingId === group.id}
            onClick={() => disableProjectGroup(group)}
          >
            停用
          </Button>
        </Space>
      )
    }
  ];

  const collapseItems = [
    {
      key: 'global-settings',
      label: (
        <Space wrap>
          <Text strong>全局设置</Text>
          <Tag color={(settingsDraft?.reviewEnabled ?? false) ? 'green' : 'default'}>AI Review {(settingsDraft?.reviewEnabled ?? false) ? '开启' : '关闭'}</Tag>
          <Tag color={(settingsDraft?.dingtalkNotificationEnabled ?? true) ? 'blue' : 'default'}>钉钉 {(settingsDraft?.dingtalkNotificationEnabled ?? true) ? '开启' : '关闭'}</Tag>
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
        >
          <Space direction="vertical" size="middle" className="global-settings-stack">
            <div className="global-setting-field">
              <div className="settings-inline-head">
                <Text strong>代码质量 AI Review 全局能力</Text>
                <Switch
                  checked={settingsDraft?.reviewEnabled ?? false}
                  loading={settingsSaving}
                  checkedChildren="开启"
                  unCheckedChildren="关闭"
                  onChange={checked => commitSettingsChange('reviewEnabled', checked, 'AI Review 全局能力已保存')}
                />
              </div>
              <Text type="secondary" className="settings-description">
                关闭后，手动触发、MR 和 Push 自动流程都不会调用模型；规则提醒与落库仍正常执行。
              </Text>
            </div>
            <div className="global-setting-field">
              <div className="settings-inline-head">
                <Text strong>钉钉推送</Text>
                <Switch
                  checked={settingsDraft?.dingtalkNotificationEnabled ?? true}
                  loading={settingsSaving}
                  checkedChildren="开启"
                  unCheckedChildren="关闭"
                  onChange={checked => commitSettingsChange('dingtalkNotificationEnabled', checked, '钉钉推送设置已保存')}
                />
              </div>
              <Text type="secondary" className="settings-description">
                关闭后，规则审查和 AI Review 仍会正常执行与落库，但不会向钉钉发送消息。
              </Text>
            </div>
          </Space>
        </Card>
      )
    },
    {
      key: 'project-target-configs',
      label: (
        <Space wrap>
          <Text strong>项目组 / 端类型配置</Text>
          {targetConfigDraft?.targetType && <Tag>{targetTypeLabel(targetConfigDraft.targetType)}</Tag>}
        </Space>
      ),
      children: (
        <Card bordered={false} className="settings-inner-card">
          <Space direction="vertical" size="middle" className="full-width">
            <div className="settings-subsection">
              <Space direction="vertical" size="middle" className="full-width">
                <div className="settings-inline-head">
                  <Space wrap>
                    <Text strong>项目组管理</Text>
                    <Tag>{groups.length} 个项目组</Tag>
                  </Space>
                  <Button icon={<ReloadOutlined />} onClick={refreshProjectConfigData} loading={projectConfigReloading}>刷新</Button>
                </div>
                <Row gutter={[12, 12]} align="bottom">
                  <Col xs={24} md={4}>
                    <Text strong>名称</Text>
                    <Input
                      className="prompt-field"
                      value={groupDraft.groupName}
                      placeholder="例如 移动业务组"
                      onChange={event => updateGroupDraft('groupName', event.target.value)}
                    />
                  </Col>
                  <Col xs={24} md={4}>
                    <Text strong>编码</Text>
                    <Input
                      className="prompt-field"
                      value={groupDraft.groupCode}
                      placeholder="例如 mobile"
                      onChange={event => updateGroupDraft('groupCode', event.target.value)}
                    />
                  </Col>
                  <Col xs={24} md={5}>
                    <Text strong>AI Review 模板</Text>
                    <Select
                      className="full-width prompt-field"
                      value={groupDraft.defaultCodeQualityProfileCode || ''}
                      options={groupProfileOptions}
                      onChange={value => updateGroupDraft('defaultCodeQualityProfileCode', value || null)}
                    />
                  </Col>
                  <Col xs={24} md={5}>
                    <Text strong>Review 模型</Text>
                    <Select
                      mode="multiple"
                      allowClear
                      className="full-width prompt-field"
                      placeholder="选择一个或多个模型"
                      value={selectedAiReviewProviderCodes(groupDraft)}
                      options={groupModelOptions}
                      onChange={value => updateGroupAiReviewProviders('create', value)}
                    />
                  </Col>
                  <Col xs={24} md={4}>
                    <Text strong>描述</Text>
                    <Input
                      className="prompt-field"
                      value={groupDraft.description}
                      placeholder="可选"
                      onChange={event => updateGroupDraft('description', event.target.value)}
                    />
                  </Col>
                  <Col xs={24} md={2}>
                    <Button block type="primary" icon={<PlusOutlined />} loading={projectGroupCreating} onClick={createProjectGroup}>
                      新增
                    </Button>
                  </Col>
                </Row>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  columns={groupColumns}
                  dataSource={groups}
                  scroll={{ x: 1180 }}
                />
                {editingGroupDraft && (
                  <div className="settings-subsection">
                    <div className="settings-inline-head">
                      <Space wrap>
                        <Text strong>{editingGroupDraft.groupName || '项目组'} 钉钉机器人</Text>
                        <Tag>{(editingGroupDraft.dingtalkWebhooks || []).filter(item => item.enabled !== false).length} 个启用</Tag>
                      </Space>
                      <Button icon={<PlusOutlined />} onClick={() => addGroupWebhookDraft('editing')}>新增机器人</Button>
                    </div>
                    <Text type="secondary" className="settings-description">
                      该项目组下项目的规则提醒和 AI Review 结果只会推送到这些机器人；未配置时通知会记录为跳过。
                    </Text>
                    {renderWebhookDraftList(editingGroupDraft.dingtalkWebhooks || [], 'editing')}
                  </div>
                )}
              </Space>
            </div>
            <div className="settings-subsection">
              <Space direction="vertical" size="middle" className="full-width">
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={8}>
                    <Text strong>项目组筛选</Text>
                    <Select
                      className="full-width prompt-field"
                      allowClear
                      value={projectGroupFilter}
                      options={groups.map(group => ({ label: group.groupName, value: group.id }))}
                      placeholder="全部项目组"
                      onChange={selectProjectGroupFilter}
                    />
                  </Col>
                  <Col xs={24} md={8}>
                    <Text strong>项目</Text>
                    <Select
                      showSearch
                      className="full-width prompt-field"
                      value={selectedProjectId || undefined}
                      options={filteredProjects.map(project => ({
                        label: `${project.name}${project.status !== 'ENABLED' ? ` (${project.status})` : ''}`,
                        value: project.id
                      }))}
                      placeholder={projectGroupFilter ? '请选择项目' : '请先选择项目组'}
                      disabled={!projectGroupFilter}
                      onChange={selectProjectForTargetConfig}
                    />
                  </Col>
                </Row>
                {selectedProjectId && (
                  <Row gutter={[16, 16]} align="bottom">
                  <Col xs={24} md={6}>
                      <Text strong>当前项目所属项目组</Text>
                      <Select
                        className="full-width prompt-field"
                        value={projectConfigDraft?.groupId || undefined}
                        options={groups.map(group => ({ label: group.groupName, value: group.id }))}
                        onChange={value => updateProjectConfigDraft('groupId', value)}
                      />
                    </Col>
                  <Col xs={24} md={6}>
                      <Text strong>当前项目所属端类型</Text>
                      <Select
                        className="full-width prompt-field"
                        value={projectConfigDraft?.targetType || undefined}
                        options={PROJECT_TARGET_TYPE_OPTIONS}
                        loading={projectConfigSaving}
                        onChange={value => updateProjectConfigDraft('targetType', value)}
                      />
                    </Col>
                  <Col xs={24} md={6}>
                    <Text strong>当前项目所用模型</Text>
                    <Select
                      className="full-width prompt-field"
                      value={targetConfigDraft?.providerCode || ''}
                      options={profileProviderOptions}
                      onChange={value => updateTargetConfigDraft('providerCode', value || null)}
                    />
                  </Col>
                  <Col xs={24} md={6}>
                      <div className="settings-action-row project-config-save-row">
                        <Button type="primary" loading={projectConfigSaving} onClick={saveSelectedProjectConfig}>
                          保存项目配置
                        </Button>
                      </div>
                    </Col>
                  </Row>
                )}
              </Space>
            </div>
            <div className="settings-subsection">
              <Space direction="vertical" size="middle" className="full-width">
                <div className="settings-inline-head">
                  <Space wrap>
                    <Text strong>端类型路径映射</Text>
                    <Tag>{targetPathMappingDrafts.filter(item => item.enabled !== false).length} 个启用</Tag>
                  </Space>
                  <Button type="primary" loading={targetPathMappingSaving} onClick={saveTargetPathMappings}>
                    保存路径映射
                  </Button>
                </div>
                <Alert
                  type="info"
                  showIcon
                  message="Webhook 新项目只按这里的全局路径映射识别端类型。路径规则从仓库根目录匹配；如需任意层级匹配，请显式配置 **/ 前缀。"
                />
                <Table
                  size="small"
                  rowKey="targetType"
                  pagination={false}
                  dataSource={targetPathMappingDrafts}
                  columns={[
                    { title: '端类型', dataIndex: 'targetType', width: 160, render: value => <Tag>{targetTypeLabel(value)}</Tag> },
                    {
                      title: '路径匹配',
                      dataIndex: 'pathPatterns',
                      render: (_, row) => (
                        <Select
                          mode="tags"
                          className="full-width"
                          value={row.pathPatterns || []}
                          onChange={value => updateTargetPathMappingDraft(row.targetType, 'pathPatterns', value)}
                        />
                      )
                    },
                    {
                      title: '启用',
                      dataIndex: 'enabled',
                      width: 180,
                      render: (_, row) => (
                        <Space wrap>
                          <Switch
                            checked={row.enabled !== false}
                            checkedChildren="启用"
                            unCheckedChildren="停用"
                            onChange={checked => updateTargetPathMappingDraft(row.targetType, 'enabled', checked)}
                          />
                          <Button
                            size="small"
                            icon={<ReloadOutlined />}
                            onClick={() => resetTargetPathMappingDraft(row.targetType)}
                          >
                            重置
                          </Button>
                        </Space>
                      )
                    }
                  ]}
                  scroll={{ x: 920 }}
                />
              </Space>
            </div>
          </Space>
        </Card>
      )
    },
    {
      key: 'provider-settings',
      label: (
        <Space wrap>
          <Text strong>模型 Provider 配置</Text>
          <Tag color="blue">{sourceLabel(aiSettings?.defaultProviderCode || selectedProviderCode)}</Tag>
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
        >
          <Row gutter={[16, 16]} align="bottom">
            <Col xs={24} md={8}>
              <Text strong>Provider</Text>
              <Select
                className="full-width prompt-field"
                value={selectedProviderCode}
                options={providerOptions}
                loading={settingsSaving}
                onChange={selectProvider}
              />
              {providerDraft && !providerDraft.apiKeyConfigured && (
                <Alert
                  className="prompt-field"
                  type="warning"
                  showIcon
                  message={`请先配置 ${sourceLabel(providerDraft.providerCode)} API Key`}
                />
              )}
            </Col>
            <Col xs={24} md={8}>
              <Text strong>端点 URL</Text>
              <Input
                className="prompt-field"
                placeholder="例如 https://api.deepseek.com"
                value={providerDraft?.endpointUrl || ''}
                onChange={event => updateProviderDraft('endpointUrl', event.target.value)}
              />
            </Col>
            <Col xs={24} md={8}>
              <Text strong>模型名称</Text>
              <Input
                className="prompt-field"
                placeholder="例如 deepseek-v4-pro"
                value={providerDraft?.modelName || ''}
                onChange={event => updateProviderDraft('modelName', event.target.value)}
              />
            </Col>
            <Col xs={24} md={8}>
              <Text strong>Review 超时秒数</Text>
              <InputNumber
                className="full-width prompt-field"
                min={1}
                max={3600}
                placeholder="默认 1000，留空使用系统默认"
                value={providerDraft?.timeoutSeconds ?? null}
                onChange={value => updateProviderDraft('timeoutSeconds', value || null)}
              />
            </Col>
            <Col xs={24} md={10}>
              <Space direction="vertical" className="full-width">
                <Space wrap>
                  <Text strong>{sourceLabel(providerDraft?.providerCode)} Key</Text>
                  {providerDraft?.apiKeyConfigured ? (
                    <Tag color="green">已配置 {providerDraft.apiKeyMasked}</Tag>
                  ) : (
                    <Tag>未配置</Tag>
                  )}
                  {providerDraft?.defaultProvider && <Tag color="blue">当前使用</Tag>}
                </Space>
                <Input.Password
                  placeholder={providerApiKeyPlaceholder}
                  value={providerApiKeyDraft}
                  onChange={event => setProviderApiKeyDraft(event.target.value)}
                />
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size={4}>
                <Switch
                  checked={providerDraft?.enabled ?? false}
                  checkedChildren="启用"
                  unCheckedChildren="停用"
                  onChange={checked => updateProviderDraft('enabled', checked)}
                />
              </Space>
            </Col>
            <Col xs={24} md={8}>
              <Button danger disabled={!providerDraft?.apiKeyConfigured} loading={providerSaving} onClick={clearProviderApiKey}>
                清除当前 Key
              </Button>
            </Col>
          </Row>
          <div className="settings-action-row">
            <Space wrap>
              <Button
                icon={<ReloadOutlined />}
                loading={providerTesting}
                onClick={testProviderConnection}
                disabled={!providerDraft || providerSaving}
              >
                测试联通性
              </Button>
              <Button type="primary" loading={providerSaving} onClick={saveProviderSettings} disabled={!providerDraft || providerTesting}>保存 Provider</Button>
            </Space>
          </div>
          {providerTestResult && (
            <Alert
              className="prompt-field"
              showIcon
              type={providerTestResult.success ? 'success' : 'error'}
              message={providerTestResult.success ? `${sourceLabel(providerTestResult.providerCode)} 联通性正常` : `${sourceLabel(providerTestResult.providerCode)} 联通性失败`}
              description={
                providerTestResult.success
                  ? `endpoint=${providerTestResult.endpointUrl || '-'}，model=${providerTestResult.modelName || '-'}，耗时 ${providerTestResult.latencyMs ?? '-'} ms`
                  : (providerTestResult.errorMessage || providerTestResult.responsePreview || '请检查 API Key、端点 URL、模型名称和网络连通性。')
              }
            />
          )}
        </Card>
      )
    },
    {
      key: 'profile-settings',
      label: (
        <Space wrap>
          <Text strong>AI Review 配置</Text>
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
        >
          {profileDraft ? (
            <div className="full-width" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="settings-subsection" style={{ order: 2 }}>
                <Space direction="vertical" size="middle" className="full-width">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} lg={10}>
                      <Text strong>Profile</Text>
                      <Select
                        className="full-width prompt-field"
                        value={selectedProfileCode}
                        options={profileOptions}
                        onChange={selectProfile}
                      />
                    </Col>
                    <Col xs={24} lg={7}>
                      <Text strong>Provider 覆盖</Text>
                      <Select
                        className="full-width prompt-field"
                        value={profileDraft.providerCode || ''}
                        options={profileProviderOptions}
                        onChange={value => updateProfileDraft('providerCode', value || null)}
                      />
                    </Col>
                    <Col xs={24} lg={7}>
                      <Text strong>模型覆盖</Text>
                      <Input
                        className="prompt-field"
                        placeholder="留空使用后端默认模型"
                        value={profileDraft.model || ''}
                        onChange={event => updateProfileDraft('model', event.target.value)}
                      />
                    </Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24}>
                      <Text strong>Review Instructions</Text>
                      <Input.TextArea
                        className="prompt-textarea"
                        value={profileDraft.reviewInstructions || ''}
                        onChange={event => updateProfileDraft('reviewInstructions', event.target.value)}
                        autoSize={{ minRows: 8, maxRows: 16 }}
                      />
                    </Col>
                  </Row>
                  {promptPreview && (
                    <Collapse
                      defaultActiveKey={['preview']}
                      items={[{
                        key: 'preview',
                        label: (
                          <Space wrap>
                            <Text strong>Prompt 预览</Text>
                            <Tag>{promptPreview.provider}</Tag>
                            {promptPreview.model && <Tag>{promptPreview.model}</Tag>}
                            <Tag>{promptPreview.promptLength} 字符</Tag>
                            <Tag>{promptPreview.promptHash?.slice(0, 12)}</Tag>
                          </Space>
                        ),
                        children: <pre className="prompt-preview-block">{promptPreview.prompt}</pre>
                      }]}
                    />
                  )}
                  <div className="settings-action-row">
                    <Space wrap>
                      <Button loading={promptPreviewLoading} onClick={previewRenderedPrompt} disabled={!profileDraft}>预览 Prompt</Button>
                      <Button loading={profileSaving} onClick={resetProfilePrompt} disabled={!profileDraft}>恢复当前 Profile 默认 Prompt</Button>
                      <Button type="primary" loading={profileSaving} onClick={saveProfilePrompt} disabled={!profileDraft}>保存 Profile</Button>
                    </Space>
                  </div>
                </Space>
              </div>
              <div className="settings-subsection" style={{ order: 1 }}>
                <Space direction="vertical" size="middle" className="full-width">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={10}>
                      <Text strong>项目组</Text>
                      <Select
                        className="full-width prompt-field"
                        value={selectedPushPolicyGroupId || undefined}
                        options={groups.map(group => ({ label: group.groupName, value: group.id }))}
                        onChange={selectPushPolicyGroup}
                        placeholder="请选择项目组"
                      />
                    </Col>
                  </Row>
                  <Row gutter={[16, 16]} align="middle">
                    <Col xs={24} md={8}>
                      <Space direction="vertical">
                        <Text strong>启用项目组 AI Review</Text>
                        <Switch
                          checked={pushPolicyDraft?.aiReviewEnabled !== false}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                          onChange={checked => updatePushPolicyDraft('aiReviewEnabled', checked)}
                        />
                      </Space>
                    </Col>
                    <Col xs={24} md={8}>
                      <Space direction="vertical">
                        <Text strong>手动触发</Text>
                        <Switch
                          checked={pushPolicyDraft?.triggerOnManual !== false}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                          onChange={checked => updatePushPolicyDraft('triggerOnManual', checked)}
                        />
                      </Space>
                    </Col>
                    <Col xs={24} md={8}>
                      <Space direction="vertical">
                        <Text strong>MR 自动触发</Text>
                        <Switch
                          checked={pushPolicyDraft?.triggerOnMr !== false}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                          onChange={checked => updatePushPolicyDraft('triggerOnMr', checked)}
                        />
                      </Space>
                    </Col>
                    <Col xs={24} md={8}>
                      <Space direction="vertical">
                        <Text strong>Push 自动触发</Text>
                        <Switch
                          checked={pushPolicyDraft?.triggerOnPush === true}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                          onChange={checked => updatePushPolicyDraft('triggerOnPush', checked)}
                        />
                      </Space>
                    </Col>
                    <Col xs={24} md={8}>
                      <Space direction="vertical">
                        <Text strong>自动生成修复预览</Text>
                        <Switch
                          checked={pushPolicyDraft?.autoFixPreviewEnabled === true}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                          onChange={checked => updatePushPolicyDraft('autoFixPreviewEnabled', checked)}
                        />
                      </Space>
                    </Col>
                    <Col xs={24} md={16}>
                      <div style={{ opacity: (pushPolicyDraft?.autoFixPreviewEnabled === true) ? 1 : 0.55 }}>
                        <Space direction="vertical" size={4} className="full-width">
                          <Text strong>自动生成修复预览</Text>
                          <Text type="secondary">
                            在 Review 之后，根据风险点建议，自动对如下等级风险点生成可查看的代码预览，免去手动生成的长时间等待。按需配置风险等级，避免过度消耗 token。
                          </Text>
                        </Space>
                        <Select
                          mode="multiple"
                          className="full-width prompt-field"
                          value={normalizeAutoFixPreviewSeverities(pushPolicyDraft?.autoFixPreviewSeverities)}
                          options={AUTO_FIX_PREVIEW_SEVERITY_OPTIONS}
                          onChange={value => updatePushPolicyDraft('autoFixPreviewSeverities', normalizeAutoFixPreviewSeverities(value))}
                        />
                      </div>
                    </Col>
                  </Row>
                  <Space direction="vertical" size={4}>
                    <Text strong>Push 审核策略</Text>
                    <Text type="secondary">允许分支匹配后，最小文件数、最小 Diff、最小 Commit、最大文件数、最大 Diff、Debounce 全部满足才会自动进入 AI Review；-1 表示不限制。</Text>
                  </Space>
                  <Row gutter={[16, 16]}>
                    <Col xs={24}>
                      <Text strong>允许分支</Text>
                      <Select
                        mode="tags"
                        className="full-width prompt-field"
                        value={pushPolicyDraft?.pushBranchPatterns || []}
                        onChange={value => updatePushPolicyDraft('pushBranchPatterns', value)}
                        placeholder="例如 master、release/*"
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最小文件数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMinChangedFiles}
                        onChange={value => updatePushPolicyDraft('pushMinChangedFiles', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最小 Diff 字节</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMinDiffBytes}
                        onChange={value => updatePushPolicyDraft('pushMinDiffBytes', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最小 Commit 数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMinCommitCount}
                        onChange={value => updatePushPolicyDraft('pushMinCommitCount', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最大文件数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMaxChangedFiles}
                        onChange={value => updatePushPolicyDraft('pushMaxChangedFiles', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最大 Diff 字节</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMaxDiffBytes}
                        onChange={value => updatePushPolicyDraft('pushMaxDiffBytes', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>Debounce 秒数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushDebounceSeconds}
                        onChange={value => updatePushPolicyDraft('pushDebounceSeconds', value)}
                      />
                    </Col>
                  </Row>
                  <div className="settings-action-row">
                    <Button
                      type="primary"
                      loading={pushPolicySaving}
                      onClick={savePushReviewPolicy}
                      disabled={!pushPolicyDraft || !selectedPushPolicyGroupId}
                    >
                      保存项目组 AI Review 策略
                    </Button>
                  </div>
                </Space>
              </div>
            </div>
          ) : (
            <Empty description="暂无 AI Review 设置" />
          )}
        </Card>
      )
    }
  ];

  const orderedCollapseItems = ['project-target-configs', 'profile-settings', 'provider-settings', 'global-settings']
    .map(key => collapseItems.find(item => item.key === key))
    .filter(Boolean);

  return (
    <div className="page-shell">
      {contextHolder}
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        <Collapse className="settings-collapse" items={orderedCollapseItems} />
      </Spin>
    </div>
  );
}
function TaskListPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const openTaskDetail = (taskId) => {
    navigate(`/tasks/${taskId}`, { state: { from: currentRoute(location) } });
  };

  return <TaskList onOpen={openTaskDetail} />;
}

function TaskDetailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { taskId } = useParams();
  const numericTaskId = Number(taskId);
  const backTarget = resolveBackTarget(location, TASK_LIST_ROUTE);

  if (!Number.isFinite(numericTaskId)) {
    return (
      <div className="page-shell">
        <Alert type="error" showIcon message="任务 ID 无效" />
      </div>
    );
  }

  return (
    <TaskDetail
      taskId={numericTaskId}
      onBack={() => navigate(backTarget)}
      onOpen={(nextTaskId) => navigate(`/tasks/${nextTaskId}`, { state: { from: backTarget } })}
    />
  );
}

const RULE_GAP_TYPE_OPTIONS = [
  { label: 'Planner Signal 暂不支持', value: 'UNSUPPORTED_PLANNER_SIGNAL' },
  { label: 'Requested Context 不可用', value: 'UNAVAILABLE_REQUESTED_CONTEXT' },
  { label: 'Retriever 失败', value: 'RETRIEVAL_FAILED' },
  { label: '预算裁剪', value: 'BUDGET_CUT' }
];

const RULE_GAP_RECOMMENDATION_STATUS = {
  RECOMMENDED: { label: '建议补全', color: 'red' },
  WATCH: { label: '继续观察', color: 'gold' },
  NOT_NOW: { label: '暂不处理', color: 'default' }
};

const RULE_GAP_COMPLETION_TYPE = {
  PLANNER: 'Planner 规则',
  RETRIEVER: '证据检索',
  BUDGET: '预算策略',
  PROMPT: 'Prompt 约束',
  STABILITY: '稳定性',
  OBSERVABILITY: '观测解释'
};

const RULE_GAP_FEEDBACK_CORRELATION = {
  TASK_LEVEL: '任务级关联',
  PROJECT_RECENT_APPROXIMATION: '项目近期近似',
  NONE: '暂无关联反馈'
};

function ruleGapRecommendationStatusTag(status) {
  const meta = RULE_GAP_RECOMMENDATION_STATUS[status] || { label: status || '-', color: 'default' };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

function RuleGapDashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [projects, setProjects] = useState([]);
  const [filters, setFilters] = useState({
    projectId: null,
    gapType: null,
    signal: '',
    recentDays: 30,
    limit: 50
  });
  const [dashboard, setDashboard] = useState({
    items: [],
    summary: {},
    recommendations: { items: [], summary: {} }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadDashboard = async (nextFilters = filters) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (nextFilters.projectId) params.set('projectId', nextFilters.projectId);
      if (nextFilters.gapType) params.set('gapType', nextFilters.gapType);
      if (nextFilters.signal?.trim()) params.set('signal', nextFilters.signal.trim());
      if (nextFilters.recentDays) params.set('recentDays', nextFilters.recentDays);
      if (nextFilters.limit) params.set('limit', nextFilters.limit);
      const data = await fetchApi(`/api/code-quality-reviews/rule-gaps?${params.toString()}`);
      setDashboard({
        items: Array.isArray(data?.items) ? data.items : [],
        summary: data?.summary || {},
        recommendations: {
          items: Array.isArray(data?.recommendations?.items) ? data.recommendations.items : [],
          summary: data?.recommendations?.summary || {}
        }
      });
    } catch (err) {
      setError(err.message);
      setDashboard({ items: [], summary: {}, recommendations: { items: [], summary: {} } });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApi('/api/projects?includeDisabled=true&pageSize=500')
      .then(data => setProjects(data.items || []))
      .catch(() => setProjects([]));
    loadDashboard();
  }, []);

  const updateFilter = (field, value) => {
    setFilters(current => ({ ...current, [field]: value }));
  };

  const applyFilters = () => {
    loadDashboard(filters);
  };

  const resetFilters = () => {
    const nextFilters = { projectId: null, gapType: null, signal: '', recentDays: 30, limit: 50 };
    setFilters(nextFilters);
    loadDashboard(nextFilters);
  };

  const openTask = (task) => {
    if (!task?.taskId) return;
    const reviewQuery = task.reviewKey && task.reviewKey !== 'default'
      ? `?reviewKey=${encodeURIComponent(task.reviewKey)}`
      : '';
    navigate(`/tasks/${task.taskId}${reviewQuery}`, { state: { from: route } });
  };

  const projectOptions = projects.map(project => ({
    label: project.name,
    value: project.id
  }));
  const summary = dashboard.summary || {};
  const recommendationItems = safeArray(dashboard.recommendations?.items);
  const recommendationSummary = dashboard.recommendations?.summary || {};
  const recommendedCount = Number(recommendationSummary.recommendedCount || 0);
  const watchCount = Number(recommendationSummary.watchCount || 0);
  const notNowCount = Number(recommendationSummary.notNowCount || 0);
  const recommendationTotal = recommendedCount + watchCount + notNowCount;
  const recommendationChartTotal = Math.max(recommendationTotal, 1);
  const recommendedEnd = (recommendedCount / recommendationChartTotal) * 100;
  const watchEnd = ((recommendedCount + watchCount) / recommendationChartTotal) * 100;
  const recommendationChartStyle = {
    background: recommendationTotal
      ? `conic-gradient(#ef4444 0 ${recommendedEnd}%, #f59e0b ${recommendedEnd}% ${watchEnd}%, #94a3b8 ${watchEnd}% 100%)`
      : 'conic-gradient(#e5e7eb 0 100%)'
  };
  const eventBreakdown = [
    { label: '含缺口', value: Number(summary.eventsWithRuleGapCount || 0), color: '#2563eb' },
    { label: '无缺口', value: Number(summary.eventsWithoutRuleGapCount || 0), color: '#10b981' },
    { label: '跳过', value: Number(summary.skippedEventCount || 0), color: '#94a3b8' },
    { label: '解析失败', value: Number(summary.parseFailedEventCount || 0), color: '#ef4444' }
  ];
  const eventTotal = Math.max(
    Number(summary.scannedEventCount || 0),
    eventBreakdown.reduce((sum, item) => sum + item.value, 0),
    1
  );
  const columns = [
    {
      title: '缺口类型',
      dataIndex: 'gapType',
      width: 190,
      render: value => <Tag color="orange">{value || '-'}</Tag>
    },
    { title: 'Signal', dataIndex: 'signal', width: 220, ellipsis: true },
    { title: 'Requested Context', dataIndex: 'requestedContext', width: 210, ellipsis: true },
    { title: '建议能力', dataIndex: 'suggestedCapability', ellipsis: true },
    { title: '出现次数', dataIndex: 'occurrenceCount', width: 100, render: value => <Text strong>{countText(value)}</Text> },
    {
      title: '影响范围',
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>项目 {countText(row.projectCount)}</Text>
          <Text>任务 {countText(row.taskCount)}</Text>
        </Space>
      )
    },
    { title: '最近出现时间', dataIndex: 'recentOccurredAt', width: 190, render: value => value || '-' },
    {
      title: '最近任务样例',
      dataIndex: 'recentTasks',
      width: 260,
      render: value => {
        const tasks = safeArray(value);
        if (!tasks.length) return '-';
        return (
          <Space direction="vertical" size={2} className="full-width">
            {tasks.slice(0, 3).map(task => (
              <Button
                key={`${task.taskId}-${task.reviewKey}`}
                type="link"
                className="rule-gap-task-link"
                onClick={() => openTask(task)}
              >
                #{task.taskId} · {task.projectName || '-'} · {task.reviewKey || 'default'}
              </Button>
            ))}
          </Space>
        );
      }
    },
  ];
  const recommendationColumns = [
    {
      title: '是否补全',
      dataIndex: 'recommendationStatus',
      width: 100,
      render: value => ruleGapRecommendationStatusTag(value)
    },
    {
      title: '补全类型',
      dataIndex: 'completionType',
      width: 108,
      render: value => <Tag color="blue">{RULE_GAP_COMPLETION_TYPE[value] || value || '-'}</Tag>
    },
    {
      title: '建议下一阶段',
      dataIndex: 'suggestedNextStage',
      width: 210,
      render: value => <Text strong>{value || '-'}</Text>
    },
    {
      title: '为什么',
      dataIndex: 'reasons',
      width: 340,
      render: value => {
        const reasons = safeArray(value);
        if (!reasons.length) return '-';
        return (
          <Space direction="vertical" size={4} className="full-width">
            {reasons.slice(0, 4).map((reason, index) => (
              <Text key={`${reason}-${index}`}>{reason}</Text>
            ))}
          </Space>
        );
      }
    },
    {
      title: '评分 / 反馈',
      width: 150,
      render: (_, row) => {
        const feedback = row.feedbackSignals || {};
        return (
          <Space direction="vertical" size={2}>
            <Text strong>{countText(row.score)} / 100</Text>
            <Text type="secondary">
              {RULE_GAP_FEEDBACK_CORRELATION[feedback.correlation] || feedback.correlation || '暂无关联反馈'}
            </Text>
            <Text type="secondary">
              上下文不足 {countText(feedback.contextMissingCount)} · 误判 {countText(feedback.falsePositiveCount)}
            </Text>
          </Space>
        );
      }
    },
    {
      title: '最近任务样例',
      dataIndex: 'recentTaskSamples',
      width: 220,
      render: value => {
        const tasks = safeArray(value);
        if (!tasks.length) return '-';
        return (
          <Space direction="vertical" size={2} className="full-width">
            {tasks.slice(0, 3).map(task => (
              <Button
                key={`${task.taskId}-${task.reviewKey}`}
                type="link"
                className="rule-gap-task-link"
                onClick={() => openTask(task)}
              >
                #{task.taskId} · {task.projectName || '-'} · {task.reviewKey || 'default'}
              </Button>
            ))}
          </Space>
        );
      }
    }
  ];
  const recommendationExpandable = {
    columnTitle: <span className="rule-gap-expand-title">详情</span>,
    columnWidth: 64,
    expandedRowRender: row => (
      <div className="rule-gap-recommendation-detail">
        <Descriptions size="small" column={{ xs: 1, lg: 3 }}>
          <Descriptions.Item label="Signal">{row.signal || '-'}</Descriptions.Item>
          <Descriptions.Item label="缺口类型">{row.gapType || '-'}</Descriptions.Item>
          <Descriptions.Item label="Requested Context">{row.requestedContext || '-'}</Descriptions.Item>
          <Descriptions.Item label="建议能力">{row.suggestedCapability || '-'}</Descriptions.Item>
          <Descriptions.Item label="补全类型">
            {RULE_GAP_COMPLETION_TYPE[row.completionType] || row.completionType || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="评分">{countText(row.score)} / 100</Descriptions.Item>
          <Descriptions.Item label="出现次数">{countText(row.occurrenceCount)}</Descriptions.Item>
          <Descriptions.Item label="影响任务">{countText(row.taskCount)}</Descriptions.Item>
          <Descriptions.Item label="影响项目">{countText(row.projectCount)}</Descriptions.Item>
          <Descriptions.Item label="反馈关联" span={3}>
            {RULE_GAP_FEEDBACK_CORRELATION[row.feedbackSignals?.correlation] || row.feedbackSignals?.correlation || '暂无关联反馈'}
            {row.feedbackSignals?.note ? `；${row.feedbackSignals.note}` : ''}
          </Descriptions.Item>
        </Descriptions>
      </div>
    )
  };

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div className="page-heading-main">
          <Title level={3}>规则缺口看板</Title>
          <Text type="secondary">
            汇总历史审查中反复缺少的证据，帮助判断下一步最值得补什么；这里只展示统计、建议和任务跳转，不展示源码或敏感信息。
          </Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={applyFilters} loading={loading}>刷新</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} className="section-gap" />}
      <Card className="section-gap">
        <Space wrap>
          <Select
            allowClear
            showSearch
            className="filter-select"
            placeholder="项目"
            optionFilterProp="label"
            value={filters.projectId}
            options={projectOptions}
            onChange={value => updateFilter('projectId', value || null)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="缺口类型"
            value={filters.gapType}
            options={RULE_GAP_TYPE_OPTIONS}
            onChange={value => updateFilter('gapType', value || null)}
          />
          <Input
            allowClear
            className="rule-gap-signal-input"
            placeholder="Signal"
            value={filters.signal}
            onChange={event => updateFilter('signal', event.target.value)}
            onPressEnter={applyFilters}
          />
          <InputNumber
            min={1}
            max={3650}
            value={filters.recentDays}
            addonBefore="最近"
            addonAfter="天"
            onChange={value => updateFilter('recentDays', value || 30)}
          />
          <InputNumber
            min={1}
            max={500}
            value={filters.limit}
            addonBefore="Limit"
            onChange={value => updateFilter('limit', value || 50)}
          />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={applyFilters}>筛选</Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </Card>
      <Card className="section-gap">
        <div className="rule-gap-stats-grid">
          <div className="rule-gap-chart-card">
            <div className="rule-gap-chart-main">
              <div className="rule-gap-donut" style={recommendationChartStyle}>
                <div className="rule-gap-donut-inner">
                  <Text strong>{countText(recommendationTotal)}</Text>
                  <Text type="secondary">条建议</Text>
                </div>
              </div>
              <div>
                <Text strong>补全建议分布</Text>
                <div className="rule-gap-legend">
                  <span><i style={{ background: '#ef4444' }} />建议补全 {countText(recommendedCount)}</span>
                  <span><i style={{ background: '#f59e0b' }} />继续观察 {countText(watchCount)}</span>
                  <span><i style={{ background: '#94a3b8' }} />暂不处理 {countText(notNowCount)}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="rule-gap-chart-card">
            <Text strong>审查样本分布</Text>
            <div className="rule-gap-bars">
              {eventBreakdown.map(item => (
                <div className="rule-gap-bar-row" key={item.label}>
                  <span>{item.label}</span>
                  <div className="rule-gap-bar-track">
                    <div
                      className="rule-gap-bar-fill"
                      style={{ width: `${Math.max(0, Math.min(100, (item.value / eventTotal) * 100))}%`, background: item.color }}
                    />
                  </div>
                  <strong>{countText(item.value)}</strong>
                </div>
              ))}
            </div>
          </div>
          <div className="rule-gap-chart-card">
            <Text strong>关键指标</Text>
            <div className="rule-gap-metrics">
              <span><b>{countText(summary.returnedGroups)}</b><em>聚合项</em></span>
              <span><b>{countText(summary.totalOccurrences)}</b><em>出现次数</em></span>
              <span><b>{countText(summary.scannedEventCount)}</b><em>扫描事件</em></span>
              <span><b>{countText(summary.truncatedProgressSummaryCount)}</b><em>截断标记</em></span>
            </div>
          </div>
        </div>
      </Card>
      <Tabs
        defaultActiveKey="recommendations"
        items={[
          {
            key: 'recommendations',
            label: '建议补全',
            children: (
              <Table
                rowKey={(row, index) => `${row.recommendationStatus}-${row.completionType}-${row.signal}-${index}`}
                loading={loading}
                columns={recommendationColumns}
                dataSource={recommendationItems}
                expandable={recommendationExpandable}
                className="rule-gap-table"
                scroll={{ x: 1220 }}
                pagination={{ pageSize: 10, showSizeChanger: false }}
                locale={{ emptyText: <Empty description="暂无补全建议" /> }}
              />
            )
          },
          {
            key: 'details',
            label: '缺口明细',
            children: (
              <Table
                rowKey={(row, index) => `${row.gapType}-${row.signal}-${row.requestedContext}-${index}`}
                loading={loading}
                columns={columns}
                dataSource={dashboard.items || []}
                className="rule-gap-table"
                scroll={{ x: 1380 }}
                pagination={{ pageSize: 20, showSizeChanger: false }}
                locale={{ emptyText: <Empty description="暂无规则缺口聚合数据" /> }}
              />
            )
          }
        ]}
      />
    </div>
  );
}

function canConvertFeedbackToPolicy(row) {
  if (!row) return false;
  if (row.status === 'CONVERTED' || row.status === 'INSUFFICIENT' || row.status === 'IGNORED') return false;
  if (row.reasonType === 'CONTEXT_MISSING') return false;
  return row.status === 'VALID' || Boolean(row.suggestAsProjectRule);
}

function convertFeedbackToPolicyDisabledReason(row) {
  if (!row || canConvertFeedbackToPolicy(row)) return '';
  if (row.status === 'CONVERTED') return '该反馈已沉淀为项目策略。';
  if (row.status === 'INSUFFICIENT') return '信息不足的反馈不能生成项目策略。';
  if (row.status === 'IGNORED') return '已忽略的反馈不能生成项目策略。';
  if (row.reasonType === 'CONTEXT_MISSING') return '上下文不足反馈应进入后续上下文统计，不会沉淀为项目策略。';
  return '需先标记为有效反馈，或提交反馈时勾选“建议沉淀”。';
}

function policyDraftFromFeedback(row) {
  const riskLabel = row?.riskTitle || categoryLabel(row?.riskType);
  const reasonText = String(row?.reasonText || '').trim();
  const sourceLines = [
    reasonText,
    row?.reasonType ? `反馈原因：${reviewFeedbackReasonLabel(row.reasonType)}` : '',
    row?.riskTitle ? `来源风险：${row.riskTitle}` : ''
  ].filter(Boolean);
  return {
    policyType: row?.reasonType === 'HAS_EXTERNAL_GUARD' ? 'CONTEXT_FACT' : 'PROJECT_RULE',
    riskType: row?.riskType || '',
    title: `关于 ${riskLabel || '该反馈'} 的项目 Review 策略`,
    content: sourceLines.join('\n') || '该反馈已确认可作为本项目后续 Review 的项目事实或审查规则。',
    enabled: true
  };
}

function RiskFeedbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [activeTabKey, setActiveTabKey] = useState('feedbacks');
  const [items, setItems] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [filters, setFilters] = useState({
    projectId: null,
    sourceType: null,
    feedbackType: null,
    reasonType: null,
    missingContextType: null,
    policyCandidate: false,
    status: null,
    keyword: ''
  });
  const [contextMissingStats, setContextMissingStats] = useState({ total: 0, byRiskType: [], byMissingContextType: [] });
  const [policies, setPolicies] = useState([]);
  const [policyProjectId, setPolicyProjectId] = useState(null);
  const [policyFilters, setPolicyFilters] = useState({
    enabled: null,
    policyType: null,
    riskType: ''
  });
  const [loading, setLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);
  const [updatingPolicyId, setUpdatingPolicyId] = useState(null);
  const [error, setError] = useState(null);
  const [policyError, setPolicyError] = useState(null);
  const [policyModal, setPolicyModal] = useState({ open: false, mode: 'create', feedback: null, policy: null });
  const [policyDraft, setPolicyDraft] = useState({
    policyType: 'PROJECT_RULE',
    riskType: '',
    title: '',
    content: '',
    enabled: true
  });
  const [policySaving, setPolicySaving] = useState(false);

  const projectOptions = useMemo(
    () => projects.map(project => ({ label: project.name, value: project.id })),
    [projects]
  );

  const load = async ({ pageNo = pagination.pageNo, pageSize = pagination.pageSize, nextFilters = filters } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('pageNo', String(pageNo));
      params.set('pageSize', String(pageSize));
      if (nextFilters.projectId) params.set('projectId', String(nextFilters.projectId));
      if (nextFilters.sourceType) params.set('sourceType', nextFilters.sourceType);
      if (nextFilters.feedbackType) params.set('feedbackType', nextFilters.feedbackType);
      if (nextFilters.reasonType) params.set('reasonType', nextFilters.reasonType);
      if (nextFilters.missingContextType) params.set('missingContextType', nextFilters.missingContextType);
      if (nextFilters.policyCandidate) params.set('policyCandidate', 'true');
      if (nextFilters.status) params.set('status', nextFilters.status);
      if (nextFilters.keyword?.trim()) params.set('keyword', nextFilters.keyword.trim());
      const data = await fetchApi(`/api/risk-feedback?${params.toString()}`);
      setItems(data.items || []);
      setPagination({ pageNo: data.pageNo || pageNo, pageSize: data.pageSize || pageSize, total: data.total || 0 });
      setContextMissingStats(data.contextMissingStats || { total: 0, byRiskType: [], byMissingContextType: [] });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const data = await fetchApi('/api/projects?includeDisabled=true');
      const nextProjects = data.items || [];
      setProjects(nextProjects);
      setPolicyProjectId(current => current || nextProjects[0]?.id || null);
    } catch {
      setProjects([]);
    }
  };

  const loadPolicies = async ({
    projectId = policyProjectId,
    nextFilters = policyFilters
  } = {}) => {
    if (!projectId) {
      setPolicies([]);
      return;
    }
    setPolicyLoading(true);
    setPolicyError(null);
    try {
      const params = new URLSearchParams();
      if (nextFilters.enabled !== null && nextFilters.enabled !== undefined) {
        params.set('enabled', String(nextFilters.enabled));
      }
      if (nextFilters.policyType) params.set('policyType', nextFilters.policyType);
      if (nextFilters.riskType?.trim()) params.set('riskType', nextFilters.riskType.trim());
      const suffix = params.toString() ? `?${params.toString()}` : '';
      const data = await fetchApi(`/api/projects/${projectId}/review-policies${suffix}`);
      setPolicies(Array.isArray(data) ? data : []);
    } catch (err) {
      setPolicyError(err.message);
    } finally {
      setPolicyLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    load({ pageNo: 1 });
  }, []);

  useEffect(() => {
    if (activeTabKey === 'policies' && policyProjectId) {
      loadPolicies({ projectId: policyProjectId });
    }
  }, [activeTabKey, policyProjectId]);

  const updateFilter = (field, value) => {
    setFilters(current => ({
      ...current,
      [field]: field === 'policyCandidate' ? Boolean(value) : (value || null)
    }));
  };

  const updatePolicyFilter = (field, value) => {
    setPolicyFilters(current => ({
      ...current,
      [field]: value === undefined ? null : value
    }));
  };

  const updateStatus = async (feedbackId, status) => {
    setUpdatingId(feedbackId);
    try {
      await fetchApi(`/api/risk-feedback/${feedbackId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status })
      });
      message.success('反馈状态已更新');
      await load({ pageNo: pagination.pageNo });
    } catch (err) {
      message.error(err.message);
    } finally {
      setUpdatingId(null);
    }
  };

  const openGeneratePolicy = row => {
    setPolicyDraft(policyDraftFromFeedback(row));
    setPolicyModal({ open: true, mode: 'create', feedback: row, policy: null });
  };

  const openEditPolicy = row => {
    setPolicyDraft({
      policyType: row.policyType || 'PROJECT_RULE',
      riskType: row.riskType || '',
      title: row.title || '',
      content: row.content || '',
      enabled: Boolean(row.enabled)
    });
    setPolicyModal({ open: true, mode: 'edit', feedback: null, policy: row });
  };

  const closePolicyModal = () => {
    setPolicyModal({ open: false, mode: 'create', feedback: null, policy: null });
  };

  const savePolicy = async () => {
    setPolicySaving(true);
    try {
      const payload = {
        policyType: policyDraft.policyType,
        riskType: policyDraft.riskType || null,
        title: policyDraft.title,
        content: policyDraft.content,
        enabled: policyDraft.enabled
      };
      const saved = policyModal.mode === 'edit'
        ? await fetchApi(`/api/project-review-policies/${policyModal.policy.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        })
        : await fetchApi(`/api/risk-feedback/${policyModal.feedback.id}/convert-to-policy`, {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      message.success(policyModal.mode === 'edit' ? '项目策略已更新' : '项目策略已生成');
      closePolicyModal();
      if (saved?.projectId) setPolicyProjectId(saved.projectId);
      await load({ pageNo: pagination.pageNo });
      await loadPolicies({ projectId: saved?.projectId || policyProjectId });
    } catch (err) {
      message.error(err.message);
    } finally {
      setPolicySaving(false);
    }
  };

  const updatePolicyEnabled = async (row, enabled) => {
    setUpdatingPolicyId(row.id);
    try {
      await fetchApi(`/api/project-review-policies/${row.id}/enabled`, {
        method: 'PUT',
        body: JSON.stringify({ enabled })
      });
      message.success(enabled ? '项目策略已启用' : '项目策略已停用');
      await loadPolicies({ projectId: row.projectId || policyProjectId });
    } catch (err) {
      message.error(err.message);
    } finally {
      setUpdatingPolicyId(null);
    }
  };

  const columns = [
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    {
      title: '任务',
      dataIndex: 'taskId',
      width: 100,
      render: value => (
        <Button type="link" onClick={() => navigate(`/tasks/${value}`, { state: { from: route } })}>
          #{value}
        </Button>
      )
    },
    { title: '来源', dataIndex: 'sourceType', width: 110, render: value => <Tag>{reviewFeedbackSourceLabel(value)}</Tag> },
    { title: '风险类型', dataIndex: 'riskType', width: 130, ellipsis: true, render: value => value ? <Tag color="blue">{categoryLabel(value)}</Tag> : '-' },
    { title: '风险标题', dataIndex: 'riskTitle', ellipsis: true, render: value => value || '-' },
    { title: '反馈', dataIndex: 'feedbackType', width: 110, render: value => <Tag color={reviewFeedbackTypeColor(value)}>{reviewFeedbackTypeLabel(value)}</Tag> },
    { title: '原因', dataIndex: 'reasonType', width: 120, render: value => value ? reviewFeedbackReasonLabel(value) : '-' },
    {
      title: '缺失上下文',
      dataIndex: 'missingContextTypes',
      width: 170,
      render: value => {
        const items = Array.isArray(value) ? value : [];
        if (!items.length) return '-';
        return (
          <Space size={[0, 4]} wrap>
            {items.map(item => <Tag key={item} color="orange">{missingContextLabel(item)}</Tag>)}
          </Space>
        );
      }
    },
    PROJECT_REVIEW_POLICY_UI_ENABLED && {
      title: '沉淀',
      dataIndex: 'suggestAsProjectRule',
      width: 90,
      render: (value, row) => {
        if (row.status === 'CONVERTED') return <Tag color="purple">已沉淀</Tag>;
        if (value) return <Tag color="green">建议</Tag>;
        return '-';
      }
    },
    { title: '说明', dataIndex: 'reasonText', ellipsis: true, render: value => value || '-' },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={reviewFeedbackStatusColor(value)}>{reviewFeedbackStatusLabel(value)}</Tag> },
    { title: '创建时间', dataIndex: 'createdAt', width: 180, render: value => value || '-' },
    {
      title: '操作',
      width: 320,
      fixed: 'right',
      render: (_, row) => {
        const disabledReason = convertFeedbackToPolicyDisabledReason(row);
        return (
          <Space wrap>
            <Button size="small" loading={updatingId === row.id} disabled={row.status === 'VALID'} onClick={() => updateStatus(row.id, 'VALID')}>有效</Button>
            <Button size="small" loading={updatingId === row.id} disabled={row.status === 'INSUFFICIENT'} onClick={() => updateStatus(row.id, 'INSUFFICIENT')}>信息不足</Button>
            <Button size="small" loading={updatingId === row.id} disabled={row.status === 'IGNORED'} onClick={() => updateStatus(row.id, 'IGNORED')}>忽略</Button>
            {PROJECT_REVIEW_POLICY_UI_ENABLED && (
              <Tooltip title={disabledReason || '生成项目策略'}>
                <span>
                  <Button
                    size="small"
                    type="primary"
                    disabled={Boolean(disabledReason)}
                    onClick={() => openGeneratePolicy(row)}
                  >
                    生成策略
                  </Button>
                </span>
              </Tooltip>
            )}
          </Space>
        );
      }
    }
  ].filter(Boolean);

  const policyColumns = [
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    {
      title: '类型',
      dataIndex: 'policyType',
      width: 120,
      render: value => <Tag color={projectReviewPolicyTypeColor(value)}>{projectReviewPolicyTypeLabel(value)}</Tag>
    },
    { title: '风险类型', dataIndex: 'riskType', width: 130, ellipsis: true, render: value => value ? <Tag color="blue">{categoryLabel(value)}</Tag> : '-' },
    { title: '标题', dataIndex: 'title', width: 260, ellipsis: true, render: value => value || '-' },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: value => <Text className="policy-content-cell" title={value}>{value || '-'}</Text>
    },
    { title: '来源反馈', dataIndex: 'sourceFeedbackId', width: 100, render: value => value ? `#${value}` : '-' },
    { title: '状态', dataIndex: 'enabled', width: 90, render: value => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
    { title: '版本', dataIndex: 'version', width: 70, render: value => value ?? '-' },
    { title: '更新时间', dataIndex: 'updatedAt', width: 180, render: value => value || '-' },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, row) => (
        <Space wrap>
          <Button size="small" onClick={() => openEditPolicy(row)}>编辑</Button>
          <Button
            size="small"
            loading={updatingPolicyId === row.id}
            onClick={() => updatePolicyEnabled(row, !row.enabled)}
          >
            {row.enabled ? '停用' : '启用'}
          </Button>
        </Space>
      )
    }
  ];

  const feedbackPanel = (
    <>
      <Card>
        <Space wrap className="task-filter-bar">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            className="filter-select"
            placeholder="项目"
            value={filters.projectId || undefined}
            options={projectOptions}
            onChange={value => updateFilter('projectId', value)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="来源"
            value={filters.sourceType || undefined}
            options={REVIEW_FEEDBACK_SOURCE_OPTIONS}
            onChange={value => updateFilter('sourceType', value)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="反馈类型"
            value={filters.feedbackType || undefined}
            options={REVIEW_FEEDBACK_TYPE_OPTIONS}
            onChange={value => updateFilter('feedbackType', value)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="反馈原因"
            value={filters.reasonType || undefined}
            options={REVIEW_FEEDBACK_REASON_OPTIONS}
            onChange={value => updateFilter('reasonType', value)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="缺失上下文"
            value={filters.missingContextType || undefined}
            options={MISSING_CONTEXT_TYPE_OPTIONS}
            onChange={value => updateFilter('missingContextType', value)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="状态"
            value={filters.status || undefined}
            options={REVIEW_FEEDBACK_STATUS_OPTIONS}
            onChange={value => updateFilter('status', value)}
          />
          <Switch
            checked={filters.policyCandidate}
            checkedChildren="建议沉淀"
            unCheckedChildren="全部"
            onChange={checked => updateFilter('policyCandidate', checked)}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="项目、任务或说明"
            value={filters.keyword || ''}
            onChange={event => updateFilter('keyword', event.target.value)}
            onPressEnter={() => load({ pageNo: 1 })}
          />
          <Button type="primary" onClick={() => load({ pageNo: 1 })}>搜索</Button>
        </Space>
      </Card>
      <Alert
        className="section-gap"
        type="info"
        showIcon
        message={`上下文不足反馈：${contextMissingStats.total || 0} 条`}
        description={(
          <Space direction="vertical" size={4}>
            <Space wrap>
              {(contextMissingStats.byRiskType || []).slice(0, 6).map(item => (
                <Tag key={item.riskType} color="blue">
                  {categoryLabel(item.riskType)} {item.count}
                </Tag>
              ))}
              {!(contextMissingStats.byRiskType || []).length && <Text type="secondary">暂无风险类型分布</Text>}
            </Space>
            <Space wrap>
              {(contextMissingStats.byMissingContextType || []).slice(0, 8).map(item => (
                <Tag key={item.missingContextType} color="orange">
                  {missingContextLabel(item.missingContextType)} {item.count}
                </Tag>
              ))}
              {!(contextMissingStats.byMissingContextType || []).length && <Text type="secondary">暂无缺失上下文类型分布</Text>}
            </Space>
          </Space>
        )}
      />
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Card className="section-gap">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          tableLayout="fixed"
          scroll={{ x: 1870 }}
          pagination={{
            current: pagination.pageNo,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showTotal: total => `共 ${total} 条`,
            onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
          }}
        />
      </Card>
    </>
  );

  const policyPanel = (
    <>
      <Card>
        <Space wrap className="task-filter-bar">
          <Select
            showSearch
            optionFilterProp="label"
            className="filter-select"
            placeholder="项目"
            value={policyProjectId || undefined}
            options={projectOptions}
            onChange={value => setPolicyProjectId(value || null)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="状态"
            value={policyFilters.enabled === null ? undefined : policyFilters.enabled}
            options={[
              { label: '启用', value: true },
              { label: '停用', value: false }
            ]}
            onChange={value => updatePolicyFilter('enabled', value ?? null)}
          />
          <Select
            allowClear
            className="filter-select"
            placeholder="策略类型"
            value={policyFilters.policyType || undefined}
            options={PROJECT_REVIEW_POLICY_TYPE_OPTIONS}
            onChange={value => updatePolicyFilter('policyType', value || null)}
          />
          <Input
            allowClear
            className="filter-select"
            placeholder="风险类型"
            value={policyFilters.riskType || ''}
            onChange={event => updatePolicyFilter('riskType', event.target.value)}
            onPressEnter={() => loadPolicies({ projectId: policyProjectId })}
          />
          <Button type="primary" onClick={() => loadPolicies({ projectId: policyProjectId })}>搜索</Button>
          <Button onClick={() => loadPolicies({ projectId: policyProjectId })} icon={<ReloadOutlined />}>刷新</Button>
        </Space>
      </Card>
      {policyError && <Alert className="section-gap" type="error" showIcon message={policyError} />}
      <Card className="section-gap">
        <Table
          rowKey="id"
          loading={policyLoading}
          columns={policyColumns}
          dataSource={policies}
          tableLayout="fixed"
          scroll={{ x: 1480 }}
          pagination={false}
          locale={{ emptyText: policyProjectId ? <Empty description="暂无项目策略" /> : <Empty description="请先选择项目" /> }}
        />
      </Card>
    </>
  );

  const feedbackTabItems = [
    { key: 'feedbacks', label: '反馈记录', children: feedbackPanel },
    PROJECT_REVIEW_POLICY_UI_ENABLED && { key: 'policies', label: '项目策略', children: policyPanel }
  ].filter(Boolean);
  const displayedFeedbackTabKey = feedbackTabItems.some(item => item.key === activeTabKey)
    ? activeTabKey
    : 'feedbacks';

  return (
    <div className="page-shell">
      <Tabs
        className="feedback-page-tabs"
        activeKey={displayedFeedbackTabKey}
        onChange={setActiveTabKey}
        items={feedbackTabItems}
      />
      <Modal
        title={policyModal.mode === 'edit' ? '编辑项目策略' : '生成项目策略'}
        open={policyModal.open}
        onCancel={closePolicyModal}
        onOk={savePolicy}
        confirmLoading={policySaving}
        okText={policyModal.mode === 'edit' ? '保存' : '生成'}
        cancelText="取消"
        width={720}
      >
        <Space direction="vertical" size="middle" className="full-width policy-modal-body">
          {policyModal.feedback && (
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="来源反馈">
                #{policyModal.feedback.id} {policyModal.feedback.riskTitle || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="反馈原因">
                {policyModal.feedback.reasonType ? reviewFeedbackReasonLabel(policyModal.feedback.reasonType) : '-'}
              </Descriptions.Item>
            </Descriptions>
          )}
          <Space direction="vertical" size={6} className="full-width">
            <Text type="secondary">策略类型</Text>
            <Select
              className="full-width"
              value={policyDraft.policyType}
              options={PROJECT_REVIEW_POLICY_TYPE_OPTIONS}
              onChange={value => setPolicyDraft(current => ({ ...current, policyType: value }))}
            />
          </Space>
          <Space direction="vertical" size={6} className="full-width">
            <Text type="secondary">风险类型</Text>
            <Input
              value={policyDraft.riskType}
              placeholder="例如 TRANSACTION"
              onChange={event => setPolicyDraft(current => ({ ...current, riskType: event.target.value }))}
            />
          </Space>
          <Space direction="vertical" size={6} className="full-width">
            <Text type="secondary">标题</Text>
            <Input
              value={policyDraft.title}
              maxLength={255}
              onChange={event => setPolicyDraft(current => ({ ...current, title: event.target.value }))}
            />
          </Space>
          <Space direction="vertical" size={6} className="full-width">
            <Text type="secondary">内容</Text>
            <Input.TextArea
              rows={6}
              maxLength={8000}
              value={policyDraft.content}
              onChange={event => setPolicyDraft(current => ({ ...current, content: event.target.value }))}
            />
          </Space>
          <Switch
            checked={policyDraft.enabled}
            checkedChildren="启用"
            unCheckedChildren="停用"
            onChange={checked => setPolicyDraft(current => ({ ...current, enabled: checked }))}
          />
        </Space>
      </Modal>
    </div>
  );
}

function SettingsPage() {
  return <TemplateConfig />;
}

function ReleaseNotesPage() {
  const [activeReleaseId, setActiveReleaseId] = useState(releaseNotes[0]?.id || null);

  return (
    <div className="page-shell release-page-shell">
      <div className="release-list">
        {releaseNotes.map((item, index) => {
          const isActive = activeReleaseId === item.id;
          const isLast = index === releaseNotes.length - 1;
          const visibleHighlights = (item.highlights || []).slice(0, 3);
          return (
            <article
              key={item.id}
              className={`release-entry ${isActive ? 'is-active' : ''}`}
              style={{ '--item-index': index }}
              onMouseEnter={() => setActiveReleaseId(item.id)}
              onFocus={() => setActiveReleaseId(item.id)}
            >
              <div className="release-track">
                <Text className="release-date">{item.releaseDate}</Text>
                <button
                  type="button"
                  className="release-marker"
                  aria-label={`${item.version} ${item.title}`}
                  onMouseEnter={() => setActiveReleaseId(item.id)}
                  onFocus={() => setActiveReleaseId(item.id)}
                  onClick={() => setActiveReleaseId(item.id)}
                >
                  <span className="release-marker-core" />
                  <span className="release-marker-ripple" />
                </button>
                {!isLast && <span className="release-track-line" aria-hidden="true" />}
              </div>
              <div className="release-card">
                <div className="release-card-head">
                  <div>
                    <Text className="release-version">{item.version}</Text>
                    <Title level={4}>{item.title}</Title>
                  </div>
                  <Space wrap>
                    {(item.tags || []).map(tag => (
                      <Tag key={tag} className="release-tag">
                        {tag}
                      </Tag>
                    ))}
                  </Space>
                </div>
                <Paragraph className="release-summary">{item.summary}</Paragraph>
                <ul className="release-highlights">
                  {visibleHighlights.map(highlight => (
                    <li key={highlight}>{highlight}</li>
                  ))}
                </ul>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function HelpCodeBlock({ children }) {
  return <pre className="help-code-block">{children}</pre>;
}

function HelpImage({ src, alt }) {
  return (
    <figure className="help-image-frame">
      <img src={src} alt={alt} loading="lazy" />
      <figcaption>{alt}</figcaption>
    </figure>
  );
}

function HelpPage() {
  return (
    <div className="page-shell help-page-shell">
      <section className="help-hero">
        <Space orientation="vertical" size={10}>
          <Tag color="blue">接入帮助</Tag>
          <Title level={2}>GitLab / 钉钉 / 项目组接入</Title>
          <Paragraph>
            按 GitLab Webhook、钉钉机器人、平台项目组、GitLab 项目和模型配置的顺序完成接入，
            平台即可从 Merge Request 或 Push 事件生成提醒卡片并推送到钉钉群。
          </Paragraph>
        </Space>
      </section>

      <div className="help-section-list">
        <section className="help-section">
          <div className="help-section-number">一</div>
          <div className="help-section-content">
            <Title level={3}>配置 GitLab Webhook</Title>
            <Paragraph>进入需要接入的平台项目：</Paragraph>
            <HelpCodeBlock>GitLab 项目 -&gt; Settings -&gt; Webhooks</HelpCodeBlock>
            <Paragraph>Webhook URL 固定填写：</Paragraph>
            <HelpCodeBlock>http://ai-review.ihere.net/api/webhooks/gitlab/merge-request</HelpCodeBlock>
            <Paragraph>打勾：</Paragraph>
            <Space wrap>
              <Tag color="blue">Merge request events</Tag>
              <Tag color="cyan">Push events</Tag>
            </Space>
            <Paragraph className="help-paragraph-gap">Secret Token 保持为空即可。</Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/deadbf05a7ea499198d905a5f4c0cb74.png"
              alt="GitLab Webhook 配置示例"
            />
            <Paragraph>保存后可以点击 GitLab 的测试按钮确认平台是否能收到请求。</Paragraph>
          </div>
        </section>

        <section className="help-section">
          <div className="help-section-number">二</div>
          <div className="help-section-content">
            <Title level={3}>配置钉钉机器人</Title>
            <Paragraph>在用于接收审查结果的钉钉群中创建机器人：</Paragraph>
            <HelpCodeBlock>群设置 -&gt; 机器人 -&gt; 添加机器人 -&gt; 自定义机器人</HelpCodeBlock>
            <Paragraph>安全设置选择关键词，并填写：</Paragraph>
            <HelpCodeBlock>变更审查结果</HelpCodeBlock>
            <Alert
              className="help-alert"
              type="warning"
              showIcon
              title="公网 IP 白名单可作为备选，但平台出口 IP 可能随网络、部署或云资源调整而变化，后续维护成本更高。"
            />
            <Paragraph>
              创建完成后，钉钉会生成机器人 Webhook URL。拿到 URL 后，只在平台“设置”页中配置。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/image-20260527110201878.png"
              alt="钉钉机器人关键词配置示例"
            />
          </div>
        </section>

        <section className="help-section">
          <div className="help-section-number">三</div>
          <div className="help-section-content">
            <Title level={3}>配置平台项目组</Title>
            <Paragraph>进入平台：</Paragraph>
            <HelpCodeBlock>设置 -&gt; 项目组 / 端类型配置</HelpCodeBlock>
            <Paragraph>
              给项目组配置钉钉机器人时，把上一步从钉钉复制的 Webhook URL 填入该项目组的机器人配置，并启用它。
              平台只会按项目所属项目组发送通知；该项目组未配置机器人时，本次通知会记录为跳过。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-27_11-10-57.png"
              alt="平台项目组与钉钉机器人配置示例"
            />
            <Paragraph>
              首次收到某个 GitLab 项目的 Webhook 后，平台可以自动创建项目记录。自动创建的项目会进入默认项目组，后续可以再人工调整。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/cd00250a14cb455e95f79c07f7cd6a03.png"
              alt="平台项目组配置示例"
            />
            <Paragraph>
              首次收到某个 GitLab 项目的 Webhook 后，项目打入通用组，同时自动匹配路径到具体端类型，走端类型对应的 AI Review 模板。
              注意，结合各端项目实际目录判断，确认映射规则能覆盖项目日常提交的主要代码路径，避免多端路径存在冲突，否则平台可能无法准确识别端类型和 AI Review 审查模板。
              当然，可以通过手动指定项目组，后续优先以项目组的策略为准。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-28_19-50-37.png"
              alt="端类型路径映射配置示例"
            />
          </div>
        </section>
      </div>
    </div>
  );
}

function ReviewQualityDashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [projects, setProjects] = useState([]);
  const [filters, setFilters] = useState({
    projectId: null,
    provider: '',
    profile: '',
    riskType: '',
    verdict: null
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const projectOptions = useMemo(
    () => projects.map(project => ({ label: project.name, value: project.id })),
    [projects]
  );

  const loadProjects = async () => {
    try {
      const data = await fetchApi('/api/projects?includeDisabled=true');
      setProjects(data.items || []);
    } catch {
      setProjects([]);
    }
  };

  const load = async ({ nextFilters = filters } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (nextFilters.projectId) params.set('projectId', String(nextFilters.projectId));
      if (nextFilters.provider?.trim()) params.set('provider', nextFilters.provider.trim());
      if (nextFilters.profile?.trim()) params.set('profile', nextFilters.profile.trim());
      if (nextFilters.riskType?.trim()) params.set('riskType', nextFilters.riskType.trim());
      if (nextFilters.verdict) params.set('verdict', nextFilters.verdict);
      const query = params.toString();
      const data = await fetchApi(`/api/review-quality/dashboard${query ? `?${query}` : ''}`);
      setDashboard(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    load();
  }, []);

  const updateFilter = (field, value) => {
    setFilters(current => ({
      ...current,
      [field]: value === undefined ? null : value
    }));
  };

  const resetFilters = () => {
    const nextFilters = {
      projectId: null,
      provider: '',
      profile: '',
      riskType: '',
      verdict: null
    };
    setFilters(nextFilters);
    load({ nextFilters });
  };

  const summary = dashboard?.summary || {};
  const dimensionColumns = [
    { title: '维度', dataIndex: 'label', ellipsis: true, render: (value, row) => value || row.key || '-' },
    { title: '样本数', dataIndex: 'sampleCount', width: 90, render: value => value ?? 0 },
    { title: '误判', dataIndex: 'falsePositiveCount', width: 80, render: value => value ?? 0 },
    { title: '误判率', dataIndex: 'falsePositiveRate', width: 90, render: value => formatRate(value) },
    { title: '上下文不足', dataIndex: 'contextMissingCount', width: 110, render: value => value ?? 0 },
    { title: '上下文不足率', dataIndex: 'contextMissingRate', width: 120, render: value => formatRate(value) },
    { title: '等级偏高', dataIndex: 'levelTooHighCount', width: 100, render: value => value ?? 0 },
    { title: '等级偏低', dataIndex: 'levelTooLowCount', width: 100, render: value => value ?? 0 },
    { title: '重复', dataIndex: 'duplicateFindingCount', width: 80, render: value => value ?? 0 },
    { title: '漏报', dataIndex: 'missingFindingCount', width: 80, render: value => value ?? 0 }
  ];
  const verdictColumns = [
    {
      title: '裁决',
      dataIndex: 'verdict',
      render: value => <Tag color={evaluationCaseVerdictColor(value)}>{evaluationCaseVerdictLabel(value)}</Tag>
    },
    { title: '数量', dataIndex: 'count', width: 100, render: value => value ?? 0 }
  ];
  const metricCards = [
    { label: '样本数', value: summary.sampleCount ?? 0 },
    { label: '误判数 / 率', value: `${summary.falsePositiveCount ?? 0} / ${formatRate(summary.falsePositiveRate)}` },
    { label: '上下文不足 / 率', value: `${summary.contextMissingCount ?? 0} / ${formatRate(summary.contextMissingRate)}` },
    { label: '等级偏高', value: summary.levelTooHighCount ?? 0 },
    { label: '等级偏低', value: summary.levelTooLowCount ?? 0 },
    { label: '重复 finding', value: summary.duplicateFindingCount ?? 0 },
    { label: '漏报样本', value: summary.missingFindingCount ?? 0 }
  ];
  const replaySummary = dashboard?.replaySummary || {};
  const refinementSummary = dashboard?.refinementSummary || {};
  const deterministicSummary = dashboard?.deterministicCheckSummary || {};

  return (
    <div className="page-shell">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-title-row">
          <div>
            <Title level={3}>质量看板</Title>
            <Text type="secondary">基于评估样本、回放记录、补证据和确定性检查的最小 Review 质量治理视图。</Text>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </div>
        <Card>
          <Space wrap className="task-filter-bar">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="filter-select"
              placeholder="项目"
              value={filters.projectId || undefined}
              options={projectOptions}
              onChange={value => updateFilter('projectId', value)}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Provider"
              value={filters.provider}
              onChange={event => updateFilter('provider', event.target.value)}
              onPressEnter={() => load()}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Profile"
              value={filters.profile}
              onChange={event => updateFilter('profile', event.target.value)}
              onPressEnter={() => load()}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="风险类型"
              value={filters.riskType}
              onChange={event => updateFilter('riskType', event.target.value)}
              onPressEnter={() => load()}
            />
            <Select
              allowClear
              className="filter-select"
              placeholder="人工裁决"
              value={filters.verdict || undefined}
              options={EVALUATION_CASE_VERDICT_OPTIONS}
              onChange={value => updateFilter('verdict', value)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => load()}>搜索</Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Card>
        {error && <Alert type="error" showIcon message={error} />}
        <Spin spinning={loading}>
          <Space direction="vertical" size="large" className="full-width">
            <Row gutter={[16, 16]}>
              {metricCards.map(item => (
                <Col xs={24} sm={12} md={8} lg={6} xl={4} key={item.label}>
                  <Card size="small">
                    <Text type="secondary">{item.label}</Text>
                    <Title level={4}>{item.value}</Title>
                  </Card>
                </Col>
              ))}
            </Row>
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <Card title="Verdict 分布">
                  <Table
                    rowKey="verdict"
                    size="small"
                    columns={verdictColumns}
                    dataSource={dashboard?.verdictDistribution || []}
                    pagination={false}
                  />
                </Card>
              </Col>
              <Col xs={24} lg={16}>
                <Card title="辅助诊断摘要">
                  <Descriptions column={2} size="small" bordered>
                    <Descriptions.Item label="回放 item">{replaySummary.itemCount ?? 0}</Descriptions.Item>
                    <Descriptions.Item label="回放完成 / 失败">{replaySummary.completedCount ?? 0} / {replaySummary.failedCount ?? 0}</Descriptions.Item>
                    <Descriptions.Item label="回放平均耗时">{replaySummary.durationMsAvg ?? 0} ms</Descriptions.Item>
                    <Descriptions.Item label="补证据完成 / 失败">{refinementSummary.completedCount ?? 0} / {refinementSummary.failedCount ?? 0}</Descriptions.Item>
                    <Descriptions.Item label="确定性检查 run">{deterministicSummary.runCount ?? 0}</Descriptions.Item>
                    <Descriptions.Item label="确定性命中">{deterministicSummary.findingCount ?? 0}</Descriptions.Item>
                    <Descriptions.Item label="补证据范围" span={2}>{refinementSummary.scopeNote || '-'}</Descriptions.Item>
                    <Descriptions.Item label="确定性检查范围" span={2}>{deterministicSummary.scopeNote || '-'}</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>
            <Card title="项目维度 Top">
              <Table
                rowKey="key"
                size="small"
                columns={dimensionColumns}
                dataSource={dashboard?.dimensions?.projects || []}
                pagination={false}
                scroll={{ x: 1020 }}
              />
            </Card>
            <Card title="Provider 维度 Top">
              <Table
                rowKey="key"
                size="small"
                columns={dimensionColumns}
                dataSource={dashboard?.dimensions?.providers || []}
                pagination={false}
                scroll={{ x: 1020 }}
              />
            </Card>
            <Card title="Profile 维度 Top">
              <Table
                rowKey="key"
                size="small"
                columns={dimensionColumns}
                dataSource={dashboard?.dimensions?.profiles || []}
                pagination={false}
                scroll={{ x: 1020 }}
              />
            </Card>
            <Card title="风险类型维度 Top">
              <Table
                rowKey="key"
                size="small"
                columns={dimensionColumns}
                dataSource={dashboard?.dimensions?.riskTypes || []}
                pagination={false}
                scroll={{ x: 1020 }}
              />
            </Card>
          </Space>
        </Spin>
      </Space>
    </div>
  );
}

function EvaluationCasesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [items, setItems] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [filters, setFilters] = useState({
    projectId: null,
    provider: '',
    profile: '',
    riskType: '',
    verdict: null
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const projectOptions = useMemo(
    () => projects.map(project => ({ label: project.name, value: project.id })),
    [projects]
  );

  const loadProjects = async () => {
    try {
      const data = await fetchApi('/api/projects?includeDisabled=true');
      setProjects(data.items || []);
    } catch {
      setProjects([]);
    }
  };

  const load = async ({ pageNo = pagination.pageNo, pageSize = pagination.pageSize, nextFilters = filters } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('pageNo', String(pageNo));
      params.set('pageSize', String(pageSize));
      if (nextFilters.projectId) params.set('projectId', String(nextFilters.projectId));
      if (nextFilters.provider?.trim()) params.set('provider', nextFilters.provider.trim());
      if (nextFilters.profile?.trim()) params.set('profile', nextFilters.profile.trim());
      if (nextFilters.riskType?.trim()) params.set('riskType', nextFilters.riskType.trim());
      if (nextFilters.verdict) params.set('verdict', nextFilters.verdict);
      const data = await fetchApi(`/api/evaluation-cases?${params.toString()}`);
      setItems(data.items || []);
      setPagination({ pageNo: data.pageNo || pageNo, pageSize: data.pageSize || pageSize, total: data.total || 0 });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    load({ pageNo: 1 });
  }, []);

  const updateFilter = (field, value) => {
    setFilters(current => ({
      ...current,
      [field]: value === undefined ? null : value
    }));
  };

  const resetFilters = () => {
    const nextFilters = {
      projectId: null,
      provider: '',
      profile: '',
      riskType: '',
      verdict: null
    };
    setFilters(nextFilters);
    load({ pageNo: 1, nextFilters });
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    {
      title: '任务',
      dataIndex: 'taskId',
      width: 100,
      render: value => value ? (
        <Button type="link" onClick={() => navigate(`/tasks/${value}`, { state: { from: route } })}>
          #{value}
        </Button>
      ) : '-'
    },
    { title: '来源', dataIndex: 'source', width: 110, render: value => <Tag>{value === 'AI_FINDING' ? 'AI Finding' : '人工样本'}</Tag> },
    { title: 'Provider', dataIndex: 'provider', width: 120, ellipsis: true, render: value => value || '-' },
    { title: 'Profile', dataIndex: 'profile', width: 190, ellipsis: true, render: value => value || '-' },
    { title: 'Review Key', dataIndex: 'reviewKey', width: 150, ellipsis: true, render: value => value || '-' },
    { title: '风险类型', dataIndex: 'riskType', width: 130, render: value => value ? <Tag color="blue">{categoryLabel(value)}</Tag> : '-' },
    { title: '等级', dataIndex: 'severity', width: 100, render: value => value ? <Tag color={severityColor(value)}>{severityLabel(value)}</Tag> : '-' },
    { title: '上下文', dataIndex: 'contextStatus', width: 110, render: value => value ? <Tag color={contextStatusColor(value)}>{contextStatusLabel(value)}</Tag> : '-' },
    {
      title: '裁决',
      dataIndex: 'verdict',
      width: 130,
      render: value => <Tag color={evaluationCaseVerdictColor(value)}>{evaluationCaseVerdictLabel(value)}</Tag>
    },
    {
      title: 'Finding',
      dataIndex: 'itemSnapshot',
      width: 260,
      ellipsis: true,
      render: (value, row) => value?.title || row.findingId || row.fingerprint || '-'
    },
    { title: '人工说明', dataIndex: 'humanComment', ellipsis: true, render: value => value || '-' },
    { title: '创建时间', dataIndex: 'createdAt', width: 180, render: value => value || '-' }
  ];

  return (
    <div className="page-shell">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-title-row">
          <div>
            <Title level={3}>评估样本</Title>
            <Text type="secondary">查看从 AI finding 或人工补充沉淀的 Review 质量评估样本。</Text>
          </div>
        </div>
        <Card>
          <Space wrap className="task-filter-bar">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="filter-select"
              placeholder="项目"
              value={filters.projectId || undefined}
              options={projectOptions}
              onChange={value => updateFilter('projectId', value)}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Provider"
              value={filters.provider}
              onChange={event => updateFilter('provider', event.target.value)}
              onPressEnter={() => load({ pageNo: 1 })}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Profile"
              value={filters.profile}
              onChange={event => updateFilter('profile', event.target.value)}
              onPressEnter={() => load({ pageNo: 1 })}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="风险类型"
              value={filters.riskType}
              onChange={event => updateFilter('riskType', event.target.value)}
              onPressEnter={() => load({ pageNo: 1 })}
            />
            <Select
              allowClear
              className="filter-select"
              placeholder="人工裁决"
              value={filters.verdict || undefined}
              options={EVALUATION_CASE_VERDICT_OPTIONS}
              onChange={value => updateFilter('verdict', value)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => load({ pageNo: 1 })}>搜索</Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Card>
        {error && <Alert type="error" showIcon message={error} />}
        <Card>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            tableLayout="fixed"
            scroll={{ x: 1920 }}
            pagination={{
              current: pagination.pageNo,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showTotal: total => `共 ${total} 条`,
              onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
            }}
          />
        </Card>
      </Space>
    </div>
  );
}

function EvaluationRunsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [items, setItems] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [filters, setFilters] = useState({
    projectId: null,
    provider: '',
    profile: '',
    runType: null,
    status: null
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const projectOptions = useMemo(
    () => projects.map(project => ({ label: project.name, value: project.id })),
    [projects]
  );

  const loadProjects = async () => {
    try {
      const data = await fetchApi('/api/projects?includeDisabled=true');
      setProjects(data.items || []);
    } catch {
      setProjects([]);
    }
  };

  const load = async ({ pageNo = pagination.pageNo, pageSize = pagination.pageSize, nextFilters = filters } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('pageNo', String(pageNo));
      params.set('pageSize', String(pageSize));
      if (nextFilters.projectId) params.set('projectId', String(nextFilters.projectId));
      if (nextFilters.provider?.trim()) params.set('provider', nextFilters.provider.trim());
      if (nextFilters.profile?.trim()) params.set('profile', nextFilters.profile.trim());
      if (nextFilters.runType) params.set('runType', nextFilters.runType);
      if (nextFilters.status) params.set('status', nextFilters.status);
      const data = await fetchApi(`/api/evaluation-runs?${params.toString()}`);
      setItems(data.items || []);
      setPagination({ pageNo: data.pageNo || pageNo, pageSize: data.pageSize || pageSize, total: data.total || 0 });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    load({ pageNo: 1 });
  }, []);

  const updateFilter = (field, value) => {
    setFilters(current => ({
      ...current,
      [field]: value === undefined ? null : value
    }));
  };

  const resetFilters = () => {
    const nextFilters = {
      projectId: null,
      provider: '',
      profile: '',
      runType: null,
      status: null
    };
    setFilters(nextFilters);
    load({ pageNo: 1, nextFilters });
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '名称',
      dataIndex: 'name',
      width: 240,
      ellipsis: true,
      render: (value, row) => (
        <Button type="link" onClick={() => navigate(`${EVALUATION_RUNS_ROUTE}/${row.id}`, { state: { from: route } })}>
          {value || `Run #${row.id}`}
        </Button>
      )
    },
    { title: '类型', dataIndex: 'runType', width: 120, render: value => <Tag>{evaluationRunTypeLabel(value)}</Tag> },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={evaluationRunStatusColor(value)}>{evaluationRunStatusLabel(value)}</Tag> },
    { title: '样本集', dataIndex: 'sampleSetName', width: 180, ellipsis: true, render: value => value || '-' },
    { title: '样本数', dataIndex: 'totalCount', width: 90, render: value => value ?? 0 },
    { title: '完成', dataIndex: 'completedCount', width: 90, render: value => value ?? 0 },
    { title: '失败', dataIndex: 'failedCount', width: 90, render: value => value ?? 0 },
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    { title: 'Provider', dataIndex: 'provider', width: 120, ellipsis: true, render: value => value || '-' },
    { title: 'Profile', dataIndex: 'profile', width: 190, ellipsis: true, render: value => value || '-' },
    { title: 'Model', dataIndex: 'model', width: 160, ellipsis: true, render: value => value || '-' },
    { title: 'Prompt Hash', dataIndex: 'promptHash', width: 140, render: value => <Text code>{compactHash(value)}</Text> },
    { title: 'Baseline', dataIndex: 'baseline', width: 150, ellipsis: true, render: value => value?.label || value?.promptHash || '-' },
    { title: 'Candidate', dataIndex: 'candidate', width: 150, ellipsis: true, render: value => value?.label || value?.promptHash || '-' },
    { title: '耗时', dataIndex: 'durationMs', width: 100, render: value => value == null ? '-' : `${value} ms` },
    { title: '创建时间', dataIndex: 'createdAt', width: 180, render: value => value || '-' }
  ];

  return (
    <div className="page-shell">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-title-row">
          <div>
            <Title level={3}>回放记录</Title>
            <Text type="secondary">查看 evaluation run / review replay run 的版本记录和样本结果摘要。</Text>
          </div>
        </div>
        <Card>
          <Space wrap className="task-filter-bar">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="filter-select"
              placeholder="项目"
              value={filters.projectId || undefined}
              options={projectOptions}
              onChange={value => updateFilter('projectId', value)}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Provider"
              value={filters.provider}
              onChange={event => updateFilter('provider', event.target.value)}
              onPressEnter={() => load({ pageNo: 1 })}
            />
            <Input
              allowClear
              className="filter-input"
              placeholder="Profile"
              value={filters.profile}
              onChange={event => updateFilter('profile', event.target.value)}
              onPressEnter={() => load({ pageNo: 1 })}
            />
            <Select
              allowClear
              className="filter-select"
              placeholder="类型"
              value={filters.runType || undefined}
              options={EVALUATION_RUN_TYPE_OPTIONS}
              onChange={value => updateFilter('runType', value)}
            />
            <Select
              allowClear
              className="filter-select"
              placeholder="状态"
              value={filters.status || undefined}
              options={EVALUATION_RUN_STATUS_OPTIONS}
              onChange={value => updateFilter('status', value)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => load({ pageNo: 1 })}>搜索</Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Card>
        {error && <Alert type="error" showIcon message={error} />}
        <Card>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            tableLayout="fixed"
            scroll={{ x: 2260 }}
            pagination={{
              current: pagination.pageNo,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showTotal: total => `共 ${total} 条`,
              onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
            }}
          />
        </Card>
      </Space>
    </div>
  );
}

function EvaluationRunDetailPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const backTarget = resolveBackTarget(location, EVALUATION_RUNS_ROUTE);
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchApi(`/api/evaluation-runs/${runId}`);
      setRun(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [runId]);

  const columns = [
    { title: '#', dataIndex: 'itemIndex', width: 70, render: value => Number(value ?? 0) + 1 },
    { title: 'Case ID', dataIndex: 'caseId', width: 100 },
    {
      title: '任务',
      dataIndex: 'taskId',
      width: 100,
      render: value => value ? (
        <Button type="link" onClick={() => navigate(`/tasks/${value}`, { state: { from: currentRoute(location) } })}>
          #{value}
        </Button>
      ) : '-'
    },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={evaluationRunStatusColor(value)}>{evaluationRunStatusLabel(value)}</Tag> },
    { title: '裁决', dataIndex: 'verdict', width: 130, render: value => <Tag color={evaluationCaseVerdictColor(value)}>{evaluationCaseVerdictLabel(value)}</Tag> },
    { title: '风险类型', dataIndex: 'riskType', width: 130, render: value => value ? <Tag color="blue">{categoryLabel(value)}</Tag> : '-' },
    { title: '等级', dataIndex: 'severity', width: 100, render: value => value ? <Tag color={severityColor(value)}>{severityLabel(value)}</Tag> : '-' },
    { title: '上下文', dataIndex: 'contextStatus', width: 110, render: value => value ? <Tag color={contextStatusColor(value)}>{contextStatusLabel(value)}</Tag> : '-' },
    { title: 'Provider', dataIndex: 'provider', width: 120, ellipsis: true, render: value => value || '-' },
    { title: 'Profile', dataIndex: 'profile', width: 190, ellipsis: true, render: value => value || '-' },
    { title: 'Review Key', dataIndex: 'reviewKey', width: 150, ellipsis: true, render: value => value || '-' },
    { title: '耗时', dataIndex: 'durationMs', width: 100, render: value => value == null ? '-' : `${value} ms` },
    { title: 'Baseline', dataIndex: 'baselineSummary', width: 220, render: value => value ? <JsonBlock value={value} /> : '-' },
    { title: 'Candidate', dataIndex: 'candidateSummary', width: 220, render: value => value ? <JsonBlock value={value} /> : '-' },
    { title: '结果摘要', dataIndex: 'resultSummary', width: 240, render: value => value ? <JsonBlock value={value} /> : '-' },
    { title: '错误', dataIndex: 'errorMessage', width: 180, ellipsis: true, render: value => value || '-' }
  ];

  return (
    <div className="page-shell">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-title-row">
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(backTarget)}>返回</Button>
            <div>
              <Title level={3}>回放详情</Title>
              <Text type="secondary">Run #{runId}</Text>
            </div>
          </Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </div>
        {error && <Alert type="error" showIcon message={error} />}
        <Spin spinning={loading}>
          {run ? (
            <Space direction="vertical" size="large" className="full-width">
              <Card>
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item label="名称">{run.name || '-'}</Descriptions.Item>
                  <Descriptions.Item label="状态"><Tag color={evaluationRunStatusColor(run.status)}>{evaluationRunStatusLabel(run.status)}</Tag></Descriptions.Item>
                  <Descriptions.Item label="类型">{evaluationRunTypeLabel(run.runType)}</Descriptions.Item>
                  <Descriptions.Item label="样本集">{run.sampleSetName || '-'}</Descriptions.Item>
                  <Descriptions.Item label="项目">{run.projectName || run.projectId || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Provider">{run.provider || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Profile">{run.profile || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Model">{run.model || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Prompt Hash"><Text code>{compactHash(run.promptHash)}</Text></Descriptions.Item>
                  <Descriptions.Item label="Context Pack">{run.contextPackVersion || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Retriever">{run.retrieverVersion || '-'}</Descriptions.Item>
                  <Descriptions.Item label="规则缺口版本">{run.ruleGapVersion || '-'}</Descriptions.Item>
                  <Descriptions.Item label="样本数">{run.totalCount ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="完成 / 失败">{run.completedCount ?? 0} / {run.failedCount ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="耗时">{run.durationMs == null ? '-' : `${run.durationMs} ms`}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{run.createdAt || '-'}</Descriptions.Item>
                  <Descriptions.Item label="说明" span={2}>{run.notes || '-'}</Descriptions.Item>
                </Descriptions>
              </Card>
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={8}>
                  <Card title="Sample Set">
                    <JsonBlock value={run.sampleSet || {}} />
                  </Card>
                </Col>
                <Col xs={24} lg={8}>
                  <Card title="Baseline">
                    <JsonBlock value={run.baseline || {}} />
                  </Card>
                </Col>
                <Col xs={24} lg={8}>
                  <Card title="Candidate">
                    <JsonBlock value={run.candidate || {}} />
                  </Card>
                </Col>
              </Row>
              <Card title="结果摘要">
                <JsonBlock value={run.resultSummary || {}} />
              </Card>
              <Card title="样本结果">
                <Table
                  rowKey="id"
                  columns={columns}
                  dataSource={run.items || []}
                  tableLayout="fixed"
                  scroll={{ x: 2360 }}
                  pagination={false}
                />
              </Card>
            </Space>
          ) : (
            !loading && <Empty description="暂无回放记录" />
          )}
        </Spin>
      </Space>
    </div>
  );
}

function HomePage() {
  const location = useLocation();
  const legacyTaskId = new URLSearchParams(location.search).get('taskId');

  if (legacyTaskId) {
    return <Navigate to={`/tasks/${legacyTaskId}`} replace />;
  }

  return <TaskListPage />;
}

function AppFrame() {
  const location = useLocation();
  const navigate = useNavigate();
  const route = currentRoute(location);
  const isTaskRoute = location.pathname === HOME_ROUTE || location.pathname.startsWith(TASK_LIST_ROUTE);
  const isRuleGapRoute = location.pathname.startsWith(RULE_GAPS_ROUTE);
  const isFeedbackRoute = location.pathname.startsWith(FEEDBACK_ROUTE);
  const isReviewQualityRoute = location.pathname.startsWith(REVIEW_QUALITY_ROUTE);
  const isEvaluationCasesRoute = location.pathname.startsWith(EVALUATION_CASES_ROUTE);
  const isEvaluationRunsRoute = location.pathname.startsWith(EVALUATION_RUNS_ROUTE);
  const isSettingsRoute = location.pathname.startsWith(SETTINGS_ROUTE);
  const isReleaseRoute = location.pathname.startsWith(RELEASES_ROUTE);
  const isHelpRoute = location.pathname.startsWith(HELP_ROUTE);
  const [jobQueue, setJobQueue] = useState({ activeCount: 0, groups: [] });
  const [jobQueueOpen, setJobQueueOpen] = useState(false);
  const [failureNotifications, setFailureNotifications] = useState({ failureCount: 0, items: [] });
  const [failureNotificationsOpen, setFailureNotificationsOpen] = useState(false);

  const loadJobQueue = async () => {
    try {
      const data = await fetchApi('/api/code-quality-reviews/job-queue');
      setJobQueue(data || { activeCount: 0, groups: [] });
    } catch {
      setJobQueue({ activeCount: 0, groups: [] });
    }
  };

  const loadFailureNotifications = async () => {
    try {
      const data = await fetchApi('/api/code-quality-reviews/failure-notifications');
      setFailureNotifications(data || { failureCount: 0, items: [] });
    } catch {
      setFailureNotifications({ failureCount: 0, items: [] });
    }
  };

  const openTaskFromQueue = (taskId) => {
    if (!taskId) return;
    setJobQueueOpen(false);
    setFailureNotificationsOpen(false);
    navigate(`/tasks/${taskId}`, { state: { from: route } });
  };

  const cancelJobFromQueue = async job => {
    if (!job?.id) return;
    try {
      await fetchApi(`/api/code-quality-reviews/job-queue/${job.id}/cancel`, { method: 'POST' });
      message.success('调度任务已中断');
      loadJobQueue();
    } catch (err) {
      message.error(err.message);
    }
  };

  useEffect(() => {
    loadJobQueue();
    loadFailureNotifications();
  }, []);

  useEffect(() => {
    const refreshIfVisible = () => {
      if (document.visibilityState === 'visible') {
        loadJobQueue();
        loadFailureNotifications();
      }
    };
    const timer = window.setInterval(refreshIfVisible, 5000);
    window.addEventListener(JOB_QUEUE_REFRESH_EVENT, loadJobQueue);
    window.addEventListener(FAILURE_NOTIFICATION_REFRESH_EVENT, loadFailureNotifications);
    document.addEventListener('visibilitychange', refreshIfVisible);
    window.addEventListener('focus', refreshIfVisible);
    refreshIfVisible();
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(JOB_QUEUE_REFRESH_EVENT, loadJobQueue);
      window.removeEventListener(FAILURE_NOTIFICATION_REFRESH_EVENT, loadFailureNotifications);
      document.removeEventListener('visibilitychange', refreshIfVisible);
      window.removeEventListener('focus', refreshIfVisible);
    };
  }, []);

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <button className="brand" type="button" onClick={() => navigate(TASK_LIST_ROUTE)}>
          AI代码质量审查平台
        </button>
        <Space className="top-nav">
          <Button
            icon={<UnorderedListOutlined />}
            type={isTaskRoute ? 'primary' : 'default'}
            onClick={() => navigate(TASK_LIST_ROUTE)}
          >
            任务
          </Button>
          <Button
            icon={<FileSearchOutlined />}
            type={isRuleGapRoute ? 'primary' : 'default'}
            onClick={() => navigate(RULE_GAPS_ROUTE, { state: { from: route } })}
          >
            规则缺口
          </Button>
          {REVIEW_LEARNING_UI_ENABLED && (
            <Button
              icon={<CommentOutlined />}
              type={isFeedbackRoute ? 'primary' : 'default'}
              onClick={() => navigate(FEEDBACK_ROUTE, { state: { from: route } })}
            >
              反馈池
            </Button>
          )}
          <Button
            icon={<ClusterOutlined />}
            type={isReviewQualityRoute ? 'primary' : 'default'}
            onClick={() => navigate(REVIEW_QUALITY_ROUTE, { state: { from: route } })}
          >
            质量看板
          </Button>
          <Button
            icon={<CommentOutlined />}
            type={isEvaluationCasesRoute ? 'primary' : 'default'}
            onClick={() => navigate(EVALUATION_CASES_ROUTE, { state: { from: route } })}
          >
            评估样本
          </Button>
          <Button
            icon={<ClusterOutlined />}
            type={isEvaluationRunsRoute ? 'primary' : 'default'}
            onClick={() => navigate(EVALUATION_RUNS_ROUTE, { state: { from: route } })}
          >
            回放记录
          </Button>
          <Button
            icon={<SettingOutlined />}
            type={isSettingsRoute ? 'primary' : 'default'}
            onClick={() => navigate(SETTINGS_ROUTE, { state: { from: route } })}
          >
            设置
          </Button>
          <Button
            icon={<ClockCircleOutlined />}
            type={isReleaseRoute ? 'primary' : 'default'}
            onClick={() => navigate(RELEASES_ROUTE, { state: { from: route } })}
          >
            版本更新
          </Button>
          <Button
            icon={<QuestionCircleOutlined />}
            type={isHelpRoute ? 'primary' : 'default'}
            onClick={() => navigate(HELP_ROUTE, { state: { from: route } })}
          >
            接入帮助
          </Button>
        </Space>
        <div className="header-actions">
          <Tooltip title="AI Review 失败通知">
            <Button
              danger={Boolean(failureNotifications?.failureCount)}
              icon={<BellOutlined />}
              type={failureNotifications?.failureCount ? 'primary' : 'default'}
              onClick={() => {
                setFailureNotificationsOpen(true);
                loadFailureNotifications();
              }}
            />
          </Tooltip>
          <Tooltip title="AI Review 调度队列">
            <Badge count={jobQueue?.activeCount || 0} size="small">
              <Button
                icon={<ClusterOutlined />}
                type={jobQueue?.activeCount ? 'primary' : 'default'}
                onClick={() => {
                  setJobQueueOpen(true);
                  loadJobQueue();
                }}
              />
            </Badge>
          </Tooltip>
        </div>
      </Header>
      <Content>
        <Routes>
          <Route path={HOME_ROUTE} element={<HomePage />} />
          <Route path={TASK_LIST_ROUTE} element={<TaskListPage />} />
          <Route path={`${TASK_LIST_ROUTE}/:taskId`} element={<TaskDetailPage />} />
          <Route path={RULE_GAPS_ROUTE} element={<RuleGapDashboardPage />} />
          <Route
            path={FEEDBACK_ROUTE}
            element={REVIEW_LEARNING_UI_ENABLED ? <RiskFeedbackPage /> : <Navigate to={TASK_LIST_ROUTE} replace />}
          />
          <Route path={REVIEW_QUALITY_ROUTE} element={<ReviewQualityDashboardPage />} />
          <Route path={EVALUATION_CASES_ROUTE} element={<EvaluationCasesPage />} />
          <Route path={EVALUATION_RUNS_ROUTE} element={<EvaluationRunsPage />} />
          <Route path={`${EVALUATION_RUNS_ROUTE}/:runId`} element={<EvaluationRunDetailPage />} />
          <Route path={SETTINGS_ROUTE} element={<SettingsPage />} />
          <Route path={RELEASES_ROUTE} element={<ReleaseNotesPage />} />
          <Route path={HELP_ROUTE} element={<HelpPage />} />
          <Route path="*" element={<Navigate to={HOME_ROUTE} replace />} />
        </Routes>
      </Content>
      <JobQueueModal
        open={jobQueueOpen}
        queue={jobQueue}
        onClose={() => setJobQueueOpen(false)}
        onOpenTask={openTaskFromQueue}
        onCancelJob={cancelJobFromQueue}
      />
      <FailureNotificationsModal
        open={failureNotificationsOpen}
        notifications={failureNotifications}
        onClose={() => setFailureNotificationsOpen(false)}
        onOpenTask={openTaskFromQueue}
      />
    </Layout>
  );
}

export default function App() {
  return <AppFrame />;
}
