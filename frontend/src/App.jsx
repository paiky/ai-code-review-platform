import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react';
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
  Drawer,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  Layout,
  Menu,
  message,
  Modal,
  Popover,
  Progress,
  Row,
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
  ApiOutlined,
  ApartmentOutlined,
  ArrowLeftOutlined,
  BellOutlined,
  BranchesOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  ClusterOutlined,
  CommentOutlined,
  ControlOutlined,
  CopyOutlined,
  DashboardOutlined,
  ExportOutlined,
  EyeOutlined,
  FileTextOutlined,
  FileSearchOutlined,
  GlobalOutlined,
  KeyOutlined,
  LoadingOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
  MoonOutlined,
  QuestionCircleOutlined,
  SunOutlined,
  TeamOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import MuiAlert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import MuiButton from '@mui/material/Button';
import MuiCard from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import MuiSelect from '@mui/material/Select';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import MuiTypography from '@mui/material/Typography';
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
import { AppFrameOperationsContext } from './appFrameOperations.js';
import {
  buildAppShellNavigation,
  readSidebarCollapsedPreference,
  resolveAppShellOpenKeys,
  resolveAppShellSelectedKey,
  resolveAppShellViewport,
  writeSidebarCollapsedPreference
} from './appShell.js';
import CommandCenterPage from './command-center/CommandCenterPage.jsx';
import { createVisibilityRefreshLifecycle } from './visibilityRefreshLifecycle.js';
import {
  formatAgentTraceDetail,
  groupAgentTraceEvents,
  isAgentHeartbeatProgressEvent,
  isAgentTraceProgressEvent,
  summarizeAgentTrace
} from './agentReviewTrace.js';
import {
  buildReviewJourney,
  buildReviewJourneys,
  resolveReviewSelectionKey,
  selectReviewJourneyEvents
} from './reviewJourney.js';
import {
  buildReviewHeroModel,
  buildStageAlertModel,
  isReviewJourneyDismissKey,
  isReviewStageActivationKey,
  resolveOpenReviewJourneyStage,
  reviewTimelineMode,
  shouldAnimateReview,
  visibleReviewJourneyStages
} from './reviewJourneyPresentation.js';
import {
  buildReviewImmersivePresentation,
  normalizeReviewWorkspaceMode,
  resolveReviewWorkspaceFrame
} from './reviewImmersivePresentation.js';
import ReviewImmersiveCanvas from './ReviewImmersiveCanvas.jsx';
import {
  agentBudgetLimits,
  bytesToKilobytes,
  formatAgentBudgetSummary,
  kilobytesToBytes,
  normalizeAgentBudgets,
  validateAgentBudgets
} from './agentReviewBudgets.js';
import {
  normalizeAgentQueueMetrics,
  normalizeAgentWorkerPool
} from './agentWorkerPool.js';
import {
  agentConfigurationTestPollTimeoutMs,
  buildAgentSettingsPayload,
  customAgentRuntime,
  normalizeAgentRuntimeDraft,
  selectedRuntimeSettings,
  validateAgentRuntimeDraft
} from './agentReviewRuntime.js';
import { releaseNotes } from './releaseNotes.js';

const { Header, Content, Sider } = Layout;
const { Title, Text, Paragraph } = Typography;

const ReviewWorkspaceModeContext = createContext({
  mode: 'RESULT',
  reportMode: () => {}
});

function useReviewWorkspaceMode() {
  return useContext(ReviewWorkspaceModeContext);
}

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
const ACCEPTANCE_GATES_ROUTE = '/acceptance-gates';
const EVALUATION_CASES_ROUTE = '/evaluation-cases';
const EVALUATION_RUNS_ROUTE = '/evaluation-runs';
const SETTINGS_ROUTE = '/settings';
const RELEASES_ROUTE = '/releases';
const HELP_ROUTE = '/help';
const REVIEW_LEARNING_UI_ENABLED = String(import.meta.env.VITE_REVIEW_LEARNING_UI_ENABLED || '').toLowerCase() === 'true';
const PROJECT_REVIEW_POLICY_UI_ENABLED = REVIEW_LEARNING_UI_ENABLED
  && String(import.meta.env.VITE_PROJECT_REVIEW_POLICY_UI_ENABLED || '').toLowerCase() === 'true';
const TASK_DETAIL_AUTO_IMMERSIVE_ENTRY_ENABLED = false;
const QUALITY_GOVERNANCE_NAV_VISIBLE = false;
const EVALUATION_CASE_ACTION_VISIBLE = false;
const FINDING_REFINEMENT_ACTION_VISIBLE = false;
const STANDARD_REVIEW_COMPARISON_ACTION_VISIBLE = false;
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
const ACCEPTANCE_GATE_CHANGE_TYPE_OPTIONS = [
  { label: '规则', value: 'RULE' },
  { label: 'Retriever', value: 'RETRIEVER' },
  { label: 'Prompt', value: 'PROMPT' },
  { label: 'Context Pack', value: 'CONTEXT_PACK' },
  { label: '确定性检查', value: 'DETERMINISTIC_CHECK' },
  { label: 'Provider', value: 'PROVIDER' },
  { label: '其他', value: 'OTHER' }
];
const ACCEPTANCE_GATE_STATUS_OPTIONS = [
  { label: '草稿', value: 'DRAFT' },
  { label: '已准入', value: 'ADMITTED' },
  { label: '验证中', value: 'RUNNING_VALIDATION' },
  { label: '通过', value: 'PASSED' },
  { label: '失败', value: 'FAILED' },
  { label: '已取消', value: 'CANCELED' }
];
const ACCEPTANCE_GATE_RESULT_STATUS_OPTIONS = [
  { label: '有改善', value: 'IMPROVED' },
  { label: '中性', value: 'NEUTRAL' },
  { label: '退化', value: 'REGRESSED' },
  { label: '不确定', value: 'INCONCLUSIVE' }
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
  reviewEngine: 'AGENT',
  agentSourceExportAllowed: true,
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
const RULE_GAP_ATTRIBUTION_OPTIONS = [
  { label: '规则缺口导致', value: 'RULE_GAP_CAUSED' },
  { label: '规则缺口相关', value: 'RULE_GAP_RELATED' },
  { label: '非规则缺口', value: 'NOT_RULE_GAP' },
  { label: 'Prompt 问题', value: 'PROMPT_ISSUE' },
  { label: '模型推理问题', value: 'MODEL_REASONING_ISSUE' },
  { label: '缺少项目策略', value: 'PROJECT_POLICY_MISSING' },
  { label: '标签信息不足', value: 'INSUFFICIENT_LABEL' }
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
    reviewEngine: 'AGENT',
    agentSourceExportAllowed: true,
    aiReviewEnabled: true,
    triggerOnManual: true,
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

function ruleGapAttributionLabel(value) {
  return RULE_GAP_ATTRIBUTION_OPTIONS.find(item => item.value === value)?.label || value || '未归因';
}

function ruleGapAttributionColor(value) {
  if (value === 'RULE_GAP_CAUSED') return 'red';
  if (value === 'RULE_GAP_RELATED') return 'orange';
  if (value === 'NOT_RULE_GAP') return 'green';
  if (value === 'INSUFFICIENT_LABEL') return 'default';
  return value ? 'blue' : 'default';
}

function recommendationBasisLabel(value) {
  if (value === 'PROVEN_BY_EVALUATION_CASES') return '样本证明';
  if (value === 'MIXED') return '样本 + 高频';
  if (value === 'FREQUENCY_ONLY') return '高频观察';
  return value || '-';
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

function acceptanceGateChangeTypeLabel(value) {
  return ACCEPTANCE_GATE_CHANGE_TYPE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function acceptanceGateStatusLabel(value) {
  return ACCEPTANCE_GATE_STATUS_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function acceptanceGateStatusColor(value) {
  switch (value) {
    case 'PASSED':
      return 'green';
    case 'FAILED':
      return 'red';
    case 'RUNNING_VALIDATION':
      return 'processing';
    case 'ADMITTED':
      return 'blue';
    case 'CANCELED':
      return 'default';
    case 'DRAFT':
      return 'gold';
    default:
      return 'default';
  }
}

function acceptanceGateResultStatusLabel(value) {
  return ACCEPTANCE_GATE_RESULT_STATUS_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function acceptanceGateResultStatusColor(value) {
  switch (value) {
    case 'IMPROVED':
      return 'green';
    case 'REGRESSED':
      return 'red';
    case 'NEUTRAL':
      return 'blue';
    case 'INCONCLUSIVE':
      return 'gold';
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
    { title: '排队时间', dataIndex: 'queuedAt', width: 190, render: formatDateTime },
    { title: '开始时间', dataIndex: 'startedAt', width: 190, render: formatDateTime },
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
    { title: '排队时间', dataIndex: 'queuedAt', width: 190, render: formatDateTime },
    { title: '开始时间', dataIndex: 'startedAt', width: 190, render: formatDateTime },
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
    { title: '失败时间', dataIndex: 'createdAt', width: 190, render: formatDateTime },
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

function TaskWorkspaceShell({ title, description, actions, children, leading }) {
  return (
    <Box
      sx={{
        px: { xs: 2, md: 3 },
        py: { xs: 2, md: 2.5 },
        minHeight: 'calc(100dvh - 56px)',
        backgroundColor: '#f6f8fb'
      }}
    >
      <Stack spacing={2.5}>
        {(title || description || actions || leading) && <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
          <Stack
            direction={{ xs: 'column', lg: 'row' }}
            spacing={2}
            sx={{ justifyContent: 'space-between', alignItems: { xs: 'stretch', lg: 'center' } }}
          >
            <Box sx={{ minWidth: 0, flex: '1 1 auto', maxWidth: 900 }}>
              {leading && (
                <Box sx={{ mb: 0.75 }}>
                  {leading}
                </Box>
              )}
              <MuiTypography variant="h5" component="h1" sx={{ fontWeight: 750, mb: description ? 0.75 : 0, color: '#1f2933' }}>
                {title}
              </MuiTypography>
              {description && (
                <MuiTypography variant="body2" sx={{ color: '#5f6b76' }}>
                  {description}
                </MuiTypography>
              )}
            </Box>
            {actions && (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                useFlexGap
                sx={{
                  flex: '0 0 auto',
                  width: { xs: '100%', lg: 'auto' },
                  ml: { lg: 'auto' },
                  flexWrap: 'wrap',
                  justifyContent: 'flex-end',
                  alignItems: { xs: 'stretch', sm: 'center' },
                  '& .MuiButton-root': { minHeight: 36, height: 36, px: 1.75, flex: '0 0 auto' }
                }}
              >
                {actions}
              </Stack>
            )}
          </Stack>
        </Paper>}
        {children}
      </Stack>
    </Box>
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
    { title: '创建时间', dataIndex: 'createdAt', width: 190, ellipsis: true, render: formatDateTime },
    { title: '操作', width: 70, render: (_, row) => <Button type="link" onClick={() => onOpen(row.id)}>详情</Button> }
  ];

  return (
    <TaskWorkspaceShell>
      <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
        <Space wrap className="task-filter-bar">
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
      </Paper>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={tasks}
          tableLayout="fixed"
          scroll={{ x: 1250 }}
          pagination={{
            current: pagination.pageNo,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showTotal: total => `共 ${total} 条`,
            onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
          }}
        />
      </Paper>
    </TaskWorkspaceShell>
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
    AGENT_SENSITIVE_PATHS_EXCLUDED: '已排除敏感路径',
    AGENT_ALL_PATHS_EXCLUDED: '全部路径已安全跳过',
    AGENT_RECLAIMED: 'Agent 重新领取',
    AGENT_ANALYZING: 'Agent 分析变更',
    AGENT_TOOL_ACTIVITY: 'Agent 补充证据',
    AGENT_CONVERGING: 'Agent 收敛结论',
    AGENT_SUBMITTING: 'Agent 提交结果',
    AGENT_HEARTBEAT: 'Agent 运行心跳',
    AGENT_FINISHED: 'Agent 审查完成',
    AGENT_FALLBACK: 'Agent 失败降级',
    AGENT_CANCELLED: 'Agent 审查取消',
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
  'AGENT_RECLAIMED',
  'AGENT_ANALYZING',
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING',
  'AGENT_FINISHED',
  'AGENT_FALLBACK',
  'AGENT_CANCELLED',
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
    case 'AGENT_SENSITIVE_PATHS_EXCLUDED':
      return '敏感文件及其 diff 未发送给 Agent，其余文件继续使用高准确模式审查。';
    case 'AGENT_ALL_PATHS_EXCLUDED':
      return '全部变更文件均命中敏感路径策略，本次未向外部模型发送代码。';
    case 'AGENT_RECLAIMED':
      return '上一 Worker 的任务租约已经过期，本次由可用 Worker 重新领取。';
    case 'AGENT_ANALYZING':
      return 'Agent 正在基于 changedFiles 和 diff 形成有限风险假设。';
    case 'AGENT_TOOL_ACTIVITY':
      return 'Agent 正在围绕已有风险假设补充受控只读证据。';
    case 'AGENT_CONVERGING':
      return 'Agent 已停止扩大检索范围，正在收敛 Review 结论。';
    case 'AGENT_SUBMITTING':
      return 'Agent 正在提交结构化 Review Card。';
    case 'AGENT_FINISHED':
      return 'Agent 已成功提交 Review Card，并保存正式审查结果。';
    case 'AGENT_FALLBACK':
      return 'Agent 未能提交有效结果，任务已进入普通 Review 降级流程。';
    case 'AGENT_CANCELLED':
      return 'Agent Review 已由用户取消。';
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
  if (isAgentTraceProgressEvent(event)) {
    return formatAgentTraceDetail(event.detail, event.phase);
  }
  return event.detail;
}

function parseEventTime(value) {
  if (!value) return null;
  const normalized = String(value).includes('T') ? value : String(value).replace(' ', 'T');
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized);
  const timestamp = new Date(hasExplicitTimezone ? normalized : `${normalized}Z`).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

const EAST_EIGHT_TIME_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
});

function formatDateTime(value) {
  const timestamp = parseEventTime(value);
  if (timestamp == null) return '-';
  const parts = Object.fromEntries(
    EAST_EIGHT_TIME_FORMATTER.formatToParts(new Date(timestamp))
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value])
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} UTC+8`;
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

function agentReviewCoverage(progress, agentRunSummary) {
  const events = Array.isArray(progress) ? progress : [];
  const event = latestProgressEvent(events, [
    'AGENT_ALL_PATHS_EXCLUDED',
    'AGENT_SENSITIVE_PATHS_EXCLUDED',
    'AGENT_QUEUED'
  ]);
  const detail = parseProgressDetailJson(event?.detail) || agentRunSummary || {};
  const excludedFileCount = Number(detail.excludedFileCount || 0);
  if (!Number.isFinite(excludedFileCount) || excludedFileCount <= 0) return null;
  return {
    totalChangedFileCount: Number(detail.totalChangedFileCount || 0),
    includedFileCount: Number(detail.includedFileCount || 0),
    excludedFileCount,
    excludedPaths: Array.isArray(detail.excludedPaths) ? detail.excludedPaths : []
  };
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

function boolText(value) {
  if (value === true) return '是';
  if (value === false) return '否';
  return '-';
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
  const sourceWorkspaceSummary = {
    ...(summary.sourceWorkspaceSummary || {}),
    ...((summary.localRepository || {}).sourceWorkspaceSummary || {}),
    ...(repoDetail.sourceWorkspaceSummary || {}),
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
    plannerTargetType: summary.plannerTargetType || 'GENERAL',
    detectedLanguages: safeArray(summary.detectedLanguages),
    extractorVersions: safeArray(summary.extractorVersions),
    plannerCoverageSummary: summary.plannerCoverageSummary || {},
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
    sourceWorkspaceSummary,
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
  const workspace = summary.sourceWorkspaceSummary || {};
  const mirror = workspace.mirror || {};
  const worktree = workspace.worktree || {};
  const cleanupPolicy = workspace.cleanupPolicy || {};
  const cleanup = workspace.cleanup || {};
  const showWorkspaceDiagnostics = summary.hasRecord && Object.keys(workspace).length > 0;

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
          <Descriptions.Item label="Planner 端类型">
            <Tag>{summary.plannerTargetType || 'GENERAL'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="检测语言">
            {(summary.detectedLanguages || []).join('、') || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="覆盖模式">
            <Tag color={summary.plannerCoverageSummary?.coverageMode === 'GENERIC_FALLBACK' ? 'orange' : 'blue'}>
              {summary.plannerCoverageSummary?.coverageMode || '-'}
            </Tag>
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
        {showWorkspaceDiagnostics && (
          <>
            <Divider plain>源码工作区诊断</Divider>
            <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
              <Descriptions.Item label="工作区模式">{workspace.mode || '-'}</Descriptions.Item>
              <Descriptions.Item label="远程仓库">{workspace.remoteUrl || '-'}</Descriptions.Item>
              <Descriptions.Item label="失败阶段">{workspace.failurePhase || summary.localRepository?.failurePhase || '-'}</Descriptions.Item>
              <Descriptions.Item label="Mirror 存在">{boolText(mirror.exists)}</Descriptions.Item>
              <Descriptions.Item label="Mirror 状态">{mirror.status || summary.localRepository?.mirrorStatus || '-'}</Descriptions.Item>
              <Descriptions.Item label="Mirror 最近拉取">{formatDateTime(mirror.lastFetchedAt)}</Descriptions.Item>
              <Descriptions.Item label="Worktree 存在">{boolText(worktree.exists)}</Descriptions.Item>
              <Descriptions.Item label="Worktree 状态">{worktree.status || summary.localRepository?.worktreeStatus || '-'}</Descriptions.Item>
              <Descriptions.Item label="Worktree 最近检出">{formatDateTime(worktree.lastCheckedOutAt)}</Descriptions.Item>
              <Descriptions.Item label="清理策略">
                {cleanupPolicy.enabled === false
                  ? '未启用'
                  : `worktree ${countText(cleanupPolicy.worktreeRetentionHours)}h / mirror ${countText(cleanupPolicy.mirrorRetentionDays)}d`}
              </Descriptions.Item>
              <Descriptions.Item label="最近清理">
                {cleanup.status || '-'}
                {cleanup.deletedWorktreeCount || cleanup.deletedMirrorCount
                  ? `，删除 worktree ${countText(cleanup.deletedWorktreeCount)} / mirror ${countText(cleanup.deletedMirrorCount)}`
                  : ''}
              </Descriptions.Item>
              <Descriptions.Item label="清理异常">{countText(cleanup.errorCount)}</Descriptions.Item>
            </Descriptions>
          </>
        )}
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
  if (!summary.enabled && summary.hasRecord) {
    return '引用查询数为 0：LOCAL_REPO_CONTEXT_ENABLED 未开启，本次保持 diff-only 或同文件上下文。';
  }
  if (summary.enabled && repositoryStatus !== 'PREPARED') {
    const failurePhase = summary.sourceWorkspaceSummary?.failurePhase || summary.localRepository?.failurePhase;
    return `引用查询数为 0：本地仓库未准备完成${failurePhase ? `（${failurePhase}）` : ''}，Retriever 被跳过。`;
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
        summary.plannerTargetType,
        summary.plannerCoverageSummary?.coverageMode,
      ]),
    },
    {
      title: '本地仓库',
      status: roleStepStatus({ hasEvent: Boolean(summary.repoEvent || summary.hasRecord), failed: repoFailed }),
      description: roleDetailLine([
        localRepositoryStatusLabel(summary.status, summary.hasRecord),
        (summary.sourceWorkspaceSummary?.mirror?.status || summary.localRepository?.mirrorStatus) && `mirror ${summary.sourceWorkspaceSummary?.mirror?.status || summary.localRepository?.mirrorStatus}`,
        (summary.sourceWorkspaceSummary?.worktree?.status || summary.localRepository?.worktreeStatus) && `worktree ${summary.sourceWorkspaceSummary?.worktree?.status || summary.localRepository?.worktreeStatus}`,
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
  const requestedEngine = String(review?.requestedEngine || 'STANDARD').toUpperCase();
  const effectiveEngine = String(review?.effectiveEngine || requestedEngine).toUpperCase();
  const agentRunSummary = review?.agentRunSummary || null;
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
      {requestedEngine === 'AGENT' && (
        <Card title="Agent Review 流转">
          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
            <Descriptions.Item label="请求引擎">{requestedEngine}</Descriptions.Item>
            <Descriptions.Item label="实际引擎">
              <Tag color={effectiveEngine === 'AGENT' ? 'purple' : 'orange'}>{effectiveEngine}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Run ID">{agentRunSummary?.runId ?? review?.agentRunId ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="运行状态">{agentRunSummary?.status || review?.status || '-'}</Descriptions.Item>
            <Descriptions.Item label="Agent turns">{agentRunSummary?.turnCount ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="工具调用">{agentRunSummary?.toolCallCount ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="源码返回">{agentRunSummary?.sourceBytesReturned == null ? '-' : `${agentRunSummary.sourceBytesReturned} bytes`}</Descriptions.Item>
            <Descriptions.Item label="Diff 返回">{agentRunSummary?.diffBytesReturned == null ? '-' : `${agentRunSummary.diffBytesReturned} bytes`}</Descriptions.Item>
            <Descriptions.Item label="耗时">{agentRunSummary?.durationMs == null ? '-' : formatDuration(agentRunSummary.durationMs / 1000)}</Descriptions.Item>
            <Descriptions.Item label="降级原因">{agentRunSummary?.failureCode || '-'}</Descriptions.Item>
            <Descriptions.Item label="生效预算" span={4}>
              {formatAgentBudgetSummary(agentRunSummary?.effectiveBudgets) || '-'}
            </Descriptions.Item>
          </Descriptions>
          {effectiveEngine === 'STANDARD_FALLBACK' && (
            <Alert
              className="top-gap"
              type="warning"
              showIcon
              message="Agent Review 已显式降级为普通 Review"
              description={agentRunSummary?.failureMessage || agentRunSummary?.failureCode || 'Agent Worker 或执行链路不可用'}
            />
          )}
        </Card>
      )}
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
              <Descriptions.Item label="端类型 / 覆盖模式">
                {summary.plannerTargetType || 'GENERAL'} / {summary.plannerCoverageSummary?.coverageMode || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="检测语言">
                {(summary.detectedLanguages || []).join('、') || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="提取器版本">
                {(summary.extractorVersions || []).join('、') || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="暂不支持语言">
                {countItemsText((summary.plannerCoverageSummary?.unsupportedLanguageCounts || []).map((item) => ({
                  type: item.language,
                  count: item.count,
                })))}
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
        <Text type="secondary">{formatDateTime(event.createdAt)}</Text>
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
          <Descriptions.Item label="开始时间">{formatDateTime(overlay.startedAt)}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{formatDateTime(overlay.finishedAt)}</Descriptions.Item>
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

function AgentTraceOverview({ summary }) {
  if (!summary) return null;
  const budgets = summary.effectiveBudgets || {};
  const budgetPhase = summary.reviewBudget?.phase || '';
  const phaseReason = summary.phase === 'AGENT_FINISHED'
    ? 'Review Card 已成功提交并保存。'
    : summary.phase === 'AGENT_FALLBACK'
      ? 'Agent 未能提交有效结果，已进入普通 Review 降级。'
      : summary.phase === 'AGENT_CANCELLED'
        ? 'Agent Review 已取消。'
        : budgetPhase === 'SUBMIT' || summary.phase === 'AGENT_SUBMITTING'
          ? '证据收集已经结束，当前只允许提交 Review Card。'
          : budgetPhase === 'CONVERGE' || summary.phase === 'AGENT_CONVERGING'
            ? '已达到收敛起点，不再扩大风险假设或检索范围。'
            : '仍处于有限取证阶段，只围绕既有风险假设补充证据。';
  const metrics = [
    {
      key: 'turns',
      label: '模型回合',
      used: summary.turnCount,
      limit: budgets.maxTurns,
      unavailable: !summary.terminal
    },
    {
      key: 'tools',
      label: '工具调用',
      used: summary.toolCallCount,
      limit: budgets.maxToolCalls
    },
    {
      key: 'evidence',
      label: '证据调用',
      used: summary.evidenceCallsUsed,
      limit: budgets.maxEvidenceCalls
    },
    {
      key: 'source',
      label: '源码返回',
      used: summary.sourceBytesReturned,
      limit: budgets.maxSourceBytes,
      bytes: true
    }
  ];

  return (
    <div className="agent-trace-overview">
      <div className="agent-trace-overview-head">
        <Space wrap>
          <Text strong>Run #{summary.runId}</Text>
          {summary.claimAttempt > 1 && (
            <Tag color="orange">第 {summary.claimAttempt} 次领取</Tag>
          )}
          <Tag color={summary.terminal ? 'default' : 'processing'}>
            {budgetPhase || phaseLabel(summary.phase)}
          </Tag>
        </Space>
        <Text type="secondary">
          最近心跳：{summary.lastHeartbeatAt ? formatDateTime(summary.lastHeartbeatAt) : '历史任务未记录'}
        </Text>
      </div>
      <Text type="secondary">{phaseReason}</Text>
      <div className="agent-trace-budget-grid">
        {metrics.map(metric => {
          const used = Number(metric.used ?? 0);
          const limit = Number(metric.limit ?? 0);
          const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
          const valueText = metric.unavailable
            ? `完成后可见 / ${limit || '-'}`
            : metric.bytes
              ? `${Math.round(used / 1000)} / ${limit ? Math.round(limit / 1000) : '-'} KB`
              : `${used} / ${limit || '-'}`;
          return (
            <div className="agent-trace-budget-item" key={metric.key}>
              <div>
                <Text type="secondary">{metric.label}</Text>
                <Text strong>{valueText}</Text>
              </div>
              {!metric.unavailable && limit > 0 && (
                <Progress percent={percent} showInfo={false} size="small" />
              )}
            </div>
          );
        })}
      </div>
      {summary.progressMayBeDelayed && (
        <Alert
          type="warning"
          showIcon
          message="Agent 进度数据可能延迟"
          description="超过 45 秒未收到 Worker 心跳；这不等同于模型卡死，页面会继续等待后端终态。"
        />
      )}
    </div>
  );
}

function CodeQualityProgressView({ progress, running = false, reviewStartedAt, reviewFinishedAt }) {
  const events = Array.isArray(progress) ? progress : [];
  const reviewEvents = events.filter(event => !isFixPreviewProgressEvent(event));
  const agentEvents = groupAgentTraceEvents(reviewEvents);
  const regularEvents = reviewEvents.filter(
    event => !isAgentTraceProgressEvent(event) && !isAgentHeartbeatProgressEvent(event)
  );
  const keyEvents = regularEvents.filter(isKeyProgressEvent);
  const debugEvents = regularEvents.filter(isDebugProgressEvent);
  const hiddenEvents = regularEvents.filter(event => !isKeyProgressEvent(event) && !isDebugProgressEvent(event));
  const startedAt = parseEventTime(reviewStartedAt);
  const finishedAt = parseEventTime(reviewFinishedAt);
  const totalDurationText = startedAt && finishedAt
    ? formatDuration(Math.max(0, (finishedAt - startedAt) / 1000))
    : formatDuration(totalProgressDuration(reviewEvents));
  const fallbackStartedAtRef = useRef(Date.now());
  const [elapsedTick, setElapsedTick] = useState(Date.now());
  const agentSummary = summarizeAgentTrace(reviewEvents, elapsedTick);
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
              <Tag color="processing">{phaseLabel(agentSummary?.phase || latestEvent?.phase)}</Tag>
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
          {agentEvents.length > 0 && (
            <div>
              <Title level={5}>Agent 执行轨迹</Title>
              <AgentTraceOverview summary={agentSummary} />
              <Timeline
                items={agentEvents.map(event => ({
                  key: event.id,
                  color: progressColor(event.level),
                  children: <ProgressEventView event={event} showStepDescription />
                }))}
              />
            </div>
          )}
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
            <Descriptions.Item label="审核时间">{formatDateTime(gate.createdAt)}</Descriptions.Item>
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

const agentReviewAnimationRegistry = Object.freeze({
  BRAIN: BrainReviewAnimation
});

function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ));
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener?.('change', update);
    return () => media.removeEventListener?.('change', update);
  }, []);
  return reducedMotion;
}

function reviewHeroStateMark(state) {
  if (state === 'SUCCESS') return '✓';
  if (state === 'FALLBACK') return '→';
  if (state === 'FAILED') return '!';
  if (state === 'CANCELLED') return '×';
  if (state === 'SKIPPED') return '–';
  return '•';
}

function BrainReviewAnimation({ state, reducedMotion, ariaLabel }) {
  const animated = shouldAnimateReview({ state, reducedMotion });
  return (
    <div
      className={`review-animation review-brain-animation review-animation-${String(state || 'history').toLowerCase()}${animated ? ' is-animated' : ' is-static'}`}
      role="img"
      aria-label={ariaLabel}
    >
      <svg viewBox="0 0 220 160" aria-hidden="true" focusable="false">
        <circle className="review-brain-orbit" cx="100" cy="80" r="66" />
        <path
          className="review-brain-outline"
          d="M99 41c-9-11-28-8-32 6-12-2-23 9-20 22-10 7-9 25 2 31-2 14 12 26 25 21 7 11 24 9 29-2"
        />
        <path
          className="review-brain-outline"
          d="M101 41c9-11 28-8 32 6 12-2 23 9 20 22 10 7 9 25-2 31 2 14-12 26-25 21-7 11-24 9-29-2"
        />
        <path className="review-brain-link" d="M64 66 88 78 67 97M136 63l-23 18 23 18M88 78l26 3M82 112l18-16 19 18" />
        <circle className="review-brain-node node-one" cx="64" cy="66" r="4" />
        <circle className="review-brain-node node-two" cx="88" cy="78" r="4" />
        <circle className="review-brain-node node-three" cx="67" cy="97" r="4" />
        <circle className="review-brain-node node-four" cx="114" cy="81" r="4" />
        <circle className="review-brain-node node-five" cx="136" cy="63" r="4" />
        <circle className="review-brain-node node-six" cx="136" cy="99" r="4" />
        <circle className="review-brain-node node-seven" cx="82" cy="112" r="4" />
        <circle className="review-brain-node node-eight" cx="119" cy="114" r="4" />
        <path className="review-brain-transfer" d="M158 80h34m-10-10 10 10-10 10" />
      </svg>
      <span className="review-animation-state-mark" aria-hidden="true">
        {reviewHeroStateMark(state)}
      </span>
    </div>
  );
}

function AgentReviewAnimation({
  style = 'BRAIN',
  state,
  subStage,
  reducedMotion,
  ariaLabel
}) {
  const Animation = agentReviewAnimationRegistry[style] || agentReviewAnimationRegistry.BRAIN;
  return (
    <Animation
      state={state}
      subStage={subStage}
      reducedMotion={reducedMotion}
      ariaLabel={ariaLabel}
    />
  );
}

function StandardReviewAnimation({ state, reducedMotion, ariaLabel }) {
  const animated = shouldAnimateReview({ state, reducedMotion });
  return (
    <div
      className={`review-animation review-provider-animation review-animation-${String(state || 'history').toLowerCase()}${animated ? ' is-animated' : ' is-static'}`}
      role="img"
      aria-label={ariaLabel}
    >
      <div className="review-provider-node" aria-hidden="true">P</div>
      <div className="review-provider-flow" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <div className="review-provider-result" aria-hidden="true">
        {reviewHeroStateMark(state)}
      </div>
    </div>
  );
}

function ReviewStatusHero({ journey }) {
  const reducedMotion = usePrefersReducedMotion();
  const hero = buildReviewHeroModel(journey);
  const currentStage = journey?.stages?.find(stage => stage.id === journey.currentStageId);
  return (
    <section
      className={`review-status-hero review-status-hero-${hero.kind.toLowerCase()} review-status-${hero.state.toLowerCase()}`}
      aria-labelledby={`review-hero-title-${journey?.selectorKey || 'history'}`}
    >
      <div className="review-status-visual">
        {hero.kind === 'BRAIN' ? (
          <AgentReviewAnimation
            style={hero.style}
            state={hero.state}
            subStage={journey?.agentSummary?.phase || null}
            reducedMotion={reducedMotion}
            ariaLabel={hero.ariaLabel}
          />
        ) : (
          <StandardReviewAnimation
            state={hero.state}
            reducedMotion={reducedMotion}
            ariaLabel={hero.ariaLabel}
          />
        )}
      </div>
      <div className="review-status-copy">
        <div className="review-status-kicker">
          <Tag color={reviewJourneyEngineColor(journey?.engineKind)}>{hero.identity}</Tag>
          <Tag color={reviewJourneyStatusColor(journey?.status)}>{journey?.statusLabel}</Tag>
          {currentStage && <Tag>{currentStage.title}</Tag>}
        </div>
        <Title level={3} id={`review-hero-title-${journey?.selectorKey || 'history'}`}>
          {hero.title}
        </Title>
        <Paragraph>{hero.description}</Paragraph>
        <Tooltip title={hero.provider}>
          <Text type="secondary" className="review-status-provider">{hero.provider}</Text>
        </Tooltip>
        {journey?.agentSummary?.lastHeartbeatAt && (
          <Text type="secondary">
            最近心跳：{formatDateTime(journey.agentSummary.lastHeartbeatAt)}
          </Text>
        )}
        {journey?.agentSummary?.progressMayBeDelayed && (
          <Alert
            type="warning"
            showIcon
            message="Agent 进度数据可能延迟"
            description="超过 45 秒未收到安全心跳；这不等同于 Agent 卡死。"
          />
        )}
      </div>
    </section>
  );
}

function reviewJourneyStageStatusLabel(status) {
  const labels = {
    WAITING: '等待中',
    ACTIVE: '执行中',
    SUCCESS: '已完成',
    WARNING: '有警告',
    FAILED: '失败',
    SKIPPED: '已跳过',
    CANCELLED: '已取消'
  };
  return labels[status] || '历史任务未记录';
}

function reviewJourneyStageStatusColor(status) {
  if (status === 'ACTIVE') return 'processing';
  if (status === 'SUCCESS') return 'green';
  if (status === 'WARNING') return 'orange';
  if (status === 'FAILED') return 'red';
  if (status === 'SKIPPED') return 'gold';
  return 'default';
}

function formatJourneyDuration(durationMs) {
  if (durationMs === null || durationMs === undefined || durationMs === '') return '-';
  const value = Number(durationMs);
  return Number.isFinite(value) && value >= 0 ? formatDuration(value / 1000) : '-';
}

function safeProgressLevelLabel(level) {
  if (level === 'ERROR') return '错误';
  if (level === 'WARN' || level === 'WARNING') return '警告';
  if (level === 'DEBUG') return '调试';
  return '记录';
}

function safeReviewErrorCode(value) {
  const code = String(value || '').trim().toUpperCase();
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(code) ? code : null;
}

function StageAlertPopoverContent({ stage }) {
  const alert = buildStageAlertModel(stage);
  if (!alert) return null;
  return (
    <div className="review-stage-alert-content">
      <Text strong>{alert.title}</Text>
      <Text>{alert.reason}</Text>
      <Text type="secondary">建议：{alert.action}</Text>
    </div>
  );
}

function contextRepositoryStatusLabel(status) {
  const labels = {
    PREPARED: '已准备',
    WORKTREE_MISSING: '工作区不可用',
    UNAVAILABLE: '不可用',
    DISABLED: '未启用',
    FAILED: '不可用'
  };
  return labels[status] || '历史任务未记录';
}

function contextRetrieverStatusLabel(status) {
  const labels = {
    COMPLETED: '已完成',
    SUCCESS: '已完成',
    UNAVAILABLE: '不可用',
    FAILED: '不可用',
    SKIPPED: '已跳过',
    DISABLED: '未启用'
  };
  return labels[status] || '历史任务未记录';
}

function safeCountTags(items, emptyText = '历史任务未记录') {
  const source = Array.isArray(items) ? items : [];
  if (source.length === 0) return <Text type="secondary">{emptyText}</Text>;
  return (
    <Space size={4} wrap>
      {source.map(item => (
        <Tag key={item.type}>{item.type} · {item.count}</Tag>
      ))}
    </Space>
  );
}

function ContextStageDrawerDetails({ details }) {
  const navigate = useNavigate();
  const location = useLocation();
  if (!details?.hasReliableRecord) return null;
  const contextPack = details.contextPack || {};
  const repository = details.repository || {};
  const planner = details.planner || {};
  const retriever = details.retriever || {};
  const requestedContext = details.requestedContext || {};
  const budgetCuts = details.budgetCuts || {};
  const refinement = details.refinement || {};
  const ruleGaps = details.ruleGaps || {};
  return (
    <Space orientation="vertical" size="large" className="full-width review-stage-domain-details">
      {details.detailState !== 'AVAILABLE' && (
        <Alert
          type="warning"
          showIcon
          title={details.detailState === 'PARTIAL' ? '部分详情不可用' : '详情不可用'}
          description="仅保留可由阶段事件可靠确认的固定状态；未补造上下文、时间或执行结果。"
        />
      )}
      <section>
        <Title level={5}>Context Pack 摘要</Title>
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="构建记录">
            {contextPack.built ? <Tag color="green">已记录</Tag> : <Tag>历史任务未记录</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="预算状态">
            {contextPack.truncated === null
              ? '历史任务未记录'
              : contextPack.truncated
                ? <Tag color="orange">发生裁剪</Tag>
                : <Tag>未裁剪</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="变更文件">{countText(contextPack.changedFileCount)}</Descriptions.Item>
        </Descriptions>
      </section>
      <section>
        <Title level={5}>本地仓库与 Planner / Retriever</Title>
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="本地仓库">
            <Tag color={repository.status === 'PREPARED' ? 'green' : repository.status ? 'orange' : 'default'}>
              {contextRepositoryStatusLabel(repository.status)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="本地能力">
            {repository.enabled === null ? '历史任务未记录' : repository.enabled ? '已启用' : '未启用'}
          </Descriptions.Item>
          <Descriptions.Item label="Planner 端类型">{planner.targetType || '历史任务未记录'}</Descriptions.Item>
          <Descriptions.Item label="检测语言">
            {(planner.detectedLanguages || []).join('、') || '历史任务未记录'}
          </Descriptions.Item>
          <Descriptions.Item label="Planner Signal">{countText(planner.signalCount)}</Descriptions.Item>
          <Descriptions.Item label="Retriever">
            <Tag color={retriever.status === 'COMPLETED' || retriever.status === 'SUCCESS' ? 'green' : retriever.status ? 'orange' : 'default'}>
              {contextRetrieverStatusLabel(retriever.status)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="检索请求">{countText(retriever.requestCount)}</Descriptions.Item>
          <Descriptions.Item label="命中文件">{countText(retriever.matchedFileCount)}</Descriptions.Item>
          <Descriptions.Item label="注入片段">{countText(retriever.includedSnippetCount)}</Descriptions.Item>
          <Descriptions.Item label="Signal 类型" span={{ xs: 1, md: 2 }}>
            {safeCountTags(planner.signalTypeCounts)}
          </Descriptions.Item>
          <Descriptions.Item label="暂不支持 Signal" span={{ xs: 1, md: 2 }}>
            {safeCountTags(planner.unsupportedSignalTypeCounts, '无可靠缺口记录')}
          </Descriptions.Item>
        </Descriptions>
      </section>
      <section>
        <Title level={5}>Requested Context 可用性</Title>
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="可用">{countText(requestedContext.available)}</Descriptions.Item>
          <Descriptions.Item label="不可用">{countText(requestedContext.unavailable)}</Descriptions.Item>
        </Descriptions>
        {(requestedContext.items || []).length > 0 && (
          <div className="review-stage-safe-list">
            {requestedContext.items.map(item => (
              <div className="review-stage-safe-row" key={item.type}>
                <Text strong>{item.type}</Text>
                <Space size={4} wrap>
                  <Tag color={item.available ? 'green' : 'orange'}>
                    {item.available ? '可用' : '不可用'}
                  </Tag>
                  {item.signalCount !== null && <Tag>Signal {item.signalCount}</Tag>}
                  {item.priority && <Tag>{item.priority}</Tag>}
                  {item.reasonCode && <Tag>{item.reasonCode}</Tag>}
                </Space>
              </div>
            ))}
          </div>
        )}
      </section>
      <section>
        <Title level={5}>预算裁剪和未注入证据</Title>
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="裁剪状态">
            {budgetCuts.truncated === null
              ? '历史任务未记录'
              : budgetCuts.truncated
                ? <Tag color="orange">发生裁剪</Tag>
                : <Tag>未裁剪</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="变更文件排除">{countText(budgetCuts.changedFilesExcluded)}</Descriptions.Item>
          <Descriptions.Item label="同文件片段裁剪">{countText(budgetCuts.sameFileSourceSnippetsRemoved)}</Descriptions.Item>
          <Descriptions.Item label="引用片段裁剪">{countText(budgetCuts.localReferenceSnippetsRemoved)}</Descriptions.Item>
          <Descriptions.Item label="未注入证据">{countText(budgetCuts.notInjectedEvidenceCount)}</Descriptions.Item>
          <Descriptions.Item label="涉及命中文件">{countText(budgetCuts.matchedFileCount)}</Descriptions.Item>
          <Descriptions.Item label="裁剪片段合计">{countText(budgetCuts.cutSnippetCount)}</Descriptions.Item>
          <Descriptions.Item label="受保护 Signal" span={{ xs: 1, md: 2 }}>
            {(budgetCuts.protectedSignalTypes || []).join('、') || '历史任务未记录'}
          </Descriptions.Item>
        </Descriptions>
      </section>
      <section>
        <Title level={5}>Finding 级补证据摘要</Title>
        <Descriptions size="small" column={{ xs: 1, md: 3 }}>
          <Descriptions.Item label="记录">{countText(refinement.total)}</Descriptions.Item>
          <Descriptions.Item label="完成">{countText(refinement.completed)}</Descriptions.Item>
          <Descriptions.Item label="失败">{countText(refinement.failed)}</Descriptions.Item>
        </Descriptions>
        <Text type="secondary">具体补证据结果与操作继续位于对应 Finding 内，不覆盖原 Review 结果。</Text>
      </section>
      <section>
        <div className="review-stage-section-heading">
          <div>
            <Title level={5}>规则缺口诊断</Title>
            <Text type="secondary">当前安全缺口计数 {countText(ruleGaps.total)}</Text>
          </div>
          <Button
            size="small"
            icon={<FileSearchOutlined />}
            onClick={() => navigate(RULE_GAPS_ROUTE, { state: { from: currentRoute(location) } })}
          >
            打开规则缺口诊断
          </Button>
        </div>
        {safeCountTags(ruleGaps.typeCounts, '本次未记录规则缺口类型')}
      </section>
    </Space>
  );
}

function PreflightStageDrawerDetails({ details, running, onRun }) {
  const auto = details?.auto || null;
  const taskLatest = details?.taskLatest || null;
  return (
    <Space orientation="vertical" size="large" className="full-width review-stage-domain-details">
      <section>
        <Title level={5}>当前 Review · AUTO_PREFLIGHT</Title>
        {!auto ? (
          <Alert
            type="info"
            showIcon
            title="当前 Review 未记录 AUTO_PREFLIGHT"
            description="不会使用任务级手动记录补造当前 Review 的阶段、时间、耗时或执行结果。"
          />
        ) : (
          <Space orientation="vertical" size="middle" className="full-width">
            <Space wrap>
              <Tag color={deterministicCheckStatusColor(auto.status)}>
                {deterministicCheckStatusText(auto.status)}
              </Tag>
              {auto.shared && <Tag color="blue">本次调度共享</Tag>}
              {auto.reused && <Tag color="geekblue">当前 reviewKey 复用</Tag>}
              {auto.failOpen && <Tag color="orange">fail-open</Tag>}
            </Space>
            <Descriptions size="small" column={{ xs: 1, md: 2 }}>
              <Descriptions.Item label="检查类型">{auto.checkType || '历史任务未记录'}</Descriptions.Item>
              <Descriptions.Item label="触发方式">{auto.trigger || '历史任务未记录'}</Descriptions.Item>
              <Descriptions.Item label="输入新鲜度">{auto.freshness || '历史任务未记录'}</Descriptions.Item>
              <Descriptions.Item label="Run">{auto.runId == null ? '历史任务未记录' : `#${auto.runId}`}</Descriptions.Item>
              <Descriptions.Item label="扫描文件">{countText(auto.scannedFileCount)}</Descriptions.Item>
              <Descriptions.Item label="新增行">{countText(auto.addedLineCount)}</Descriptions.Item>
              <Descriptions.Item label="命中">{countText(auto.findingCount)}</Descriptions.Item>
              <Descriptions.Item label="耗时">{formatJourneyDuration(auto.durationMs)}</Descriptions.Item>
            </Descriptions>
            {auto.detailState !== 'AVAILABLE' && (
              <Text type="secondary">{auto.detailState === 'PARTIAL' ? '部分详情不可用' : '详情不可用'}</Text>
            )}
            {auto.failOpen && (
              <Alert
                type="warning"
                showIcon
                title="确定性预检不可用，Review 已按 fail-open 继续"
                description="该记录不会改写 Review 主状态，也不会被解释为未发现风险。"
              />
            )}
          </Space>
        )}
      </section>
      <section>
        <div className="review-stage-section-heading">
          <div>
            <Title level={5}>任务级最新确定性检查</Title>
            <Text type="secondary">独立任务记录，不改写任何已完成 Review 的 AUTO_PREFLIGHT 阶段。</Text>
          </div>
          <Button icon={<ReloadOutlined />} loading={running} onClick={onRun}>
            {taskLatest ? '重新运行敏感信息扫描' : '运行敏感信息扫描'}
          </Button>
        </div>
        {!taskLatest ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前任务暂无手动或自动检查记录" />
        ) : (
          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label="状态">
              <Tag color={deterministicCheckStatusColor(taskLatest.status)}>
                {deterministicCheckStatusText(taskLatest.status)}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="检查类型">{taskLatest.checkType || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="记录来源">{taskLatest.trigger || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="输入新鲜度">{taskLatest.freshness || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="扫描范围">{taskLatest.scope || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="扫描文件">{countText(taskLatest.scannedFileCount)}</Descriptions.Item>
            <Descriptions.Item label="新增行">{countText(taskLatest.addedLineCount)}</Descriptions.Item>
            <Descriptions.Item label="命中">{countText(taskLatest.findingCount)}</Descriptions.Item>
            <Descriptions.Item label="耗时">{formatJourneyDuration(taskLatest.durationMs)}</Descriptions.Item>
            <Descriptions.Item label="完成时间">{formatDateTime(taskLatest.finishedAt)}</Descriptions.Item>
            <Descriptions.Item label="规则命中摘要" span={{ xs: 1, md: 2 }}>
              {safeCountTags(taskLatest.ruleTypeCounts, '无命中或历史任务未记录')}
            </Descriptions.Item>
          </Descriptions>
        )}
      </section>
    </Space>
  );
}

function ReviewStageDrawerContent({
  journey,
  stage,
  taskCheckRunning,
  onRunTaskCheck
}) {
  const advancedEvents = (Array.isArray(stage?.events) ? stage.events : [])
    .filter(event => !event.auxiliary);
  const hasReviewStageRecord = stage.visible !== false;
  return (
    <Space orientation="vertical" size="large" className="full-width review-stage-drawer-content">
      <Descriptions size="small" column={{ xs: 1, md: 2 }}>
        <Descriptions.Item label="阶段状态">
          <Tag color={hasReviewStageRecord ? reviewJourneyStageStatusColor(stage.status) : 'default'}>
            {hasReviewStageRecord ? reviewJourneyStageStatusLabel(stage.status) : '历史任务未记录'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Review">{journey?.engineLabel || '历史任务未记录'}</Descriptions.Item>
        <Descriptions.Item label="开始时间">{formatDateTime(stage.startedAt)}</Descriptions.Item>
        <Descriptions.Item label="结束时间">{formatDateTime(stage.finishedAt)}</Descriptions.Item>
        <Descriptions.Item label="真实耗时">{formatJourneyDuration(stage.durationMs)}</Descriptions.Item>
      </Descriptions>
      <Alert
        type={hasReviewStageRecord && stage.status === 'FAILED' ? 'error' : hasReviewStageRecord && stage.status === 'WARNING' ? 'warning' : 'info'}
        showIcon
        message={hasReviewStageRecord ? stage.summary : '当前 Review 未记录确定性预检阶段'}
        description={
          !hasReviewStageRecord
            ? '任务级检查操作独立保留，不会补造当前 Review 的阶段、时间、耗时或执行结果。'
            : stage.status === 'FAILED' || stage.status === 'WARNING'
            ? stage.warningSummary
            : '仅展示当前接口中可可靠验证的安全阶段记录。'
        }
      />
      {journey?.engineKind === 'FALLBACK' && stage.id === 'terminal' && (
        <div className="review-fallback-transfer" aria-label="Agent 向 Standard fallback 显式转交">
          <span>Agent</span>
          <strong aria-hidden="true">→</strong>
          <span>Standard fallback</span>
        </div>
      )}
      {stage.subStages.length > 0 && (
        <section>
          <Title level={5}>Agent 子阶段</Title>
          <div className="review-agent-substages">
            {stage.subStages.map(item => (
              <div className={`review-agent-substage is-${item.status.toLowerCase()}`} key={item.id}>
                <span>{item.title}</span>
                <Tag color={reviewJourneyStageStatusColor(item.status)}>
                  {reviewJourneyStageStatusLabel(item.status)}
                </Tag>
              </div>
            ))}
          </div>
        </section>
      )}
      {stage.safeMetrics.length > 0 && (
        <section>
          <Title level={5}>安全摘要</Title>
          <div className="review-stage-metrics">
            {stage.safeMetrics.map(metric => (
              <div className="review-stage-metric" key={metric.label}>
                <Text type="secondary">{metric.label}</Text>
                <Text strong>{metric.label === '最近心跳' ? formatDateTime(metric.value) : metric.value}</Text>
              </div>
            ))}
          </div>
        </section>
      )}
      {stage.id === 'context' && (
        <ContextStageDrawerDetails details={stage.details?.context} />
      )}
      {stage.id === 'preflight' && (
        <PreflightStageDrawerDetails
          details={stage.details?.preflight}
          running={taskCheckRunning}
          onRun={onRunTaskCheck}
        />
      )}
      <Collapse
        className="review-stage-advanced"
        items={[{
          key: 'advanced',
          label: `高级执行记录 (${advancedEvents.length})`,
          children: advancedEvents.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可安全展示的高级执行记录" />
          ) : (
            <div className="review-stage-event-list">
              {advancedEvents.map((event, index) => (
                <div className="review-stage-event" key={`${event.id ?? 'event'}-${index}`}>
                  <div>
                    <Text strong>{event.safeLabel}</Text>
                    <Space size={4} wrap>
                      <Tag>{safeProgressLevelLabel(event.level)}</Tag>
                      {event.shared && <Tag color="blue">本次调度共享</Tag>}
                    </Space>
                  </div>
                  <Text type="secondary">{formatDateTime(event.createdAt)}</Text>
                  <Text>{event.detailAvailable ? event.safeSummary : '详情不可用'}</Text>
                </div>
              ))}
            </div>
          )
        }]}
      />
    </Space>
  );
}

function OtherReviewJourneyEvents({ events }) {
  const source = Array.isArray(events) ? events : [];
  if (source.length === 0) return null;
  return (
    <Collapse
      className="review-other-events"
      items={[{
        key: 'other-events',
        label: `其它执行记录 (${source.length})`,
        children: (
          <div className="review-stage-event-list">
            {source.map((event, index) => (
              <div className="review-stage-event" key={`${event.id ?? 'other'}-${index}`}>
                <div>
                  <Text strong>{event.safeLabel}</Text>
                  <Tag>{safeProgressLevelLabel(event.level)}</Tag>
                </div>
                <Text type="secondary">{formatDateTime(event.createdAt)}</Text>
                <Text>{event.safeSummary}</Text>
              </div>
            ))}
          </div>
        )
      }]}
    />
  );
}

function ReviewJourneyTimeline({
  journey,
  taskCheckRunning,
  onRunTaskCheck,
  variant = 'default'
}) {
  const mode = reviewTimelineMode(journey);
  const stages = visibleReviewJourneyStages(journey);
  const [openStageId, setOpenStageId] = useState(null);
  const [allowHiddenPreflight, setAllowHiddenPreflight] = useState(false);
  const [openAlertStageId, setOpenAlertStageId] = useState(null);
  const stageButtonRefs = useRef(new Map());
  const focusReturnStageIdRef = useRef(null);
  const journeyKeyRef = useRef(journey?.selectorKey);
  const openStage = allowHiddenPreflight && openStageId === 'preflight'
    ? journey?.stages?.find(stage => stage.id === 'preflight') || null
    : resolveOpenReviewJourneyStage(journey, openStageId);
  const stageSignature = stages.map(stage => stage.id).join('\u001f');

  const closeDrawer = () => {
    setOpenStageId(null);
    setAllowHiddenPreflight(false);
  };
  const openDrawer = stageId => {
    setOpenAlertStageId(null);
    setAllowHiddenPreflight(false);
    focusReturnStageIdRef.current = stageId;
    setOpenStageId(stageId);
  };
  const openTaskPreflightDrawer = () => {
    setOpenAlertStageId(null);
    setAllowHiddenPreflight(true);
    focusReturnStageIdRef.current = 'task-preflight';
    setOpenStageId('preflight');
  };
  useEffect(() => {
    if (journeyKeyRef.current !== journey?.selectorKey) {
      journeyKeyRef.current = journey?.selectorKey;
      setOpenStageId(null);
      setAllowHiddenPreflight(false);
      setOpenAlertStageId(null);
      focusReturnStageIdRef.current = null;
      return;
    }
    if (
      openStageId
      && !allowHiddenPreflight
      && !resolveOpenReviewJourneyStage(journey, openStageId)
    ) {
      setOpenStageId(null);
      focusReturnStageIdRef.current = null;
    }
    if (
      openAlertStageId
      && !stages.some(stage => stage.id === openAlertStageId)
    ) {
      setOpenAlertStageId(null);
    }
  }, [
    journey?.selectorKey,
    openStageId,
    allowHiddenPreflight,
    openAlertStageId,
    stageSignature
  ]);
  useEffect(() => {
    if (!openStageId && !openAlertStageId) return undefined;
    const dismiss = event => {
      if (!isReviewJourneyDismissKey(event.key)) return;
      if (openAlertStageId) {
        setOpenAlertStageId(null);
        return;
      }
      closeDrawer();
    };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [openStageId, openAlertStageId]);

  return (
    <section className={`review-journey-timeline review-journey-${mode.toLowerCase()} review-journey-${variant}`}>
      <div className="review-journey-heading">
        <div>
          <Text strong>{mode === 'FULL' ? '统一 Review 进度' : 'Review 阶段回顾'}</Text>
          <Text type="secondary">
            {stages.length === 0
              ? '历史任务未记录可可靠回看的阶段'
              : mode === 'FULL'
                ? '点击阶段查看当前安全详情'
                : '结果优先展示，阶段仍可点击回看'}
          </Text>
        </div>
        <div className="review-journey-heading-actions">
          <Tag>{mode === 'FULL' ? '完整时间轴' : '紧凑时间轴'}</Tag>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            ref={node => {
              if (node) stageButtonRefs.current.set('task-preflight', node);
              else stageButtonRefs.current.delete('task-preflight');
            }}
            onClick={openTaskPreflightDrawer}
          >
            任务级确定性检查
          </Button>
        </div>
      </div>
      {stages.length > 0 && (
        <ol className="review-journey-stages" aria-label="Review 六阶段进度">
          {stages.map((stage, index) => {
            const alert = buildStageAlertModel(stage);
            return (
              <li className={`review-journey-stage is-${stage.status.toLowerCase()}`} key={stage.id}>
                <button
                  type="button"
                  className="review-journey-stage-trigger"
                  ref={node => {
                    if (node) stageButtonRefs.current.set(stage.id, node);
                    else stageButtonRefs.current.delete(stage.id);
                  }}
                  aria-current={stage.status === 'ACTIVE' ? 'step' : undefined}
                  aria-label={`${stage.title}，${reviewJourneyStageStatusLabel(stage.status)}`}
                  onClick={() => openDrawer(stage.id)}
                  onKeyDown={event => {
                    if (!isReviewStageActivationKey(event.key)) return;
                    event.preventDefault();
                    openDrawer(stage.id);
                  }}
                >
                  <span className="review-journey-stage-index" aria-hidden="true">{index + 1}</span>
                  <span className="review-journey-stage-copy">
                    <strong>{stage.title}</strong>
                    <small>{reviewJourneyStageStatusLabel(stage.status)}</small>
                  </span>
                </button>
                {alert && (
                  <Popover
                    trigger="click"
                    open={openAlertStageId === stage.id}
                    onOpenChange={open => setOpenAlertStageId(open ? stage.id : null)}
                    content={<StageAlertPopoverContent stage={stage} />}
                    placement="bottom"
                  >
                    <button
                      type="button"
                      className="review-stage-alert-trigger"
                      aria-label={`查看${stage.title}告警摘要`}
                      aria-expanded={openAlertStageId === stage.id}
                      onClick={event => event.stopPropagation()}
                    >
                      !
                    </button>
                  </Popover>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <OtherReviewJourneyEvents events={journey?.otherEvents} />
      <Drawer
        className="review-stage-drawer"
        rootClassName="review-stage-drawer-root"
        title={openStage?.title || '阶段详情'}
        size="min(880px, 100vw)"
        open={Boolean(openStage)}
        keyboard
        onClose={closeDrawer}
        afterOpenChange={open => {
          if (open) return;
          const stageId = focusReturnStageIdRef.current;
          focusReturnStageIdRef.current = null;
          window.requestAnimationFrame(() => stageButtonRefs.current.get(stageId)?.focus());
        }}
      >
        {openStage && (
          <ReviewStageDrawerContent
            journey={journey}
            stage={openStage}
            taskCheckRunning={taskCheckRunning}
            onRunTaskCheck={onRunTaskCheck}
          />
        )}
      </Drawer>
    </section>
  );
}

function ReviewJourneyExperience({ journey, taskCheckRunning, onRunTaskCheck }) {
  if (!journey) return null;
  return (
    <Space orientation="vertical" size="middle" className="full-width review-journey-experience">
      <ReviewStatusHero journey={journey} />
      <ReviewJourneyTimeline
        journey={journey}
        taskCheckRunning={taskCheckRunning}
        onRunTaskCheck={onRunTaskCheck}
      />
    </Space>
  );
}

function ReviewImmersiveMetricList({ metrics, emptyText }) {
  const items = Array.isArray(metrics) ? metrics : [];
  if (items.length === 0) {
    return <Text className="review-immersive-empty">{emptyText}</Text>;
  }
  return (
    <dl className="review-immersive-metrics">
      {items.map(item => (
        <div key={item.id}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReviewImmersiveWorkspace({
  presentation,
  journey,
  review,
  journeys,
  activeReviewKey,
  onSelectReview,
  onBack,
  onCancelReview,
  taskCheckRunning,
  onRunTaskCheck
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [taskInfoOpen, setTaskInfoOpen] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const taskInfoTriggerRef = useRef(null);
  const task = presentation.taskSummary;
  const reviewOptions = (Array.isArray(journeys) ? journeys : []).map(item => ({
    value: item.selectorKey,
    label: `${item.engineLabel} · ${item.providerModelLabel}`
  }));

  const cancelCurrentReview = async () => {
    if (!journey?.running || canceling) return;
    setCanceling(true);
    try {
      await onCancelReview?.({
        jobType: journey.requestedEngine === 'AGENT' ? 'AGENT_REVIEW' : 'AI_REVIEW',
        reviewKey: review?.reviewKey
      });
      message.success('AI Review 已中断');
    } catch (err) {
      message.error(err.message);
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="review-immersive-workspace">
      <header className="review-immersive-header">
        <Button
          className="review-immersive-back"
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
        >
          返回上一层
        </Button>
        <div className="review-immersive-task">
          <strong>{task?.title || `Review 任务 #${task?.id ?? '-'}`}</strong>
          <span>任务 #{task?.id ?? '-'}</span>
        </div>
        <div className="review-immersive-identity" aria-label="当前 Review 身份与状态">
          <Tag color={reviewJourneyEngineColor(journey?.engineKind)}>
            {presentation.identityLabel}
          </Tag>
          <Tooltip title={presentation.providerModelLabel}>
            <span>{presentation.providerModelLabel}</span>
          </Tooltip>
          <Tag color={reviewJourneyStatusColor(presentation.status)}>
            {presentation.statusLabel}
          </Tag>
        </div>
        {reviewOptions.length > 1 && (
          <Select
            className="review-immersive-selector"
            aria-label="选择当前 Review"
            value={activeReviewKey}
            options={reviewOptions}
            onChange={onSelectReview}
          />
        )}
        <div className="review-immersive-actions">
          {journey?.running && (
            <Button
              danger
              ghost
              icon={<CloseOutlined />}
              loading={canceling}
              onClick={cancelCurrentReview}
            >
              中断当前 Review
            </Button>
          )}
          <Button
            ref={taskInfoTriggerRef}
            ghost
            icon={<FileSearchOutlined />}
            onClick={() => setTaskInfoOpen(true)}
          >
            任务信息
          </Button>
        </div>
      </header>

      <main className="review-immersive-main">
        <section
          className={`review-immersive-stage review-immersive-stage-${presentation.engineVisual.toLowerCase()}`}
          aria-labelledby={`review-immersive-title-${presentation.selectedReviewKey || 'history'}`}
        >
          <div className="review-immersive-stage-glow" aria-hidden="true" />
          <div className="review-immersive-visual">
            <ReviewImmersiveCanvas
              key={`${presentation.selectedReviewKey || 'history'}:${presentation.engineVisual}`}
              presentation={presentation}
              reducedMotion={reducedMotion}
              fallback={presentation.engineVisual === 'STANDARD_FLOW' ? (
                <StandardReviewAnimation
                  state={presentation.heroState}
                  reducedMotion
                  ariaLabel={presentation.ariaLabel}
                />
              ) : (
                <AgentReviewAnimation
                  style="BRAIN"
                  state={presentation.heroState}
                  subStage={null}
                  reducedMotion
                  ariaLabel={presentation.ariaLabel}
                />
              )}
            />
          </div>
          <div className="review-immersive-current-stage">
            <span>当前阶段</span>
            <h1 id={`review-immersive-title-${presentation.selectedReviewKey || 'history'}`}>
              {presentation.currentStageTitle}
            </h1>
            <h2>{presentation.headline}</h2>
            <p>{presentation.description}</p>
          </div>
          {presentation.fallbackTransfer && (
            <div className="review-immersive-transfer" role="status">
              <strong>{presentation.fallbackTransfer.title}</strong>
              <span>{presentation.fallbackTransfer.description}</span>
            </div>
          )}
        </section>

        <nav className="review-immersive-timeline" aria-label="Review 阶段导航">
          <ReviewJourneyTimeline
            journey={journey}
            taskCheckRunning={taskCheckRunning}
            onRunTaskCheck={onRunTaskCheck}
            variant="immersive"
          />
        </nav>

        <aside className="review-immersive-aside" aria-label="Review 安全摘要">
          <section>
            <div className="review-immersive-panel-title">
              <span>上下文概览</span>
              <Tag>安全摘要</Tag>
            </div>
            <ReviewImmersiveMetricList
              metrics={presentation.contextMetrics}
              emptyText="暂无可靠上下文记录"
            />
          </section>
          <section>
            <div className="review-immersive-panel-title">
              <span>安全活动摘要</span>
              <Tag color="blue">{presentation.currentStageTitle}</Tag>
            </div>
            <ReviewImmersiveMetricList
              metrics={presentation.activityMetrics}
              emptyText="等待可靠活动记录"
            />
            {presentation.heartbeat.delayed && (
              <div className="review-immersive-delay">
                进度数据可能延迟；这不等同于 Review 已停止。
              </div>
            )}
          </section>
        </aside>
      </main>

      <footer className="review-immersive-footer">
        <span>
          真实开始时间：
          <strong>{presentation.startedAt ? formatDateTime(presentation.startedAt) : '历史任务未记录'}</strong>
        </span>
        <span>
          已运行时长：
          <strong>{presentation.elapsedMs === null ? '历史任务未记录' : formatJourneyDuration(presentation.elapsedMs)}</strong>
        </span>
        <span>
          心跳状态：
          <strong>
            {presentation.heartbeat.lastHeartbeatAt
              ? `${formatDateTime(presentation.heartbeat.lastHeartbeatAt)}${presentation.heartbeat.delayed ? ' · 可能延迟' : ''}`
              : presentation.engineVisual === 'STANDARD_FLOW'
                ? '通过任务轮询同步'
                : '历史任务未记录'}
          </strong>
        </span>
      </footer>

      <Drawer
        className="review-immersive-task-drawer"
        rootClassName="review-immersive-task-drawer-root"
        title="任务信息"
        size="min(480px, 100vw)"
        open={taskInfoOpen}
        keyboard
        onClose={() => setTaskInfoOpen(false)}
        afterOpenChange={open => {
          if (!open) {
            window.requestAnimationFrame(() => taskInfoTriggerRef.current?.focus());
          }
        }}
      >
        {task ? (
          <Descriptions column={1} size="small">
            <Descriptions.Item label="任务 ID">{task.id ?? '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="任务标题">{task.title}</Descriptions.Item>
            <Descriptions.Item label="触发类型">{task.triggerLabel}</Descriptions.Item>
            <Descriptions.Item label="端类型">{task.targetLabel}</Descriptions.Item>
            <Descriptions.Item label="任务状态">{task.taskStatusLabel}</Descriptions.Item>
            <Descriptions.Item label="事件时间">
              {task.eventAt ? formatDateTime(task.eventAt) : '历史任务未记录'}
            </Descriptions.Item>
            <Descriptions.Item label="变更文件">
              {task.changedFileCount ?? '历史任务未记录'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="历史任务未记录安全概要" />
        )}
      </Drawer>
    </div>
  );
}

function CodeQualityReviewView({
  taskId,
  review,
  journey,
  progress,
  changedFilesSummary,
  diffContextCapabilities,
  initialFixPreviews,
  triggerType,
  onRefresh,
  onRetry,
  retrying,
  onCancelReview,
  onCancelFixPreview,
  taskCheckRunning,
  onRunTaskCheck
}) {
  const location = useLocation();
  const [diffTarget, setDiffTarget] = useState(null);
  const [fixPreviewTarget, setFixPreviewTarget] = useState(null);
  const [fixPreviewByIndex, setFixPreviewByIndex] = useState({});
  const [fixPreviewLoadingIndex, setFixPreviewLoadingIndex] = useState(null);
  const [cancelingAction, setCancelingAction] = useState(null);
  const [activeFindingKeys, setActiveFindingKeys] = useState([]);
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
    return (
      <Space orientation="vertical" size="large" className="full-width">
        <Card>
          <Empty description="暂无代码质量 Review 结果" />
          <div className="empty-action-row">
            <Button type="primary" loading={retrying} onClick={() => onRetry?.()}>重试 AI Review</Button>
          </div>
        </Card>
        {journey && (
          <ReviewJourneyTimeline
            journey={journey}
            taskCheckRunning={taskCheckRunning}
            onRunTaskCheck={onRunTaskCheck}
          />
        )}
      </Space>
    );
  }

  const findings = Array.isArray(review.findings) ? review.findings : [];
  const requestedEngine = String(review.requestedEngine || 'STANDARD').toUpperCase();
  const effectiveEngine = String(review.effectiveEngine || requestedEngine).toUpperCase();
  const agentRunSummary = review.agentRunSummary || null;
  const reviewCoverage = agentReviewCoverage(progress, agentRunSummary);
  const isGitLabTask = ['GITLAB_MR_WEBHOOK', 'GITLAB_PUSH_WEBHOOK'].includes(triggerType);
  const alternateEngine = requestedEngine === 'AGENT' ? 'STANDARD' : 'AGENT';
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
      await onCancelReview?.({
        jobType: requestedEngine === 'AGENT' ? 'AGENT_REVIEW' : 'AI_REVIEW',
        reviewKey: review?.reviewKey
      });
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
      {journey?.running && (
        <ReviewJourneyExperience
          journey={journey}
          taskCheckRunning={taskCheckRunning}
          onRunTaskCheck={onRunTaskCheck}
        />
      )}
      <Card>
        <Space direction="vertical" size="small" className="full-width">
          <div className="quality-result-head">
            <Space wrap>
              <Tag color={reviewJourneyStatusColor(journey?.status)}>{journey?.statusLabel || '历史任务未记录'}</Tag>
              <Tag color="blue">{review.provider || '-'}</Tag>
              {review.model && <Tag>{review.model}</Tag>}
              <Tag color={reviewJourneyEngineColor(journey?.engineKind)}>
                {journey?.engineLabel || '历史任务未记录'}
              </Tag>
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
              {isGitLabTask && (
                alternateEngine === 'AGENT'
                || STANDARD_REVIEW_COMPARISON_ACTION_VISIBLE
              ) && (
                <Button
                  loading={retrying}
                  disabled={review.status === 'RUNNING'}
                  onClick={() => onRetry?.(undefined, alternateEngine)}
                >
                  {alternateEngine === 'AGENT' ? '追加 Agent 对照' : '追加普通 Review 对照'}
                </Button>
              )}
              <Button
                loading={retrying}
                disabled={review.status === 'RUNNING'}
                onClick={() => onRetry?.(requestedEngine === 'AGENT' ? undefined : review?.reviewKey, requestedEngine)}
              >
                重试 AI Review
              </Button>
            </Space>
          </div>
          <Alert
            type={findings.length > 0 && !journey?.running ? 'warning' : 'info'}
            showIcon
            message={journey?.running ? 'Review 正在执行，正式结果尚未生成' : summaryText}
          />
          {journey?.status === 'QUEUED' && <Alert type="info" showIcon message="AI Review 正在排队" description="任务已进入调度队列，执行状态会自动刷新。" />}
          {journey?.status === 'RUNNING' && <Alert type="info" showIcon message="AI Review 正在执行" description="模型 Provider 正在分析代码变更，完成后结果会自动刷新。" />}
          {journey?.status === 'SKIPPED' && (
            <Alert
              type="warning"
              showIcon
              message="AI Review 未执行"
              description="本次 Review 已跳过；历史记录不足时不会补造具体原因。"
            />
          )}
          {journey?.status === 'FAILED' && (
            <Alert
              type="error"
              showIcon
              message="AI Review 执行失败"
              description="本次 Review 没有成功完成，可查看统一时间轴中的固定安全摘要。"
            />
          )}
          {reviewCoverage && (
            <Alert
              type="warning"
              showIcon
              message={reviewCoverage.includedFileCount > 0 ? '部分敏感文件已隔离，其余文件继续 Agent Review' : '全部变更文件已按敏感路径策略安全跳过'}
              description={`总文件 ${reviewCoverage.totalChangedFileCount}，Agent 审查 ${reviewCoverage.includedFileCount}，排除 ${reviewCoverage.excludedFileCount}`}
            />
          )}
          {effectiveEngine === 'STANDARD_FALLBACK' && (
            <Alert
              type="warning"
              showIcon
              message="本次 Agent Review 已降级为普通 Review"
              description={[
                'Agent 未形成有效终态，任务已按既有策略由 Standard Review 接管。',
                safeReviewErrorCode(agentRunSummary?.failureCode)
                  ? `错误码：${safeReviewErrorCode(agentRunSummary.failureCode)}`
                  : null
              ].filter(Boolean).join(' ')}
            />
          )}
          <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
            <Descriptions.Item label="Profile">{review.profileCode || '-'}</Descriptions.Item>
            <Descriptions.Item label="请求引擎">{journey?.requestedEngine || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="实际引擎">{journey?.effectiveEngine || '历史任务未记录'}</Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatDateTime(review.startedAt)}</Descriptions.Item>
            <Descriptions.Item label="结束时间">{formatDateTime(review.finishedAt)}</Descriptions.Item>
            <Descriptions.Item label="Exit Code">{review.exitCode ?? '-'}</Descriptions.Item>
            {requestedEngine === 'AGENT' && <Descriptions.Item label="Agent Run">{agentRunSummary?.runId ?? review.agentRunId ?? '-'}</Descriptions.Item>}
            {requestedEngine === 'AGENT' && <Descriptions.Item label="Agent turns / 工具">{agentRunSummary ? `${agentRunSummary.turnCount ?? 0} / ${agentRunSummary.toolCallCount ?? 0}` : '-'}</Descriptions.Item>}
            {requestedEngine === 'AGENT' && <Descriptions.Item label="源码 / Diff 返回">{agentRunSummary ? `${agentRunSummary.sourceBytesReturned ?? 0} / ${agentRunSummary.diffBytesReturned ?? 0} bytes` : '-'}</Descriptions.Item>}
            {requestedEngine === 'AGENT' && <Descriptions.Item label="Agent 耗时">{agentRunSummary?.durationMs == null ? '-' : formatDuration(agentRunSummary.durationMs / 1000)}</Descriptions.Item>}
          </Descriptions>
        </Space>
      </Card>
      {!journey?.running && (
        <ReviewJourneyExperience
          journey={journey}
          taskCheckRunning={taskCheckRunning}
          onRunTaskCheck={onRunTaskCheck}
        />
      )}
      {!journey?.running && <Card title="质量问题">
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
                          {FINDING_REFINEMENT_ACTION_VISIBLE && (
                            <FindingRefinementControl
                              taskId={taskId}
                              review={review}
                              finding={finding}
                              findingIndex={index}
                              onRefresh={onRefresh}
                            />
                          )}
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
                    {EVALUATION_CASE_ACTION_VISIBLE && (
                      <EvaluationCaseControl
                        taskId={taskId}
                        review={review}
                        finding={finding}
                        compact
                      />
                    )}
                  </Space>
                )
              };
            })}
          />
        )}
      </Card>}
    </Space>
  );

  return (
    <Space direction="vertical" size="large" className="full-width">
      {resultContent}
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

function reviewJourneyStatusColor(status) {
  if (status === 'QUEUED') return 'blue';
  if (status === 'RUNNING') return 'processing';
  if (status === 'SUCCESS') return 'green';
  if (status === 'FAILED') return 'red';
  if (status === 'CANCELLED') return 'default';
  if (status === 'SKIPPED') return 'gold';
  return 'default';
}

function reviewJourneyEngineColor(engineKind) {
  if (engineKind === 'AGENT') return 'purple';
  if (engineKind === 'FALLBACK') return 'orange';
  if (engineKind === 'STANDARD') return 'blue';
  return 'default';
}

function ReviewSelectorIdentity({ journey, compact = false }) {
  if (!journey) return null;
  return (
    <div className={`review-selector-identity${compact ? ' review-selector-identity-compact' : ''}`}>
      <div className="review-selector-identity-main">
        <Tag color={reviewJourneyEngineColor(journey.engineKind)}>{journey.engineLabel}</Tag>
        <Tag color={reviewJourneyStatusColor(journey.status)}>{journey.statusLabel}</Tag>
      </div>
      <Tooltip title={journey.providerModelLabel}>
        <span className="review-selector-provider-model">{journey.providerModelLabel}</span>
      </Tooltip>
    </div>
  );
}

function CodeQualityReviewsPanel({
  taskId,
  reviews,
  journeys: providedJourneys,
  progress,
  changedFilesSummary,
  diffContextCapabilities,
  fixPreviews,
  triggerType,
  activeReviewKey,
  onActiveReviewKeyChange,
  onRefresh,
  onRetry,
  retrying,
  onCancelReview,
  onCancelFixPreview,
  deterministicChecks,
  runningDeterministicCheck,
  onRunDeterministicCheck
}) {
  const reviewItems = Array.isArray(reviews) ? reviews : [];
  const journeys = Array.isArray(providedJourneys)
    ? providedJourneys
    : buildReviewJourneys(reviewItems, progress, { deterministicChecks });
  const displayedActiveReviewKey = journeys.some(item => item.selectorKey === activeReviewKey)
    ? activeReviewKey
    : journeys[0]?.selectorKey;
  if (reviewItems.length <= 1) {
    const review = reviewItems[0] || null;
    const journey = journeys[0] || buildReviewJourney({}, progress, {
      deterministicChecks,
      allowUnscopedCompatibility: true
    });
    const scopedProgress = review
      ? selectReviewJourneyEvents(review, progress)
      : progress;
    return (
      <CodeQualityReviewView
        taskId={taskId}
        review={review}
        journey={journey}
        progress={scopedProgress}
        changedFilesSummary={changedFilesSummary}
        diffContextCapabilities={diffContextCapabilities}
        initialFixPreviews={fixPreviews}
        triggerType={triggerType}
        onRefresh={onRefresh}
        onRetry={onRetry}
        retrying={retrying}
        onCancelReview={onCancelReview}
        onCancelFixPreview={onCancelFixPreview}
        taskCheckRunning={runningDeterministicCheck}
        onRunTaskCheck={onRunDeterministicCheck}
      />
    );
  }
  return (
    <Space direction="vertical" size="small" className="full-width">
      <div className="review-selector-heading">
        <Tag color="geekblue">多模型 Review</Tag>
        <Text type="secondary">{reviewItems.length} 个独立结果，按 Review Key 隔离</Text>
      </div>
      <Tabs
        className="review-selector-tabs"
        activeKey={displayedActiveReviewKey}
        onChange={onActiveReviewKeyChange}
        items={reviewItems.map((review, index) => {
          const journey = journeys[index];
          return {
            key: journey.selectorKey,
            label: <ReviewSelectorIdentity journey={journey} compact />,
            children: (
              <CodeQualityReviewView
                taskId={taskId}
                review={review}
                journey={journey}
                progress={selectReviewJourneyEvents(review, progress, {
                  allowUnscopedCompatibility: false
                })}
                changedFilesSummary={changedFilesSummary}
                diffContextCapabilities={diffContextCapabilities}
                initialFixPreviews={review.reviewKey
                  ? (fixPreviews || []).filter(item => item.reviewKey === review.reviewKey)
                  : []}
                triggerType={triggerType}
                onRefresh={onRefresh}
                onRetry={onRetry}
                retrying={retrying}
                onCancelReview={onCancelReview}
                onCancelFixPreview={onCancelFixPreview}
                taskCheckRunning={runningDeterministicCheck}
                onRunTaskCheck={onRunDeterministicCheck}
              />
            )
          };
        })}
      />
    </Space>
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
    REUSED: '已复用',
  }[normalized] || (status || '历史任务未记录');
}

function TaskDetail({ taskId, onBack, onOpen }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { reportMode } = useReviewWorkspaceMode();
  const selectedReviewKey = new URLSearchParams(location.search).get('reviewKey');
  const [detail, setDetail] = useState(null);
  const [codeQualityResult, setCodeQualityResult] = useState(null);
  const [codeQualityResults, setCodeQualityResults] = useState([]);
  const [codeQualityProgress, setCodeQualityProgress] = useState([]);
  const [codeQualityGate, setCodeQualityGate] = useState(null);
  const [fixPreviews, setFixPreviews] = useState([]);
  const [deterministicChecks, setDeterministicChecks] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoaded, setDetailLoaded] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [runningDeterministicCheck, setRunningDeterministicCheck] = useState(false);
  const [error, setError] = useState(null);
  const [activeReviewKey, setActiveReviewKey] = useState(null);
  const [presentationNow, setPresentationNow] = useState(() => Date.now());
  const reviewSelectionTaskRef = useRef(taskId);
  const journeys = useMemo(() => buildReviewJourneys(
    codeQualityResults,
    codeQualityProgress,
    { deterministicChecks }
  ), [codeQualityResults, codeQualityProgress, deterministicChecks]);
  const selectionKeys = journeys.map(item => item.selectorKey).join('\u001f');
  const urlSelectionKey = journeys
    .find(item => item.reviewKey === selectedReviewKey)
    ?.selectorKey || null;
  const displayedActiveReviewKey = journeys.some(item => item.selectorKey === activeReviewKey)
    ? activeReviewKey
    : resolveReviewSelectionKey(journeys, {
        requestedReviewKey: selectedReviewKey,
        currentSelectionKey: activeReviewKey,
        preferRequested: Boolean(urlSelectionKey)
      });
  const activeReviewIndex = journeys.findIndex(
    item => item.selectorKey === displayedActiveReviewKey
  );
  const activeJourney = activeReviewIndex >= 0 ? journeys[activeReviewIndex] : null;
  const activeReview = activeReviewIndex >= 0 ? codeQualityResults[activeReviewIndex] : null;
  const changedFileCount = Array.isArray(detail?.changedFilesSummary?.files)
    ? detail.changedFilesSummary.files.length
    : Number.isFinite(Number(detail?.changedFilesSummary?.count))
      ? Number(detail.changedFilesSummary.count)
      : null;
  const taskSafeSummary = detail ? {
    id: detail.id,
    title: `${detail.projectName || '代码审查'} · ${taskTypeLabel(detail.triggerType)}`,
    triggerLabel: taskTypeLabel(detail.triggerType),
    targetLabel: targetTypeLabel(detail.targetType),
    taskStatusLabel: taskReviewStatusLabel(detail.reviewStatus),
    eventAt: detail.eventTime,
    changedFileCount
  } : null;
  const immersivePresentation = useMemo(() => buildReviewImmersivePresentation({
    loaded: detailLoaded,
    journey: activeJourney,
    taskSummary: taskSafeSummary,
    changedFilesSummary: { changedFileCount },
    now: presentationNow,
    safeFallback: Boolean(error)
  }), [
    detailLoaded,
    activeJourney,
    taskSafeSummary?.id,
    taskSafeSummary?.title,
    taskSafeSummary?.triggerLabel,
    taskSafeSummary?.targetLabel,
    taskSafeSummary?.taskStatusLabel,
    taskSafeSummary?.eventAt,
    changedFileCount,
    presentationNow,
    error
  ]);
  const taskDetailWorkspaceMode = TASK_DETAIL_AUTO_IMMERSIVE_ENTRY_ENABLED
    ? immersivePresentation.mode
    : 'RESULT';

  useEffect(() => {
    const taskChanged = reviewSelectionTaskRef.current !== taskId;
    reviewSelectionTaskRef.current = taskId;
    setActiveReviewKey(current => resolveReviewSelectionKey(journeys, {
      requestedReviewKey: selectedReviewKey,
      currentSelectionKey: taskChanged ? null : current,
      preferRequested: Boolean(urlSelectionKey)
    }));
  }, [taskId, selectedReviewKey, urlSelectionKey]);

  useEffect(() => {
    setActiveReviewKey(current => resolveReviewSelectionKey(journeys, {
      currentSelectionKey: current,
      preferRequested: false
    }));
  }, [selectionKeys]);

  useEffect(() => {
    reportMode(taskDetailWorkspaceMode);
    return () => reportMode('RESULT');
  }, [taskDetailWorkspaceMode, reportMode]);

  useEffect(() => {
    if (taskDetailWorkspaceMode !== 'IMMERSIVE' || !immersivePresentation.startedAt) {
      return undefined;
    }
    setPresentationNow(Date.now());
    const timer = window.setInterval(() => setPresentationNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [
    taskDetailWorkspaceMode,
    immersivePresentation.selectedReviewKey,
    immersivePresentation.startedAt
  ]);

  const selectActiveReview = useCallback(nextSelectionKey => {
    const nextJourney = journeys.find(item => item.selectorKey === nextSelectionKey);
    if (!nextJourney) return;
    setActiveReviewKey(nextSelectionKey);
    const search = new URLSearchParams(location.search);
    if (nextJourney.reviewKey) {
      search.set('reviewKey', nextJourney.reviewKey);
    } else {
      search.delete('reviewKey');
    }
    const query = search.toString();
    navigate({
      pathname: location.pathname,
      search: query ? `?${query}` : '',
      hash: location.hash
    }, {
      replace: true,
      state: location.state
    });
  }, [journeys, location.pathname, location.search, location.hash, location.state, navigate]);

  const load = async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const taskDetail = await fetchApi(`/api/review-tasks/${taskId}`);
      setDetail(taskDetail);
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
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) {
        setLoading(false);
        setDetailLoaded(true);
      }
    }
  };

  useEffect(() => {
    setDetailLoaded(false);
    load();
  }, [taskId]);

  useEffect(() => {
    const hasRunningFixPreview = fixPreviews.some(item => ['QUEUED', 'RUNNING'].includes(item?.status));
    const hasRunningReview = codeQualityResults.some(
      item => ['PENDING', 'QUEUED', 'RUNNING'].includes(item?.status)
    );
    if (
      !hasRunningReview
      && !['PENDING', 'QUEUED', 'RUNNING'].includes(codeQualityResult?.status)
      && !hasRunningFixPreview
    ) return undefined;
    const timer = window.setInterval(() => load({ silent: true }), 5000);
    return () => window.clearInterval(timer);
  }, [taskId, codeQualityResult?.status, codeQualityResults, fixPreviews]);

  const retryCodeQualityReview = async (reviewKey, reviewEngine) => {
    setRetrying(true);
    setError(null);
    try {
      const retryResult = await fetchApi(`/api/code-quality-reviews/tasks/${taskId}/retry`, {
        method: 'POST',
        body: JSON.stringify({
          ...(reviewKey ? { reviewKey } : {}),
          ...(reviewEngine ? { reviewEngine, comparisonMode: true } : {})
        })
      });
      const optimisticReviews = (retryResult.reviews || [retryResult]).map(item => ({
        taskId: retryResult.taskId,
        projectId: detail?.projectId,
        reviewKey: item.reviewKey,
        profileCode: item.profileCode || retryResult.profileCode,
        provider: item.provider || retryResult.provider,
        model: item.model,
        displayName: item.displayName,
        requestedEngine: item.requestedEngine || retryResult.requestedEngine || reviewEngine || 'STANDARD',
        effectiveEngine: item.effectiveEngine || retryResult.effectiveEngine || reviewEngine || 'STANDARD',
        agentRunSummary: item.agentRunSummary || retryResult.agentRunSummary,
        status: item.status || retryResult.status,
        overallLevel: item.overallLevel || retryResult.overallLevel,
        summary: 'AI code review is running',
        findingCount: item.findingCount ?? retryResult.findingCount,
        findings: []
      }));
      setCodeQualityResults(current => {
        if (!reviewKey && !reviewEngine) return optimisticReviews;
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
        if (!reviewKey && !reviewEngine) return [localQueued];
        return [...current.filter(item => item.reviewKey !== reviewKey), localQueued];
      });
      setFixPreviews(current => (
        reviewKey ? current.filter(item => item.reviewKey !== reviewKey) : reviewEngine ? current : []
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
    } catch {
      setError('确定性检查暂不可用，请稍后重试。');
      message.error('确定性检查暂不可用');
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

  const qualityReviewContent = (
    <CodeQualityReviewsPanel
      taskId={taskId}
      reviews={codeQualityResults}
      journeys={journeys}
      progress={codeQualityProgress}
      changedFilesSummary={detail?.changedFilesSummary}
      diffContextCapabilities={detail?.diffContextCapabilities}
      fixPreviews={fixPreviews}
      triggerType={detail?.triggerType}
      activeReviewKey={displayedActiveReviewKey}
      onActiveReviewKeyChange={selectActiveReview}
      onRefresh={() => load({ silent: true })}
      onRetry={retryCodeQualityReview}
      retrying={retrying}
      onCancelReview={cancelCodeQualityJob}
      onCancelFixPreview={cancelCodeQualityJob}
      deterministicChecks={deterministicChecks}
      runningDeterministicCheck={runningDeterministicCheck}
      onRunDeterministicCheck={runDeterministicCheck}
    />
  );

  if (
    TASK_DETAIL_AUTO_IMMERSIVE_ENTRY_ENABLED
    && immersivePresentation.mode === 'IMMERSIVE'
    && detail
    && activeJourney
  ) {
    return (
      <ReviewImmersiveWorkspace
        presentation={immersivePresentation}
        journey={activeJourney}
        review={activeReview}
        journeys={journeys}
        activeReviewKey={displayedActiveReviewKey}
        onSelectReview={selectActiveReview}
        onBack={onBack}
        onCancelReview={cancelCodeQualityJob}
        taskCheckRunning={runningDeterministicCheck}
        onRunTaskCheck={runDeterministicCheck}
      />
    );
  }

  const canRerunTask = Boolean(detail && ['GITLAB_MR_WEBHOOK', 'GITLAB_PUSH_WEBHOOK'].includes(detail.triggerType));
  const taskHeaderTitle = detail ? taskTitle(detail) : `任务 #${taskId}`;
  const taskHeaderDescription = detail
    ? branchSummary(detail)
    : '查看统一 Review 进度、结果和阶段详情。';
  const detailActions = (
    <>
      <MuiButton
        variant="outlined"
        startIcon={<ArrowLeftOutlined />}
        onClick={onBack}
      >
        返回上一层
      </MuiButton>
      <MuiButton
        variant="contained"
        startIcon={<ReloadOutlined />}
        disabled={!canRerunTask || rerunning}
        onClick={rerunReviewTask}
      >
        {rerunning ? '执行中' : '重新执行审阅'}
      </MuiButton>
      <MuiButton
        variant="outlined"
        disabled={!canRerunTask || rerunning}
        onClick={cloneAndRerunReviewTask}
      >
        复制为新任务重跑
      </MuiButton>
    </>
  );

  return (
    <TaskWorkspaceShell
      title={taskHeaderTitle}
      description={taskHeaderDescription}
      actions={detailActions}
    >
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        {detail ? (
          <Space direction="vertical" size="large" className="full-width">
            <Paper variant="outlined" sx={{ p: { xs: 1.75, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 1.75, alignItems: { xs: 'stretch', md: 'center' }, justifyContent: 'space-between' }}>
                <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Chip size="small" label={`#${detail.id}`} sx={{ height: 24, borderColor: '#c9d5e2' }} variant="outlined" />
                  <Chip size="small" label={taskTypeLabel(detail.triggerType)} sx={{ height: 24 }} variant="outlined" />
                  <Chip size="small" label={targetTypeLabel(detail.targetType)} sx={{ height: 24 }} variant="outlined" />
                </Stack>
                <Tag color={taskReviewStatusColor(detail.reviewStatus)}>{taskReviewStatusLabel(detail.reviewStatus)}</Tag>
              </Stack>
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
                <Descriptions.Item label="事件时间">{formatDateTime(detail.eventTime)}</Descriptions.Item>
              </Descriptions>
              {detail.errorMessage && (
                <Alert className="section-gap" type="error" showIcon message="任务执行失败" description={detail.errorMessage} />
              )}
            </Paper>
            <Paper variant="outlined" sx={{ p: { xs: 1.25, md: 2 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
              <Space direction="vertical" size="large" className="full-width">
                {qualityReviewContent}
                {detail.triggerType === 'GITLAB_PUSH_WEBHOOK' && (
                  <Collapse
                    className="task-push-gate-collapse"
                    items={[{
                      key: 'push-gate',
                      label: 'Push 审核',
                      children: <CodeQualityGateView gate={codeQualityGate} detail={detail} />
                    }]}
                  />
                )}
              </Space>
            </Paper>
          </Space>
        ) : !loading ? <Empty description="任务不存在" /> : null}
      </Spin>
    </TaskWorkspaceShell>
  );
}


function SettingsCardHeader({ icon, title, description, tags, extra, compact = false }) {
  return (
    <div className={`settings-card-header${compact ? ' settings-card-header-compact' : ''}`}>
      <div className="settings-card-heading">
        <span className="settings-card-icon" aria-hidden="true">{icon}</span>
        <div className="settings-card-title-copy">
          <Space wrap size={[8, 6]} className="settings-card-title-row">
            <Title level={compact ? 5 : 4} className="settings-card-title">{title}</Title>
            {tags && <Space wrap size={[4, 4]}>{tags}</Space>}
          </Space>
          <Text type="secondary" className="settings-card-description">{description}</Text>
        </div>
      </div>
      {extra && <div className="settings-card-extra">{extra}</div>}
    </div>
  );
}

function AgentBudgetFieldCard({
  field,
  value,
  defaultValue,
  limits,
  onChange
}) {
  const toDisplayValue = rawValue => (
    field.bytes ? bytesToKilobytes(rawValue) : rawValue
  );
  const displayDefault = toDisplayValue(defaultValue) ?? '-';
  const displayMinimum = toDisplayValue(limits.min);
  const displayMaximum = toDisplayValue(limits.max);

  return (
    <div className="agent-budget-field-card">
      <div className="agent-budget-field-title">
        <Text strong>{field.label}</Text>
      </div>
      <InputNumber
        aria-label={field.label}
        className="agent-budget-field-input"
        size="large"
        min={displayMinimum}
        max={displayMaximum}
        step={1}
        precision={0}
        addonAfter={field.unit}
        value={toDisplayValue(value)}
        onChange={nextValue => onChange(
          field.key,
          field.bytes ? kilobytesToBytes(nextValue) : nextValue
        )}
      />
      <div className="agent-budget-field-meta">
        <div>
          <Text type="secondary">默认值</Text>
          <Text strong>{displayDefault} {field.unit}</Text>
        </div>
        <div>
          <Text type="secondary">允许范围</Text>
          <Text strong>{displayMinimum}～{displayMaximum} {field.unit}</Text>
        </div>
      </div>
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
  const [agentSettings, setAgentSettings] = useState(null);
  const [agentSettingsDraft, setAgentSettingsDraft] = useState({
    ...normalizeAgentRuntimeDraft(null),
    budgets: normalizeAgentBudgets(null)
  });
  const [agentSettingsSaving, setAgentSettingsSaving] = useState(false);
  const [agentSettingsTesting, setAgentSettingsTesting] = useState(false);
  const [agentSettingsTestResult, setAgentSettingsTestResult] = useState(null);
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
      const [settingsData, agentSettingsData, profileData, providerData, groupData, projectData, pathMappingData] = await Promise.all([
        fetchApi('/api/code-quality-reviews/settings'),
        fetchApi('/api/code-quality-reviews/agent-settings'),
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
      setAgentSettings(agentSettingsData);
      setAgentSettingsDraft({
        ...normalizeAgentRuntimeDraft(agentSettingsData),
        budgets: normalizeAgentBudgets(agentSettingsData)
      });
      setAgentSettingsTestResult(agentSettingsData?.configurationTest || null);
      setAgentSettingsTesting(['QUEUED', 'RUNNING'].includes(agentSettingsData?.configurationTest?.status));
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

  useEffect(() => {
    const requestId = agentSettingsTestResult?.requestId;
    const initialStatus = agentSettingsTestResult?.status;
    if (!requestId || !['QUEUED', 'RUNNING'].includes(initialStatus)) return undefined;

    let cancelled = false;
    let timer = null;
    const deadline = Date.now() + agentConfigurationTestPollTimeoutMs;
    const poll = async () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setAgentSettingsTesting(false);
        setAgentSettingsTestResult(current => ({
          ...(current || {}),
          status: 'POLL_TIMEOUT',
          message: '等待配置测试结果超时，请稍后刷新设置页查看最终状态。'
        }));
        return;
      }
      try {
        const settings = await fetchApi('/api/code-quality-reviews/agent-settings');
        if (cancelled) return;
        const nextTest = settings?.configurationTest || null;
        setAgentSettings(settings);
        setAgentSettingsTestResult(nextTest);
        if (['QUEUED', 'RUNNING'].includes(nextTest?.status)) {
          timer = window.setTimeout(poll, 2000);
          return;
        }
        setAgentSettingsTesting(false);
        if (nextTest?.status === 'SUCCESS') {
          messageApi.success('Agent 配置测试成功');
        } else {
          messageApi.error(nextTest?.message || 'Agent 配置测试失败');
        }
      } catch (err) {
        if (cancelled) return;
        setAgentSettingsTesting(false);
        setAgentSettingsTestResult(current => ({
          ...(current || {}),
          status: 'POLL_FAILED',
          message: err.message
        }));
        messageApi.error(err.message);
      }
    };

    timer = window.setTimeout(poll, 1500);
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [agentSettingsTestResult?.requestId]);

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

  const saveAgentSettings = async ({ clearApiKey = false, showSuccess = true } = {}) => {
    if (agentSettingsSaving) return null;
    const runtimeError = validateAgentRuntimeDraft(agentSettingsDraft, agentSettings);
    if (!clearApiKey && runtimeError) {
      messageApi.error(runtimeError);
      return null;
    }
    const budgetError = validateAgentBudgets(agentSettingsDraft.budgets, agentSettings);
    if (!clearApiKey && budgetError) {
      messageApi.error(budgetError);
      return null;
    }
    setAgentSettingsSaving(true);
    try {
      const body = buildAgentSettingsPayload(agentSettingsDraft, { clearKey: clearApiKey });
      const settings = await fetchApi('/api/code-quality-reviews/agent-settings', {
        method: 'PUT',
        body: JSON.stringify(body)
      });
      setAgentSettings(settings);
      setAgentSettingsDraft({
        ...normalizeAgentRuntimeDraft(settings),
        budgets: normalizeAgentBudgets(settings)
      });
      setAgentSettingsTestResult(settings?.configurationTest || null);
      if (showSuccess) {
        messageApi.success(clearApiKey ? 'Agent API Key 已清除' : 'Agent Review 设置已保存');
      }
      return settings;
    } catch (err) {
      messageApi.error(err.message);
      return null;
    } finally {
      setAgentSettingsSaving(false);
    }
  };

  const resetAgentBudgets = async () => {
    if (agentSettingsSaving) return;
    setAgentSettingsSaving(true);
    try {
      const settings = await fetchApi('/api/code-quality-reviews/agent-settings', {
        method: 'PUT',
        body: JSON.stringify({ resetBudgets: true })
      });
      setAgentSettings(settings);
      setAgentSettingsDraft(current => ({
        ...current,
        budgets: normalizeAgentBudgets(settings)
      }));
      messageApi.success('Agent Review 运行参数已恢复默认');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setAgentSettingsSaving(false);
    }
  };

  const updateAgentBudget = (field, value) => {
    if (!Number.isInteger(Number(value))) return;
    setAgentSettingsDraft(current => ({
      ...current,
      budgets: {
        ...current.budgets,
        [field]: Number(value)
      }
    }));
  };

  const testAgentSettings = async () => {
    if (agentSettingsTesting || agentSettingsSaving) return;
    const savedSettings = await saveAgentSettings({ showSuccess: false });
    if (!savedSettings) return;
    const selectedRuntime = selectedRuntimeSettings(
      savedSettings,
      savedSettings?.selectedRuntime
    );
    if (!savedSettings?.enabled || !selectedRuntime?.apiKeyConfigured) {
      messageApi.warning('请先保存并启用 Agent Review 配置');
      return;
    }
    if (savedSettings?.selectedRuntime === customAgentRuntime && !selectedRuntime?.configurationComplete) {
      messageApi.warning('自定义 Agent 配置不完整或 Base URL 未通过安全校验');
      return;
    }
    if (savedSettings?.selectedRuntime === customAgentRuntime && !selectedRuntime?.workerSupported) {
      messageApi.warning('当前没有支持 OpenAI Responses 的在线 Worker');
      return;
    }
    if (savedSettings?.workerStatus !== 'ONLINE') {
      messageApi.warning('Agent Worker 当前离线，无法执行配置测试');
      return;
    }
    setAgentSettingsTesting(true);
    setAgentSettingsTestResult(null);
    try {
      const result = await fetchApi('/api/code-quality-reviews/agent-settings/test', { method: 'POST' });
      setAgentSettingsTestResult(result);
      setAgentSettings(current => current ? { ...current, configurationTest: result } : current);
      if (['QUEUED', 'RUNNING'].includes(result?.status)) {
        messageApi.info('Agent 配置测试已提交，正在等待 Worker 完成');
      } else {
        setAgentSettingsTesting(false);
      }
    } catch (err) {
      setAgentSettingsTesting(false);
      setAgentSettingsTestResult({ status: 'FAILED', message: err.message });
      messageApi.error(err.message);
    }
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
          reviewEngine: 'AGENT',
          agentSourceExportAllowed: true,
          aiReviewEnabled: true,
          triggerOnManual: true,
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

  const agentTestStatus = String(agentSettingsTestResult?.status || 'NOT_RUN').toUpperCase();
  const agentTestPending = ['QUEUED', 'RUNNING'].includes(agentTestStatus);
  const agentTestAlertType = agentTestPending
    ? 'info'
    : agentTestStatus === 'POLL_TIMEOUT'
      ? 'warning'
      : 'error';
  const agentTestMessage = agentTestPending
    ? 'Agent 配置测试进行中'
    : 'Agent 配置不可用';
  const selectedAgentRuntime = selectedRuntimeSettings(
    agentSettings,
    agentSettingsDraft.selectedRuntime
  );
  const agentRuntimeError = validateAgentRuntimeDraft(agentSettingsDraft, agentSettings);
  const agentSaveRequiresEncryption = Boolean(
    agentSettingsDraft.enabled
    || String(agentSettingsDraft.apiKey || '').trim()
    || String(agentSettingsDraft.customRuntime?.apiKey || '').trim()
  );
  const currentAgentBudgetLimits = agentBudgetLimits(agentSettings);
  const agentBudgetError = validateAgentBudgets(agentSettingsDraft.budgets, agentSettings);
  const agentWorkerPool = useMemo(
    () => normalizeAgentWorkerPool(agentSettings),
    [agentSettings]
  );
  const agentQueueMetrics = useMemo(
    () => normalizeAgentQueueMetrics(agentSettings, agentWorkerPool),
    [agentSettings, agentWorkerPool]
  );
  const agentBudgetFields = [
    { key: 'maxTurns', label: '模型决策回合', unit: 'turns' },
    { key: 'maxToolCalls', label: 'MCP 工具调用', unit: '次' },
    { key: 'maxSourceBytes', label: '源码返回', unit: 'KB', bytes: true },
    { key: 'timeoutSeconds', label: '整体超时', unit: '秒' },
    { key: 'inlineDiffBytes', label: '内联 Diff', unit: 'KB', bytes: true },
    { key: 'maxEvidenceCalls', label: '证据调用', unit: '次', advanced: true },
    { key: 'convergeAtCalls', label: '收敛起点', unit: '次', advanced: true },
    { key: 'submitByTurn', label: '最迟提交回合', unit: 'turn', advanced: true }
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
          <div className="settings-subsection">
            <Space direction="vertical" size="middle" className="global-settings-stack">
            <SettingsCardHeader
              icon={<GlobalOutlined />}
              title="平台全局能力"
              description="控制全平台 AI Review 调用和钉钉消息推送；规则分析与结果落库不受影响。"
              tags={(
                <>
                  <Tag color={(settingsDraft?.reviewEnabled ?? false) ? 'green' : 'default'}>AI Review {(settingsDraft?.reviewEnabled ?? false) ? '开启' : '关闭'}</Tag>
                  <Tag color={(settingsDraft?.dingtalkNotificationEnabled ?? true) ? 'blue' : 'default'}>钉钉 {(settingsDraft?.dingtalkNotificationEnabled ?? true) ? '开启' : '关闭'}</Tag>
                </>
              )}
            />
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
          </div>
        </Card>
      )
    },
    {
      key: 'agent-review-settings',
      label: (
        <Space wrap>
          <Text strong>Agent Review</Text>
          <Tag color={agentSettings?.enabled ? 'purple' : 'default'}>{agentSettings?.enabled ? '已启用' : '未启用'}</Tag>
          <Tag>{agentSettings?.selectedRuntime === customAgentRuntime ? 'OpenAI Responses' : 'Claude + DeepSeek'}</Tag>
          <Tag color={agentWorkerPool.status === 'ONLINE' ? 'green' : 'red'}>Worker Pool {agentWorkerPool.status}</Tag>
          {agentQueueMetrics.queued > 0 && <Tag color="gold">排队 {agentQueueMetrics.queued}</Tag>}
        </Space>
      ),
      children: (
        <Card bordered={false} className="settings-inner-card">
          <Space direction="vertical" size="middle" className="full-width">
            <div className="settings-subsection">
              <SettingsCardHeader
                icon={<KeyOutlined />}
                title="Agent Review 接入配置"
                description="选择 Agent 运行时并配置独立凭据；默认保持 Claude Code + DeepSeek。"
                tags={<Tag color={selectedAgentRuntime?.apiKeyConfigured ? 'green' : 'gold'}>Key {selectedAgentRuntime?.apiKeyConfigured ? '已配置' : '未配置'}</Tag>}
              />
              {!agentSettings?.encryptionAvailable && (
              <Alert
                type="error"
                showIcon
                message="需要配置 Agent 加密主密钥"
                description="请在后端运行环境设置 AGENT_REVIEW_CONFIG_ENCRYPTION_KEY 并重启服务。该密钥用于分别加密两个 Agent Key 槽位。"
              />
              )}
              <Row gutter={[16, 16]} align="bottom">
                <Col xs={24} md={5}>
                  <Space direction="vertical">
                    <Text strong>启用 Agent Review</Text>
                    <Switch
                      checked={agentSettingsDraft.enabled}
                      disabled={agentSettingsSaving || (
                        agentSettingsDraft.selectedRuntime === customAgentRuntime
                        && !agentSettingsDraft.enabled
                        && !agentSettings?.customRuntime?.workerSupported
                      )}
                      onChange={checked => setAgentSettingsDraft(current => ({ ...current, enabled: checked }))}
                    />
                  </Space>
                </Col>
                <Col xs={24} md={11}>
                  <Text strong>Agent 运行时</Text>
                  <Select
                    className="full-width"
                    value={agentSettingsDraft.selectedRuntime}
                    disabled={agentSettingsSaving}
                    options={(agentSettings?.runtimeOptions || []).map(item => ({ value: item.value, label: item.isDefault ? `${item.label}（默认）` : item.label }))}
                    onChange={value => setAgentSettingsDraft(current => ({ ...current, selectedRuntime: value }))}
                  />
                </Col>
                <Col xs={24} md={8}>
                <Space wrap>
                  <Button
                    type="primary"
                    loading={agentSettingsSaving}
                    onClick={() => saveAgentSettings()}
                    disabled={Boolean(agentBudgetError || agentRuntimeError) || (!agentSettings?.encryptionAvailable && agentSaveRequiresEncryption)}
                    title={!agentSettings?.encryptionAvailable && agentSaveRequiresEncryption ? '请先初始化加密主密钥并重启后端' : undefined}
                  >
                    保存
                  </Button>
                  <Button loading={agentSettingsTesting} onClick={testAgentSettings}>测试配置</Button>
                  <Button danger loading={agentSettingsSaving} disabled={!selectedAgentRuntime?.apiKeyConfigured} onClick={() => saveAgentSettings({ clearApiKey: true })}>清除当前 Key</Button>
                </Space>
                </Col>
              </Row>
              {agentSettingsDraft.selectedRuntime === customAgentRuntime ? (
                <>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={8}>
                      <Text strong>配置名称</Text>
                      <Input
                        value={agentSettingsDraft.customRuntime?.displayName}
                        placeholder="Custom OpenAI Agent"
                        onChange={event => setAgentSettingsDraft(current => ({ ...current, customRuntime: { ...current.customRuntime, displayName: event.target.value } }))}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>协议</Text>
                      <Input value="OpenAI Responses" disabled />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>推理强度</Text>
                      <Select
                        className="full-width"
                        value={agentSettingsDraft.customRuntime?.reasoningEffort}
                        options={(agentSettings?.customRuntime?.reasoningEffortOptions || ['low', 'medium', 'high']).map(value => ({ value, label: value }))}
                        onChange={value => setAgentSettingsDraft(current => ({ ...current, customRuntime: { ...current.customRuntime, reasoningEffort: value } }))}
                      />
                    </Col>
                    <Col xs={24} md={12}>
                      <Text strong>Base URL</Text>
                      <Input
                        value={agentSettingsDraft.customRuntime?.baseUrl}
                        placeholder="https://relay.example.com/v1"
                        onChange={event => setAgentSettingsDraft(current => ({ ...current, customRuntime: { ...current.customRuntime, baseUrl: event.target.value } }))}
                      />
                    </Col>
                    <Col xs={24} md={12}>
                      <Text strong>模型</Text>
                      <Input
                        value={agentSettingsDraft.customRuntime?.model}
                        placeholder="gpt-5.6-sol"
                        onChange={event => setAgentSettingsDraft(current => ({ ...current, customRuntime: { ...current.customRuntime, model: event.target.value } }))}
                      />
                    </Col>
                    <Col xs={24}>
                      <Text strong>自定义中转站 API Key</Text>
                      <Input.Password
                        value={agentSettingsDraft.customRuntime?.apiKey}
                        placeholder={agentSettings?.customRuntime?.apiKeyConfigured ? `${agentSettings.customRuntime.apiKeyMasked || '已配置'}；留空保持原值` : '请输入自定义 Agent API Key'}
                        onChange={event => setAgentSettingsDraft(current => ({ ...current, customRuntime: { ...current.customRuntime, apiKey: event.target.value } }))}
                      />
                    </Col>
                    <Col xs={24}>
                      <Space>
                        <Switch
                          checked={agentSettingsDraft.customRuntime?.tlsVerify === false}
                          onChange={checked => setAgentSettingsDraft(current => ({
                            ...current,
                            customRuntime: { ...current.customRuntime, tlsVerify: !checked }
                          }))}
                        />
                        <Text strong type={agentSettingsDraft.customRuntime?.tlsVerify === false ? 'danger' : undefined}>
                          跳过 TLS 证书校验（高风险）
                        </Text>
                      </Space>
                    </Col>
                  </Row>
                  <Space wrap>
                    <Tag color={agentSettings?.customRuntime?.urlSafetyValidated ? 'green' : 'gold'}>
                      Base URL {agentSettings?.customRuntime?.urlSafetyValidated ? '安全校验通过' : '待配置'}
                    </Tag>
                    <Tag color={agentSettings?.customRuntime?.workerSupported ? 'green' : 'gold'}>
                      Worker {agentSettings?.customRuntime?.workerSupported ? '支持 Responses' : '暂不支持'}
                    </Tag>
                    <Tag color={agentSettings?.customRuntime?.configurationComplete ? 'green' : 'gold'}>
                      配置{agentSettings?.customRuntime?.configurationComplete ? '完整' : '未完成'}
                    </Tag>
                  </Space>
                </>
              ) : (
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12}>
                    <Text strong>DeepSeek 模型与 Endpoint</Text>
                    <Input value={`${agentSettings?.defaultRuntime?.model || 'deepseek-v4-pro[1m]'} · ${agentSettings?.defaultRuntime?.endpoint || ''}`} disabled />
                  </Col>
                  <Col xs={24} md={12}>
                    <Text strong>独立 DeepSeek API Key</Text>
                    <Input.Password
                      value={agentSettingsDraft.apiKey}
                      disabled={agentSettingsSaving}
                      placeholder={agentSettings?.defaultRuntime?.apiKeyConfigured ? `${agentSettings.defaultRuntime.apiKeyMasked || '已配置'}；留空保持原值` : '请输入 Agent 专用 API Key'}
                      onChange={event => setAgentSettingsDraft(current => ({ ...current, apiKey: event.target.value }))}
                    />
                  </Col>
                </Row>
              )}
              {agentRuntimeError && <Alert type="error" showIcon message="运行时配置无效" description={agentRuntimeError} />}
              {agentSettingsTestResult && !['NOT_RUN', 'SUCCESS'].includes(agentTestStatus) && (
                <Alert
                  showIcon
                  type={agentTestAlertType}
                  message={agentTestMessage}
                  description={agentSettingsTestResult.message || (agentTestPending ? 'Worker 正在执行当前 Agent 运行时的 synthetic 最小连通性测试。' : undefined)}
                />
              )}
            </div>
            <div className="settings-subsection">
              <SettingsCardHeader
                icon={<ControlOutlined />}
                title="Agent 执行预算"
                description="控制任务回合数、工具调用、源码量、超时和证据调用上限。"
                tags={<Tag color="blue">{agentSettings?.budgetConfigSource === 'CUSTOM' ? '自定义预算' : '默认预算'}</Tag>}
                extra={<Button loading={agentSettingsSaving} onClick={resetAgentBudgets}>恢复默认运行参数</Button>}
              />
              <div className="agent-budget-toolbar">
              <Text type="secondary">
                参数只影响保存后新建的 Agent 任务；已排队和运行中的任务继续使用入队快照。KB 按 1000 bytes 计算。
              </Text>
              </div>
              <div className="agent-budget-grid agent-budget-grid-basic">
              {agentBudgetFields.map(item => (
                <AgentBudgetFieldCard
                  key={item.key}
                  field={item}
                  value={agentSettingsDraft.budgets?.[item.key]}
                  defaultValue={agentSettings?.budgetDefaults?.[item.key]}
                  limits={currentAgentBudgetLimits[item.key]}
                  onChange={updateAgentBudget}
                />
              ))}
              </div>
              {agentBudgetError && <Alert type="error" showIcon message="运行参数无效" description={agentBudgetError} />}
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
                <SettingsCardHeader
                  icon={<TeamOutlined />}
                  title="项目组管理"
                  description="维护项目组、默认 Review 模板、可用模型及基础信息。"
                  tags={<Tag>{groups.length} 个项目组</Tag>}
                  extra={<Button icon={<ReloadOutlined />} onClick={refreshProjectConfigData} loading={projectConfigReloading}>刷新</Button>}
                />
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
                  <div className="settings-subsection settings-subcard">
                    <SettingsCardHeader
                      compact
                      icon={<BellOutlined />}
                      title={`${editingGroupDraft.groupName || '项目组'}钉钉通知`}
                      description="配置该项目组接收规则提醒和 AI Review 结果的钉钉机器人；未配置时通知会记录为跳过。"
                      tags={<Tag>{(editingGroupDraft.dingtalkWebhooks || []).filter(item => item.enabled !== false).length} 个启用</Tag>}
                      extra={<Button icon={<PlusOutlined />} onClick={() => addGroupWebhookDraft('editing')}>新增机器人</Button>}
                    />
                    {renderWebhookDraftList(editingGroupDraft.dingtalkWebhooks || [], 'editing')}
                  </div>
                )}
              </Space>
            </div>
            <div className="settings-subsection">
              <Space direction="vertical" size="middle" className="full-width">
                <SettingsCardHeader
                  icon={<ApartmentOutlined />}
                  title="项目归属与 Review 配置"
                  description="为具体 GitLab 项目绑定项目组、端类型和默认 Review 模型。"
                  tags={targetConfigDraft?.targetType ? <Tag>{targetTypeLabel(targetConfigDraft.targetType)}</Tag> : null}
                />
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={7}>
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
                  <Col xs={24} md={10}>
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
                  <Col xs={24} md={7}>
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
                  <Col xs={24} md={7}>
                    <Text strong>当前项目所用模型</Text>
                    <Select
                      className="full-width prompt-field"
                      value={targetConfigDraft?.providerCode || ''}
                      options={profileProviderOptions}
                      onChange={value => updateTargetConfigDraft('providerCode', value || null)}
                    />
                  </Col>
                  <Col xs={24} md={4}>
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
                <SettingsCardHeader
                  icon={<BranchesOutlined />}
                  title="端类型自动识别规则"
                  description="根据仓库目录结构识别后端、PC、App 等端类型。"
                  tags={<Tag>{targetPathMappingDrafts.filter(item => item.enabled !== false).length} 个启用</Tag>}
                  extra={(
                    <Button type="primary" loading={targetPathMappingSaving} onClick={saveTargetPathMappings}>
                      保存路径映射
                    </Button>
                  )}
                />
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
          <SettingsCardHeader
            icon={<ApiOutlined />}
            title="AI 模型 Provider"
            description="配置模型服务地址、模型名称、访问凭证、超时和启用状态。"
            tags={(
              <>
                <Tag color="blue">{sourceLabel(aiSettings?.defaultProviderCode || selectedProviderCode)}</Tag>
                <Tag color={providerDraft?.enabled ? 'green' : 'default'}>{providerDraft?.enabled ? '已启用' : '未启用'}</Tag>
                <Tag color={providerDraft?.apiKeyConfigured ? 'green' : 'gold'}>Key {providerDraft?.apiKeyConfigured ? '已配置' : '未配置'}</Tag>
              </>
            )}
          />
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
          <Tag>Profile / 项目组策略</Tag>
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
                  <SettingsCardHeader
                    icon={<FileTextOutlined />}
                    title="普通 Review 初始 Prompt"
                    description="配置普通 Review 的审查场景、模型覆盖与初始审查指令；该配置不影响 Agent Review。"
                    tags={<Tag color="blue">STANDARD REVIEW</Tag>}
                  />
                  <Row gutter={[16, 16]}>
                    <Col xs={24} lg={8}>
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
                  <SettingsCardHeader
                    icon={<SettingOutlined />}
                    title="项目组 AI Review 通用策略"
                    description="配置项目组默认 Review 引擎、自动触发方式与 Push 审核门槛。"
                    tags={(
                      <>
                        <Tag color="blue">项目组级</Tag>
                        {selectedPushPolicyGroupId && <Tag color="purple">AGENT</Tag>}
                      </>
                    )}
                  />
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
                  <Row gutter={[16, 16]} align="middle" className="project-review-switch-row">
                    <Col xs={12} sm={8} lg={4}>
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
                    <Col xs={12} sm={8} lg={4}>
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
                    <Col xs={12} sm={8} lg={4}>
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
                  </Row>
                  {(pushPolicyDraft?.autoFixPreviewEnabled === true || pushPolicyDraft?.triggerOnPush === true) && (
                    <Row gutter={[16, 16]} align="stretch" className="project-review-policy-panels">
                    {pushPolicyDraft?.autoFixPreviewEnabled === true && (
                      <Col xs={24} lg={pushPolicyDraft?.triggerOnPush === true ? 8 : 24}>
                        <div className="project-review-policy-panel">
                          <SettingsCardHeader
                            compact
                            icon={<ThunderboltOutlined />}
                            title="修复预览策略"
                            description="配置自动生成修复预览的风险等级和生成范围，避免不必要的 token 消耗。"
                          />
                          <Select
                            mode="multiple"
                            className="full-width prompt-field"
                            value={normalizeAutoFixPreviewSeverities(pushPolicyDraft?.autoFixPreviewSeverities)}
                            options={AUTO_FIX_PREVIEW_SEVERITY_OPTIONS}
                            onChange={value => updatePushPolicyDraft('autoFixPreviewSeverities', normalizeAutoFixPreviewSeverities(value))}
                          />
                        </div>
                      </Col>
                    )}
                    {pushPolicyDraft?.triggerOnPush === true && (
                      <Col xs={24} lg={pushPolicyDraft?.autoFixPreviewEnabled === true ? 16 : 24}>
                        <div className="project-review-policy-panel">
                          <SettingsCardHeader
                            compact
                            icon={<SafetyCertificateOutlined />}
                            title="Push 审核策略"
                            description="配置 Push 事件进入 AI Review 前必须满足的分支和变更门槛；-1 表示不限制。"
                          />
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
                        </div>
                      </Col>
                    )}
                    </Row>
                  )}
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

  const orderedCollapseItems = [
    'project-target-configs',
    'profile-settings',
    'provider-settings',
    'agent-review-settings',
    'global-settings'
  ]
    .map(key => collapseItems.find(item => item.key === key))
    .filter(Boolean);

  return (
    <TaskWorkspaceShell>
      {contextHolder}
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        <Collapse className="settings-collapse" items={orderedCollapseItems} />
      </Spin>
    </TaskWorkspaceShell>
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
      <TaskWorkspaceShell
        title="任务详情"
        description="任务 ID 无效，无法加载任务详情。"
        actions={(
          <MuiButton variant="outlined" startIcon={<ArrowLeftOutlined />} onClick={() => navigate(backTarget)}>
            返回上一层
          </MuiButton>
        )}
      >
        <Alert type="error" showIcon message="任务 ID 无效" />
      </TaskWorkspaceShell>
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

function GovernanceDiagnosticsShell({ title, description, children, actions, backAction }) {
  const combinedDescription = `${description} 高级诊断页用于解释质量问题、验收能力改动和查看回放记录；统一从顶部“质量治理”下拉框或直接路由进入。`;
  return (
    <Box
      sx={{
        px: { xs: 2, md: 3 },
        py: { xs: 2, md: 2.5 },
        minHeight: 'calc(100dvh - 56px)',
        backgroundColor: '#f6f8fb'
      }}
    >
      <Stack spacing={2.5}>
        <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff', color: '#1f2933' }}>
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { xs: 'stretch', lg: 'center' } }}>
            <Box sx={{ minWidth: 0, flex: '1 1 auto', maxWidth: 820 }}>
              {backAction && (
                <Box sx={{ mb: 0.75 }}>
                  {backAction}
                </Box>
              )}
              <MuiTypography variant="h5" component="h1" sx={{ fontWeight: 750, mb: 0.75 }}>
                {title}
              </MuiTypography>
              <MuiTypography variant="body2" sx={{ color: '#5f6b76' }}>
                {combinedDescription}
              </MuiTypography>
            </Box>
            {actions && (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                useFlexGap
                sx={{
                  flex: '0 0 auto',
                  width: { xs: '100%', lg: 'auto' },
                  maxWidth: { lg: 560 },
                  ml: { lg: 'auto' },
                  flexWrap: 'wrap',
                  justifyContent: 'flex-end',
                  alignItems: { xs: 'stretch', sm: 'center' },
                  '& .MuiButton-root': { minHeight: 36, height: 36, px: 1.75, flex: '0 0 auto' }
                }}
              >
                {actions}
              </Stack>
            )}
          </Stack>
        </Paper>
        {children}
      </Stack>
    </Box>
  );
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
    { title: '最近出现时间', dataIndex: 'recentOccurredAt', width: 210, render: formatDateTime },
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
      title: '推荐依据',
      dataIndex: 'recommendationBasis',
      width: 110,
      render: value => <Tag color={value === 'FREQUENCY_ONLY' ? 'default' : 'purple'}>{recommendationBasisLabel(value)}</Tag>
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
      width: 180,
      render: (_, row) => {
        const feedback = row.feedbackSignals || {};
        const attribution = row.attributionSignals || {};
        return (
          <Space direction="vertical" size={2}>
            <Text strong>{countText(row.score)} / 100</Text>
            <Text type="secondary">
              {RULE_GAP_FEEDBACK_CORRELATION[feedback.correlation] || feedback.correlation || '暂无关联反馈'}
            </Text>
            <Text type="secondary">
              上下文不足 {countText(feedback.contextMissingCount)} · 误判 {countText(feedback.falsePositiveCount)}
            </Text>
            <Text type="secondary">
              已归因 {countText(attribution.attributedCaseCount)} · 已证明 {countText(attribution.causedOrRelatedCount)}
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
          <Descriptions.Item label="推荐依据">{recommendationBasisLabel(row.recommendationBasis)}</Descriptions.Item>
          <Descriptions.Item label="已归因样本">{countText(row.attributionSignals?.attributedCaseCount)}</Descriptions.Item>
          <Descriptions.Item label="已证明相关">{countText(row.attributionSignals?.causedOrRelatedCount)}</Descriptions.Item>
          <Descriptions.Item label="归因类型分布" span={3}>
            <JsonBlock value={row.attributionSignals?.attributionTypeCounts || {}} />
          </Descriptions.Item>
          <Descriptions.Item label="关联裁决分布" span={3}>
            <JsonBlock value={row.attributionSignals?.verdictCounts || {}} />
          </Descriptions.Item>
        </Descriptions>
      </div>
    )
  };

  return (
    <GovernanceDiagnosticsShell
      title="规则缺口诊断"
      description="汇总历史审查中反复缺少的证据，解释 Planner、Retriever 和预算裁剪为什么没有拿到足够上下文。"
    >
      {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
      </Paper>
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
                scroll={{ x: 1400 }}
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
    </GovernanceDiagnosticsShell>
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
    { title: '创建时间', dataIndex: 'createdAt', width: 210, render: formatDateTime },
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
    { title: '更新时间', dataIndex: 'updatedAt', width: 210, render: formatDateTime },
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
    <TaskWorkspaceShell>
      <Paper variant="outlined" className="release-page-shell" sx={{ p: { xs: 1.5, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
      </Paper>
    </TaskWorkspaceShell>
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
    <TaskWorkspaceShell>
      <Paper variant="outlined" className="help-page-shell" sx={{ p: { xs: 1.5, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff', maxWidth: 1180, width: '100%', mx: 'auto' }}>
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
      </Paper>
    </TaskWorkspaceShell>
  );
}

function ReviewQualityDashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [dashboard, setDashboard] = useState(null);
  const [agentObservation, setAgentObservation] = useState(null);
  const [projects, setProjects] = useState([]);
  const [filters, setFilters] = useState({
    projectId: null,
    provider: '',
    profile: '',
    riskType: '',
    verdict: null,
    taskId: '',
    groupId: '',
    startAt: '',
    endAt: '',
    syntheticDemo: false
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
      const observationParams = new URLSearchParams();
      if (nextFilters.taskId?.trim()) observationParams.set('taskId', nextFilters.taskId.trim());
      if (nextFilters.groupId?.trim()) observationParams.set('groupId', nextFilters.groupId.trim());
      if (nextFilters.projectId) observationParams.set('projectId', String(nextFilters.projectId));
      if (nextFilters.profile?.trim()) observationParams.set('profile', nextFilters.profile.trim());
      if (nextFilters.startAt) observationParams.set('startAt', nextFilters.startAt);
      if (nextFilters.endAt) observationParams.set('endAt', nextFilters.endAt);
      if (nextFilters.syntheticDemo) observationParams.set('syntheticDemo', 'true');
      const [data, observation] = await Promise.all([
        fetchApi(`/api/review-quality/dashboard${query ? `?${query}` : ''}`),
        fetchApi(`/api/review-quality/agent-observation?${observationParams.toString()}`)
      ]);
      setDashboard(data);
      setAgentObservation(observation);
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
      verdict: null,
      taskId: '',
      groupId: '',
      startAt: '',
      endAt: '',
      syntheticDemo: false
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
  const metricAccentColors = ['#2563eb', '#ec4899', '#f59e0b', '#8b5cf6', '#06b6d4', '#f97316', '#84cc16'];
  const replaySummary = dashboard?.replaySummary || {};
  const refinementSummary = dashboard?.refinementSummary || {};
  const deterministicSummary = dashboard?.deterministicCheckSummary || {};
  const ruleGapAttributionSummary = dashboard?.ruleGapAttributionSummary || {};
  const acceptanceGateSummary = dashboard?.acceptanceGateSummary || {};
  const agentSampleSummary = agentObservation?.sampleSummary || {};
  const agentAnnotationProgress = agentObservation?.annotationProgress || {};
  const agentFindingSummary = agentObservation?.findingSummary || {};
  const agentReliability = agentObservation?.agentReliability || {};
  const agentExecutionMetrics = agentObservation?.agentExecutionMetrics || {};
  const agentSampleGate = agentObservation?.sampleGate || {};
  const agentObservationCards = [
    { label: '普通 / Agent 样本', value: `${agentSampleSummary.standardSampleCount ?? 0} / ${agentSampleSummary.agentSampleCount ?? 0}` },
    { label: '已配对任务', value: agentSampleSummary.pairedTaskCount ?? 0 },
    { label: '人工标注样本进度', value: `${agentAnnotationProgress.annotationSampleCount ?? 0} / ${agentAnnotationProgress.targetAnnotatedSampleCount ?? 30}` },
    { label: 'finding（普通 / Agent）', value: `${agentFindingSummary.standardFindingCount ?? 0} / ${agentFindingSummary.agentFindingCount ?? 0}` },
    { label: '误判 / 漏报 / 上下文不足', value: `${agentFindingSummary.humanFalsePositiveCount ?? 0} / ${agentFindingSummary.missingFindingCount ?? 0} / ${agentFindingSummary.contextInsufficientCount ?? 0}` },
    { label: 'Agent 成功 / 失败 / fallback', value: `${agentReliability.successCount ?? 0} / ${agentReliability.failureCount ?? 0} / ${agentReliability.fallbackCount ?? 0}` },
    { label: '成功率 / 失败率 / fallback 率', value: `${formatRate(agentReliability.successRate)} / ${formatRate(agentReliability.failureRate)} / ${formatRate(agentReliability.fallbackRate)}` },
    { label: '耗时 p50 / p95', value: `${agentExecutionMetrics.durationMs?.p50 ?? 0} / ${agentExecutionMetrics.durationMs?.p95 ?? 0} ms` },
    { label: 'turn p50 / p95', value: `${agentExecutionMetrics.turnCount?.p50 ?? 0} / ${agentExecutionMetrics.turnCount?.p95 ?? 0}` },
    { label: '工具调用 p50 / p95', value: `${agentExecutionMetrics.toolCallCount?.p50 ?? 0} / ${agentExecutionMetrics.toolCallCount?.p95 ?? 0}` },
    { label: '源码返回 p50 / p95', value: `${agentExecutionMetrics.sourceBytesReturned?.p50 ?? 0} / ${agentExecutionMetrics.sourceBytesReturned?.p95 ?? 0} B` },
    { label: 'Token 输入 / 输出', value: `${agentExecutionMetrics.usageSummary?.inputTokens ?? 0} / ${agentExecutionMetrics.usageSummary?.outputTokens ?? 0}` }
  ];
  const agentComparisonColumns = [
    { title: '任务', dataIndex: 'taskId', width: 90, render: value => <Button type="link" onClick={() => navigate(`${TASK_LIST_ROUTE}/${value}`)}>#{value}</Button> },
    { title: '项目组 / 项目', key: 'scope', ellipsis: true, render: (_, row) => `${row.groupName || row.groupId || '-'} / ${row.projectName || row.projectId || '-'}` },
    { title: 'Profile', dataIndex: 'profile', width: 180, ellipsis: true },
    { title: '普通 / Agent 结果', key: 'results', width: 130, render: (_, row) => `${row.standardResultCount ?? 0} / ${row.agentResultCount ?? 0}` },
    { title: 'finding（普通 / Agent）', key: 'findings', width: 155, render: (_, row) => `${row.standardFindingCount ?? 0} / ${row.agentFindingCount ?? 0}` },
    { title: '人工标注', dataIndex: 'annotationCount', width: 95, render: value => value ?? 0 },
    { title: 'Agent 状态', dataIndex: 'agentStatus', width: 120, render: value => value ? <Tag color={value === 'SUCCEEDED' ? 'green' : 'red'}>{value}</Tag> : '-' },
    { title: 'fallback', dataIndex: 'fallbackTriggered', width: 90, render: value => <Tag color={value ? 'orange' : 'default'}>{value ? '是' : '否'}</Tag> },
    { title: '耗时', dataIndex: 'durationMs', width: 100, render: value => value == null ? '-' : `${value} ms` },
    { title: 'turn / tool', key: 'tools', width: 110, render: (_, row) => `${row.turnCount ?? 0} / ${row.toolCallCount ?? 0}` },
    { title: '源码返回', dataIndex: 'sourceBytesReturned', width: 110, render: value => value == null ? '-' : `${value} B` }
  ];
  const exportAgentObservation = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchApi('/api/review-quality/agent-observation/export', {
        method: 'POST',
        body: JSON.stringify({
          confirmation: 'SANITIZED_SUMMARY_ONLY',
          filters: {
            taskId: filters.taskId || null,
            groupId: filters.groupId || null,
            projectId: filters.projectId || null,
            profile: filters.profile || null,
            startAt: filters.startAt || null,
            endAt: filters.endAt || null,
            syntheticDemo: filters.syntheticDemo
          }
        })
      });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `agent-review-observation-${Date.now()}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      message.success('已导出强制脱敏的阶段 3A 对照摘要');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  const governanceSummaryRows = [
    { label: '回放 item', value: replaySummary.itemCount ?? 0 },
    { label: '回放完成 / 失败', value: `${replaySummary.completedCount ?? 0} / ${replaySummary.failedCount ?? 0}` },
    { label: '回放平均耗时', value: `${replaySummary.durationMsAvg ?? 0} ms` },
    { label: '补证据完成 / 失败', value: `${refinementSummary.completedCount ?? 0} / ${refinementSummary.failedCount ?? 0}` },
    { label: '确定性检查 run', value: deterministicSummary.runCount ?? 0 },
    { label: '确定性命中', value: deterministicSummary.findingCount ?? 0 },
    {
      label: '规则缺口已归因 / 未归因',
      value: `${ruleGapAttributionSummary.attributedCaseCount ?? 0} / ${ruleGapAttributionSummary.unattributedCaseCount ?? 0}`
    },
    { label: '规则缺口已证明相关', value: ruleGapAttributionSummary.causedOrRelatedCount ?? 0 },
    { label: '验收记录数', value: acceptanceGateSummary.recordCount ?? 0 },
    {
      label: '最近验收状态',
      value: acceptanceGateSummary.latestStatus ? (
        <Tag color={acceptanceGateStatusColor(acceptanceGateSummary.latestStatus)}>
          {acceptanceGateStatusLabel(acceptanceGateSummary.latestStatus)}
        </Tag>
      ) : '-'
    }
  ];
  const scopeNotes = [
    { label: '补证据范围', value: refinementSummary.scopeNote },
    { label: '确定性检查范围', value: deterministicSummary.scopeNote },
    { label: '验收记录范围', value: acceptanceGateSummary.scopeNote }
  ].filter(item => item.value);

  return (
    <Box
      sx={{
        px: { xs: 2, md: 3 },
        py: { xs: 2, md: 2.5 },
        minHeight: 'calc(100dvh - 56px)',
        backgroundColor: '#f6f8fb'
      }}
    >
      <Stack spacing={2.5}>
        <Paper
          variant="outlined"
          sx={{
            p: { xs: 2, md: 2.25 },
            borderRadius: 1,
            backgroundColor: '#ffffff',
            color: '#1f2933'
          }}
        >
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { xs: 'stretch', lg: 'center' } }}>
            <Box sx={{ minWidth: 0, flex: '1 1 auto', maxWidth: 760 }}>
              <MuiTypography variant="h5" component="h1" sx={{ fontWeight: 750, mb: 0.75 }}>
                质量看板
              </MuiTypography>
              <MuiTypography variant="body2" sx={{ color: '#5f6b76' }}>
                面向管理员的 Review 质量治理视图，聚合评估样本、补证据、确定性检查、回放和改动记录。
              </MuiTypography>
            </Box>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
          <Stack spacing={2}>
            <MuiTypography variant="subtitle1" sx={{ fontWeight: 700 }}>
              筛选范围
            </MuiTypography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                  lg: '1.1fr repeat(4, minmax(136px, 1fr)) auto auto'
                },
                gap: 1.25,
                alignItems: 'center'
              }}
            >
              <FormControl size="small" fullWidth>
                <InputLabel id="review-quality-project-label">项目</InputLabel>
                <MuiSelect
                  labelId="review-quality-project-label"
                  label="项目"
                  value={filters.projectId || ''}
                  onChange={event => updateFilter('projectId', event.target.value || null)}
                >
                  <MenuItem value="">全部项目</MenuItem>
                  {projectOptions.map(option => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </MuiSelect>
              </FormControl>
              <TextField
                size="small"
                label="Provider"
                value={filters.provider}
                onChange={event => updateFilter('provider', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load();
                }}
              />
              <TextField
                size="small"
                label="Profile"
                value={filters.profile}
                onChange={event => updateFilter('profile', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load();
                }}
              />
              <TextField
                size="small"
                label="风险类型"
                value={filters.riskType}
                onChange={event => updateFilter('riskType', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load();
                }}
              />
              <FormControl size="small" fullWidth>
                <InputLabel id="review-quality-verdict-label">人工裁决</InputLabel>
                <MuiSelect
                  labelId="review-quality-verdict-label"
                  label="人工裁决"
                  value={filters.verdict || ''}
                  onChange={event => updateFilter('verdict', event.target.value || null)}
                >
                  <MenuItem value="">全部裁决</MenuItem>
                  {EVALUATION_CASE_VERDICT_OPTIONS.map(option => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </MuiSelect>
              </FormControl>
              <MuiButton size="small" variant="contained" startIcon={<SearchOutlined />} onClick={() => load()} sx={{ minHeight: 40 }}>
                搜索
              </MuiButton>
              <MuiButton size="small" variant="outlined" onClick={resetFilters} sx={{ minHeight: 40 }}>
                重置
              </MuiButton>
            </Box>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(150px, 1fr)) auto' },
                gap: 1.25,
                alignItems: 'center'
              }}
            >
              <TextField size="small" label="任务 ID（Agent 观察）" value={filters.taskId} onChange={event => updateFilter('taskId', event.target.value)} />
              <TextField size="small" label="项目组 ID（Agent 观察）" value={filters.groupId} onChange={event => updateFilter('groupId', event.target.value)} />
              <TextField size="small" label="开始时间" type="datetime-local" value={filters.startAt} onChange={event => updateFilter('startAt', event.target.value)} InputLabelProps={{ shrink: true }} />
              <TextField size="small" label="结束时间" type="datetime-local" value={filters.endAt} onChange={event => updateFilter('endAt', event.target.value)} InputLabelProps={{ shrink: true }} />
              <Stack direction="row" spacing={1} sx={{ minHeight: 40, alignItems: 'center' }}>
                <Switch
                  checked={filters.syntheticDemo}
                  onChange={checked => {
                    setFilters(current => ({
                      ...current,
                      syntheticDemo: checked,
                      projectId: checked ? null : current.projectId,
                      profile: checked ? '' : current.profile,
                      taskId: checked ? '' : current.taskId,
                      groupId: checked ? '' : current.groupId
                    }));
                  }}
                />
                <MuiTypography variant="body2">合成 demo（不调用模型）</MuiTypography>
              </Stack>
            </Box>
          </Stack>
        </Paper>

        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}

        <Spin spinning={loading}>
          <Stack spacing={2.5}>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                  md: 'repeat(3, minmax(0, 1fr))',
                  xl: 'repeat(7, minmax(0, 1fr))'
                },
                gap: 1.5
              }}
            >
              {metricCards.map((item, index) => (
                <MuiCard
                  key={item.label}
                  variant="outlined"
                  sx={{
                    minHeight: 98,
                    borderRadius: 1,
                    borderTop: `4px solid ${metricAccentColors[index % metricAccentColors.length]}`,
                    backgroundColor: '#ffffff',
                    color: '#1f2933'
                  }}
                >
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    <MuiTypography
                      variant="body2"
                      sx={{
                        color: '#5f6b76',
                        mb: 0.75
                      }}
                    >
                      {item.label}
                    </MuiTypography>
                    <MuiTypography variant="h6" component="div" sx={{ color: '#1f2933', fontWeight: 760, overflowWrap: 'anywhere' }}>
                      {item.value}
                    </MuiTypography>
                  </CardContent>
                </MuiCard>
              ))}
            </Box>

            <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
              <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5} sx={{ mb: 2, justifyContent: 'space-between', alignItems: { xs: 'stretch', lg: 'center' } }}>
                <Box>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                    <MuiTypography variant="h6" sx={{ fontWeight: 720 }}>Agent Review 生产观察（阶段 3A）</MuiTypography>
                    <Tag color={agentObservation?.dataMode === 'SYNTHETIC_DEMO' ? 'purple' : 'blue'}>{agentObservation?.dataMode || 'PRODUCTION_OBSERVATION'}</Tag>
                    <Tag color={agentSampleGate.status === 'INSUFFICIENT_SAMPLE' ? 'orange' : 'blue'}>{agentSampleGate.status || 'INSUFFICIENT_SAMPLE'}</Tag>
                  </Stack>
                  <MuiTypography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    只观察和收集数据，不计算 Agent 准确性或扩大范围结论。合成 demo 不含真实模型调用。
                  </MuiTypography>
                </Box>
                <MuiButton variant="outlined" startIcon={<ExportOutlined />} onClick={exportAgentObservation}>
                  导出脱敏摘要
                </MuiButton>
              </Stack>
              <MuiAlert severity={agentSampleGate.status === 'INSUFFICIENT_SAMPLE' ? 'warning' : 'info'} variant="outlined" sx={{ mb: 2 }}>
                {agentSampleGate.message || '人工标注样本不足 30 条，不计算扩大范围结论。'}
              </MuiAlert>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1 }}>
                {agentObservationCards.map(item => (
                  <Box key={item.label} sx={{ p: 1.5, borderRadius: 2, border: theme => `1px solid ${theme.palette.divider}`, backgroundColor: '#f8fafc' }}>
                    <MuiTypography variant="caption" color="text.secondary">{item.label}</MuiTypography>
                    <MuiTypography variant="body1" sx={{ fontWeight: 700, mt: 0.5, overflowWrap: 'anywhere' }}>{item.value}</MuiTypography>
                  </Box>
                ))}
              </Box>
              <MuiTypography variant="subtitle1" sx={{ fontWeight: 700, mt: 2.5, mb: 1 }}>任务级 STANDARD / AGENT 对照</MuiTypography>
              <Table
                rowKey="taskId"
                size="small"
                columns={agentComparisonColumns}
                dataSource={agentObservation?.comparisons || []}
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                scroll={{ x: 1300 }}
              />
            </Paper>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(280px, 0.8fr) minmax(0, 1.4fr)' }, gap: 1.5 }}>
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
                <MuiTypography variant="h6" sx={{ fontWeight: 720, mb: 2 }}>
                  Verdict 分布
                </MuiTypography>
                <Table
                  rowKey="verdict"
                  size="small"
                  columns={verdictColumns}
                  dataSource={dashboard?.verdictDistribution || []}
                  pagination={false}
                />
              </Paper>

              <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mb: 2, justifyContent: 'space-between', alignItems: { xs: 'flex-start', md: 'center' } }}>
                  <Box>
                    <MuiTypography variant="h6" sx={{ fontWeight: 720 }}>
                      治理摘要
                    </MuiTypography>
                    <MuiTypography variant="body2" color="text.secondary">
                      回放、补证据、确定性检查、规则缺口和验收记录的辅助诊断。
                    </MuiTypography>
                  </Box>
                  <Chip
                    size="small"
                    color={acceptanceGateSummary.latestStatus ? 'primary' : 'default'}
                    variant="outlined"
                    label={acceptanceGateSummary.latestStatus ? acceptanceGateStatusLabel(acceptanceGateSummary.latestStatus) : '暂无最近验收'}
                  />
                </Stack>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
                    gap: 1,
                    mb: scopeNotes.length ? 2 : 0
                  }}
                >
                  {governanceSummaryRows.map(item => (
                    <Box
                      key={item.label}
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        border: theme => `1px solid ${theme.palette.divider}`,
                        backgroundColor: '#f8fafc'
                      }}
                    >
                      <MuiTypography variant="caption" sx={{ color: '#5f6b76' }}>
                        {item.label}
                      </MuiTypography>
                      <MuiTypography variant="body1" sx={{ color: '#1f2933', fontWeight: 650, mt: 0.5, overflowWrap: 'anywhere' }}>
                        {item.value}
                      </MuiTypography>
                    </Box>
                  ))}
                </Box>
                {scopeNotes.length > 0 && (
                  <Stack spacing={1}>
                    {scopeNotes.map(item => (
                      <MuiAlert key={item.label} severity="info" variant="outlined">
                        <strong>{item.label}：</strong>{item.value}
                      </MuiAlert>
                    ))}
                  </Stack>
                )}
              </Paper>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' }, gap: 1.5 }}>
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
                <MuiTypography variant="h6" sx={{ fontWeight: 720, mb: 2 }}>
                  规则缺口归因类型
                </MuiTypography>
                <JsonBlock value={ruleGapAttributionSummary.attributionTypeCounts || {}} />
              </Paper>
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
                <MuiTypography variant="h6" sx={{ fontWeight: 720, mb: 2 }}>
                  规则缺口归因关联裁决
                </MuiTypography>
                <JsonBlock value={ruleGapAttributionSummary.verdictCounts || {}} />
              </Paper>
            </Box>

            {[
              { title: '项目维度 Top', data: dashboard?.dimensions?.projects || [] },
              { title: 'Provider 维度 Top', data: dashboard?.dimensions?.providers || [] },
              { title: 'Profile 维度 Top', data: dashboard?.dimensions?.profiles || [] },
              { title: '风险类型维度 Top', data: dashboard?.dimensions?.riskTypes || [] }
            ].map(section => (
              <Paper key={section.title} variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
                <MuiTypography variant="h6" sx={{ fontWeight: 720, mb: 2 }}>
                  {section.title}
                </MuiTypography>
                <Table
                  rowKey="key"
                  size="small"
                  columns={dimensionColumns}
                  dataSource={section.data}
                  pagination={false}
                  scroll={{ x: 1020 }}
                />
              </Paper>
            ))}
          </Stack>
        </Spin>
      </Stack>
    </Box>
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
  const [attributionModalOpen, setAttributionModalOpen] = useState(false);
  const [attributionSubmitting, setAttributionSubmitting] = useState(false);
  const [editingAttributionCase, setEditingAttributionCase] = useState(null);
  const [attributionDraft, setAttributionDraft] = useState({
    attributionType: null,
    ruleGapSummary: [],
    comment: '',
    attributedBy: ''
  });

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

  const openAttributionModal = async row => {
    setEditingAttributionCase(row);
    setAttributionModalOpen(true);
    const fallback = row.ruleGapAttribution || {};
    setAttributionDraft({
      attributionType: fallback.attributionType || null,
      ruleGapSummary: safeArray(fallback.ruleGapSummary),
      comment: fallback.comment || '',
      attributedBy: fallback.attributedBy || ''
    });
    try {
      const data = await fetchApi(`/api/evaluation-cases/${row.id}/rule-gap-attribution`);
      setAttributionDraft({
        attributionType: data.attributionType || null,
        ruleGapSummary: safeArray(data.ruleGapSummary),
        comment: data.comment || '',
        attributedBy: data.attributedBy || ''
      });
    } catch (err) {
      message.error(err.message);
    }
  };

  const saveAttribution = async () => {
    if (!editingAttributionCase?.id) return;
    setAttributionSubmitting(true);
    try {
      await fetchApi(`/api/evaluation-cases/${editingAttributionCase.id}/rule-gap-attribution`, {
        method: 'PUT',
        body: JSON.stringify(attributionDraft)
      });
      message.success('规则缺口归因已保存');
      setAttributionModalOpen(false);
      load();
    } catch (err) {
      message.error(err.message);
    } finally {
      setAttributionSubmitting(false);
    }
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
      title: '规则缺口归因',
      dataIndex: 'ruleGapAttribution',
      width: 150,
      render: value => <Tag color={ruleGapAttributionColor(value?.attributionType)}>{ruleGapAttributionLabel(value?.attributionType)}</Tag>
    },
    {
      title: 'Finding',
      dataIndex: 'itemSnapshot',
      width: 260,
      ellipsis: true,
      render: (value, row) => value?.title || row.findingId || row.fingerprint || '-'
    },
    { title: '人工说明', dataIndex: 'humanComment', ellipsis: true, render: value => value || '-' },
    { title: '创建时间', dataIndex: 'createdAt', width: 210, render: formatDateTime },
    {
      title: '操作',
      width: 120,
      fixed: 'right',
      render: (_, row) => <Button size="small" onClick={() => openAttributionModal(row)}>编辑归因</Button>
    }
  ];

  return (
    <Box
      sx={{
        px: { xs: 2, md: 3 },
        py: { xs: 2, md: 2.5 },
        minHeight: 'calc(100dvh - 56px)',
        backgroundColor: '#f6f8fb'
      }}
    >
      <Stack spacing={2.5}>
        <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff', color: '#1f2933' }}>
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { xs: 'stretch', lg: 'center' } }}>
            <Box sx={{ minWidth: 0, flex: '1 1 auto', maxWidth: 760 }}>
              <MuiTypography variant="h5" component="h1" sx={{ fontWeight: 750, mb: 0.75 }}>
                评估样本
              </MuiTypography>
              <MuiTypography variant="body2" sx={{ color: '#5f6b76' }}>
                查看从 AI finding 或人工补充沉淀的 Review 质量评估样本。
              </MuiTypography>
            </Box>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.25 }, borderRadius: 1, backgroundColor: '#ffffff' }}>
          <Stack spacing={2}>
            <MuiTypography variant="subtitle1" sx={{ color: '#1f2933', fontWeight: 700 }}>
              筛选范围
            </MuiTypography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                  lg: '1.1fr repeat(4, minmax(136px, 1fr)) auto auto'
                },
                gap: 1.25,
                alignItems: 'center'
              }}
            >
              <FormControl size="small" fullWidth>
                <InputLabel id="evaluation-case-project-label">项目</InputLabel>
                <MuiSelect
                  labelId="evaluation-case-project-label"
                  label="项目"
                  value={filters.projectId || ''}
                  onChange={event => updateFilter('projectId', event.target.value || null)}
                >
                  <MenuItem value="">全部项目</MenuItem>
                  {projectOptions.map(option => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </MuiSelect>
              </FormControl>
              <TextField
                size="small"
                label="Provider"
                value={filters.provider}
                onChange={event => updateFilter('provider', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load({ pageNo: 1 });
                }}
              />
              <TextField
                size="small"
                label="Profile"
                value={filters.profile}
                onChange={event => updateFilter('profile', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load({ pageNo: 1 });
                }}
              />
              <TextField
                size="small"
                label="风险类型"
                value={filters.riskType}
                onChange={event => updateFilter('riskType', event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') load({ pageNo: 1 });
                }}
              />
              <FormControl size="small" fullWidth>
                <InputLabel id="evaluation-case-verdict-label">人工裁决</InputLabel>
                <MuiSelect
                  labelId="evaluation-case-verdict-label"
                  label="人工裁决"
                  value={filters.verdict || ''}
                  onChange={event => updateFilter('verdict', event.target.value || null)}
                >
                  <MenuItem value="">全部裁决</MenuItem>
                  {EVALUATION_CASE_VERDICT_OPTIONS.map(option => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </MuiSelect>
              </FormControl>
              <MuiButton size="small" variant="contained" startIcon={<SearchOutlined />} onClick={() => load({ pageNo: 1 })} sx={{ minHeight: 40 }}>
                搜索
              </MuiButton>
              <MuiButton size="small" variant="outlined" onClick={resetFilters} sx={{ minHeight: 40 }}>
                重置
              </MuiButton>
            </Box>
          </Stack>
        </Paper>

        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}

        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mb: 2, justifyContent: 'space-between', alignItems: { xs: 'flex-start', md: 'center' } }}>
            <Box>
              <MuiTypography variant="h6" sx={{ color: '#1f2933', fontWeight: 720 }}>
                样本列表
              </MuiTypography>
              <MuiTypography variant="body2" sx={{ color: '#5f6b76' }}>
                保留表格视图用于扫描、筛选和横向比较。
              </MuiTypography>
            </Box>
            <Chip size="small" variant="outlined" color="primary" label={`共 ${pagination.total || 0} 条`} />
          </Stack>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            tableLayout="fixed"
            scroll={{ x: 2190 }}
            pagination={{
              current: pagination.pageNo,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showTotal: total => `共 ${total} 条`,
              onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
            }}
          />
        </Paper>

        <Dialog
          open={attributionModalOpen}
          onClose={() => setAttributionModalOpen(false)}
          fullWidth
          maxWidth="md"
          PaperProps={{ sx: { borderRadius: 1 } }}
        >
          <DialogTitle sx={{ pb: 1 }}>
            <MuiTypography variant="h6" component="div" sx={{ color: '#1f2933', fontWeight: 750 }}>
              编辑规则缺口归因
            </MuiTypography>
            <MuiTypography variant="body2" sx={{ color: '#5f6b76', mt: 0.5 }}>
              归因只用于质量诊断，不会修改原 AI Review 结果、Prompt 或项目策略。
            </MuiTypography>
          </DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <MuiAlert severity="info" variant="outlined">
                不会触发 Retriever、门禁、自动降级或自动忽略 finding。
              </MuiAlert>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1
                }}
              >
                {[
                  { label: 'Case ID', value: editingAttributionCase?.id || '-' },
                  { label: '裁决', value: evaluationCaseVerdictLabel(editingAttributionCase?.verdict) },
                  { label: '任务', value: editingAttributionCase?.taskId || '-' },
                  { label: 'Review Key', value: editingAttributionCase?.reviewKey || '-' }
                ].map(item => (
                  <Box
                    key={item.label}
                    sx={{
                      p: 1.5,
                      borderRadius: 1,
                      border: theme => `1px solid ${theme.palette.divider}`,
                      backgroundColor: '#f8fafc'
                    }}
                  >
                    <MuiTypography variant="caption" sx={{ color: '#5f6b76' }}>{item.label}</MuiTypography>
                    <MuiTypography variant="body2" sx={{ color: '#1f2933', fontWeight: 650, mt: 0.5, overflowWrap: 'anywhere' }}>
                      {item.value}
                    </MuiTypography>
                  </Box>
                ))}
              </Box>
              <FormControl size="small" fullWidth>
                <InputLabel id="rule-gap-attribution-type-label">归因类型</InputLabel>
                <MuiSelect
                  labelId="rule-gap-attribution-type-label"
                  label="归因类型"
                  value={attributionDraft.attributionType || ''}
                  onChange={event => setAttributionDraft(current => ({ ...current, attributionType: event.target.value || null }))}
                >
                  <MenuItem value="">未选择</MenuItem>
                  {RULE_GAP_ATTRIBUTION_OPTIONS.map(option => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </MuiSelect>
              </FormControl>
              <TextField
                size="small"
                label="归因人"
                placeholder="例如 reviewer / admin"
                value={attributionDraft.attributedBy}
                onChange={event => setAttributionDraft(current => ({ ...current, attributedBy: event.target.value }))}
              />
              <TextField
                size="small"
                multiline
                minRows={3}
                label="归因说明"
                inputProps={{ maxLength: 4000 }}
                value={attributionDraft.comment}
                onChange={event => setAttributionDraft(current => ({ ...current, comment: event.target.value }))}
              />
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                <MuiTypography variant="subtitle1" sx={{ color: '#1f2933', fontWeight: 700, mb: 1.5 }}>
                  安全 Rule Gap 摘要
                </MuiTypography>
                {safeArray(attributionDraft.ruleGapSummary).length ? (
                  <Table
                    rowKey={(row, index) => row.summaryKey || `${row.gapType}-${row.signal}-${index}`}
                    size="small"
                    pagination={false}
                    columns={[
                      { title: '缺口类型', dataIndex: 'gapType', width: 190, render: value => <Tag color="orange">{value || '-'}</Tag> },
                      { title: 'Signal', dataIndex: 'signal', width: 180, ellipsis: true },
                      { title: 'Requested Context', dataIndex: 'requestedContext', width: 180, ellipsis: true },
                      { title: '建议能力', dataIndex: 'suggestedCapability', ellipsis: true }
                    ]}
                    dataSource={safeArray(attributionDraft.ruleGapSummary)}
                    scroll={{ x: 760 }}
                  />
                ) : (
                  <Empty description="暂无 rule gap 摘要；可先从有上下文准备阶段记录的 AI finding 创建样本" />
                )}
              </Paper>
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, py: 1.5 }}>
            <MuiButton variant="outlined" onClick={() => setAttributionModalOpen(false)}>
              取消
            </MuiButton>
            <MuiButton variant="contained" onClick={saveAttribution} disabled={attributionSubmitting}>
              保存归因
            </MuiButton>
          </DialogActions>
        </Dialog>
      </Stack>
    </Box>
  );
}

function AcceptanceGatesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const route = currentRoute(location);
  const [items, setItems] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [filters, setFilters] = useState({
    projectId: null,
    changeType: null,
    status: null,
    provider: '',
    profile: '',
    riskType: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingGate, setEditingGate] = useState(null);
  const [draft, setDraft] = useState(() => emptyAcceptanceGateDraft());

  const projectOptions = useMemo(
    () => projects.map(project => ({ label: project.name, value: project.id })),
    [projects]
  );

  const loadProjects = async () => {
    try {
      const data = await fetchApi('/api/projects?includeDisabled=true&pageSize=500');
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
      if (nextFilters.changeType) params.set('changeType', nextFilters.changeType);
      if (nextFilters.status) params.set('status', nextFilters.status);
      if (nextFilters.provider?.trim()) params.set('provider', nextFilters.provider.trim());
      if (nextFilters.profile?.trim()) params.set('profile', nextFilters.profile.trim());
      if (nextFilters.riskType?.trim()) params.set('riskType', nextFilters.riskType.trim());
      const data = await fetchApi(`/api/review-quality/acceptance-gates?${params.toString()}`);
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
      changeType: null,
      status: null,
      provider: '',
      profile: '',
      riskType: ''
    };
    setFilters(nextFilters);
    load({ pageNo: 1, nextFilters });
  };

  const openCreate = () => {
    setEditingGate(null);
    setDraft(emptyAcceptanceGateDraft());
    setModalOpen(true);
  };

  const openEdit = async row => {
    setEditingGate(row);
    setModalOpen(true);
    setDraft(emptyAcceptanceGateDraft(row));
    try {
      const detail = await fetchApi(`/api/review-quality/acceptance-gates/${row.id}`);
      setDraft(emptyAcceptanceGateDraft(detail));
    } catch (err) {
      message.error(err.message);
    }
  };

  const saveGate = async () => {
    if (!draft.projectId || !draft.title.trim()) {
      message.error('项目和标题必填');
      return;
    }
    setSubmitting(true);
    try {
      const payload = acceptanceGateDraftToPayload(draft);
      const path = editingGate?.id
        ? `/api/review-quality/acceptance-gates/${editingGate.id}`
        : '/api/review-quality/acceptance-gates';
      await fetchApi(path, {
        method: editingGate?.id ? 'PUT' : 'POST',
        body: JSON.stringify(payload)
      });
      message.success(editingGate?.id ? '验收记录已更新' : '验收记录已创建');
      setModalOpen(false);
      load({ pageNo: 1 });
    } catch (err) {
      message.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '标题',
      dataIndex: 'title',
      width: 240,
      ellipsis: true,
      render: (value, row) => (
        <Button type="link" onClick={() => navigate(`${ACCEPTANCE_GATES_ROUTE}/${row.id}`, { state: { from: route } })}>
          {value || `Gate #${row.id}`}
        </Button>
      )
    },
    { title: '项目', dataIndex: 'projectName', width: 180, ellipsis: true, render: value => value || '-' },
    { title: '改动类型', dataIndex: 'changeType', width: 130, render: value => <Tag>{acceptanceGateChangeTypeLabel(value)}</Tag> },
    { title: '状态', dataIndex: 'status', width: 120, render: value => <Tag color={acceptanceGateStatusColor(value)}>{acceptanceGateStatusLabel(value)}</Tag> },
    { title: 'Provider', dataIndex: 'provider', width: 120, ellipsis: true, render: value => value || '-' },
    { title: 'Profile', dataIndex: 'profile', width: 190, ellipsis: true, render: value => value || '-' },
    { title: '风险类型', dataIndex: 'riskType', width: 130, render: value => value ? <Tag color="blue">{categoryLabel(value)}</Tag> : '-' },
    { title: '关联样本', dataIndex: 'evaluationCaseCount', width: 100, render: value => value ?? 0 },
    { title: '关联 Run', dataIndex: 'evaluationRunCount', width: 100, render: value => value ?? 0 },
    {
      title: '核心 Delta',
      dataIndex: 'coreDelta',
      width: 260,
      render: value => (
        <Space size={4} wrap>
          {value?.resultStatus && <Tag color={acceptanceGateResultStatusColor(value.resultStatus)}>{acceptanceGateResultStatusLabel(value.resultStatus)}</Tag>}
          {value?.falsePositiveDelta != null && <Tag>误判 {value.falsePositiveDelta}</Tag>}
          {value?.contextMissingDelta != null && <Tag>上下文 {value.contextMissingDelta}</Tag>}
          {value?.missingFindingDelta != null && <Tag>漏报 {value.missingFindingDelta}</Tag>}
          {value?.findingCountDelta != null && <Tag>Finding {value.findingCountDelta}</Tag>}
        </Space>
      )
    },
    { title: '更新时间', dataIndex: 'updatedAt', width: 210, render: formatDateTime },
    { title: '操作', width: 100, fixed: 'right', render: (_, row) => <Button size="small" onClick={() => openEdit(row)}>编辑</Button> }
  ];

  return (
    <GovernanceDiagnosticsShell
      title="验收记录"
      description="记录规则、Retriever、Prompt、Context Pack、确定性检查或 Provider 改动的人工准入和退出验收。"
      actions={<MuiButton size="small" variant="contained" startIcon={<PlusOutlined />} onClick={openCreate}>新建验收记录</MuiButton>}
    >
        <MuiAlert severity="info" variant="outlined" sx={{ backgroundColor: '#ffffff' }}>
          验收记录不会阻断线上 Review、代码合并或运行时流程，也不会自动修改 Prompt、项目策略或 finding。
        </MuiAlert>
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
              placeholder="改动类型"
              value={filters.changeType || undefined}
              options={ACCEPTANCE_GATE_CHANGE_TYPE_OPTIONS}
              onChange={value => updateFilter('changeType', value)}
            />
            <Select
              allowClear
              className="filter-select"
              placeholder="状态"
              value={filters.status || undefined}
              options={ACCEPTANCE_GATE_STATUS_OPTIONS}
              onChange={value => updateFilter('status', value)}
            />
            <Input allowClear className="filter-input" placeholder="Provider" value={filters.provider} onChange={event => updateFilter('provider', event.target.value)} onPressEnter={() => load({ pageNo: 1 })} />
            <Input allowClear className="filter-input" placeholder="Profile" value={filters.profile} onChange={event => updateFilter('profile', event.target.value)} onPressEnter={() => load({ pageNo: 1 })} />
            <Input allowClear className="filter-input" placeholder="风险类型" value={filters.riskType} onChange={event => updateFilter('riskType', event.target.value)} onPressEnter={() => load({ pageNo: 1 })} />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => load({ pageNo: 1 })}>搜索</Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Paper>
        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            tableLayout="fixed"
            scroll={{ x: 2040 }}
            pagination={{
              current: pagination.pageNo,
              pageSize: pagination.pageSize,
              total: pagination.total,
              showTotal: total => `共 ${total} 条`,
              onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
            }}
          />
        </Paper>
        <AcceptanceGateModal
          open={modalOpen}
          projects={projectOptions}
          draft={draft}
          setDraft={setDraft}
          editing={Boolean(editingGate?.id)}
          submitting={submitting}
          onCancel={() => setModalOpen(false)}
          onOk={saveGate}
        />
    </GovernanceDiagnosticsShell>
  );
}

function AcceptanceGateModal({ open, projects, draft, setDraft, editing, submitting, onCancel, onOk }) {
  const update = (field, value) => setDraft(current => ({ ...current, [field]: value }));
  const updateAdmission = (field, value) => setDraft(current => ({ ...current, admission: { ...current.admission, [field]: value } }));
  const updateExit = (field, value) => setDraft(current => ({ ...current, exit: { ...current.exit, [field]: value } }));

  return (
    <Modal
      title={editing ? '编辑验收记录' : '新建验收记录'}
      open={open}
      onCancel={onCancel}
      onOk={onOk}
      confirmLoading={submitting}
      okText={editing ? '保存' : '创建'}
      cancelText="取消"
      width={900}
    >
      <Space direction="vertical" size="middle" className="full-width">
        <Row gutter={12}>
          <Col xs={24} md={12}>
            <Text type="secondary">项目</Text>
            <Select showSearch optionFilterProp="label" className="full-width" value={draft.projectId || undefined} options={projects} onChange={value => update('projectId', value)} />
          </Col>
          <Col xs={24} md={12}>
            <Text type="secondary">标题</Text>
            <Input value={draft.title} onChange={event => update('title', event.target.value)} placeholder="例如：补缓存 Retriever 准入" />
          </Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} md={8}>
            <Text type="secondary">改动类型</Text>
            <Select className="full-width" value={draft.changeType} options={ACCEPTANCE_GATE_CHANGE_TYPE_OPTIONS} onChange={value => update('changeType', value)} />
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">状态</Text>
            <Select className="full-width" value={draft.status} options={ACCEPTANCE_GATE_STATUS_OPTIONS} onChange={value => update('status', value)} />
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary">退出结果</Text>
            <Select allowClear className="full-width" value={draft.exit.resultStatus || undefined} options={ACCEPTANCE_GATE_RESULT_STATUS_OPTIONS} onChange={value => updateExit('resultStatus', value || null)} />
          </Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} md={8}><Text type="secondary">Provider</Text><Input value={draft.provider} onChange={event => update('provider', event.target.value)} /></Col>
          <Col xs={24} md={8}><Text type="secondary">Profile</Text><Input value={draft.profile} onChange={event => update('profile', event.target.value)} /></Col>
          <Col xs={24} md={8}><Text type="secondary">风险类型</Text><Input value={draft.riskType} onChange={event => update('riskType', event.target.value)} /></Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} md={12}><Text type="secondary">关联 Evaluation Case IDs</Text><Input value={draft.evaluationCaseIdsText} onChange={event => update('evaluationCaseIdsText', event.target.value)} placeholder="例如：1,2,3" /></Col>
          <Col xs={24} md={12}><Text type="secondary">关联 Evaluation Run IDs</Text><Input value={draft.evaluationRunIdsText} onChange={event => update('evaluationRunIdsText', event.target.value)} placeholder="例如：10,11" /></Col>
        </Row>
        <Card size="small" title="准入信息">
          <Space direction="vertical" className="full-width">
            <Input.TextArea rows={2} placeholder="问题说明" value={draft.admission.problemStatement} onChange={event => updateAdmission('problemStatement', event.target.value)} />
            <Input.TextArea rows={2} placeholder="预期收益" value={draft.admission.expectedBenefit} onChange={event => updateAdmission('expectedBenefit', event.target.value)} />
            <Input.TextArea rows={2} placeholder="风险评估" value={draft.admission.riskAssessment} onChange={event => updateAdmission('riskAssessment', event.target.value)} />
            <Input.TextArea rows={2} placeholder="成本估算" value={draft.admission.costEstimate} onChange={event => updateAdmission('costEstimate', event.target.value)} />
            <Row gutter={12}>
              <Col xs={24} md={12}><Input placeholder="决策人" value={draft.admission.decisionBy} onChange={event => updateAdmission('decisionBy', event.target.value)} /></Col>
              <Col xs={24} md={12}><Input placeholder="决策时间，例如 2026-07-02T10:00:00+08:00" value={draft.admission.decisionAt} onChange={event => updateAdmission('decisionAt', event.target.value)} /></Col>
            </Row>
          </Space>
        </Card>
        <Card size="small" title="退出结果">
          <Row gutter={12}>
            <Col xs={12} md={6}><Text type="secondary">误判 Delta</Text><InputNumber className="full-width" value={draft.exit.falsePositiveDelta} onChange={value => updateExit('falsePositiveDelta', value)} /></Col>
            <Col xs={12} md={6}><Text type="secondary">上下文 Delta</Text><InputNumber className="full-width" value={draft.exit.contextMissingDelta} onChange={value => updateExit('contextMissingDelta', value)} /></Col>
            <Col xs={12} md={6}><Text type="secondary">漏报 Delta</Text><InputNumber className="full-width" value={draft.exit.missingFindingDelta} onChange={value => updateExit('missingFindingDelta', value)} /></Col>
            <Col xs={12} md={6}><Text type="secondary">Finding Delta</Text><InputNumber className="full-width" value={draft.exit.findingCountDelta} onChange={value => updateExit('findingCountDelta', value)} /></Col>
          </Row>
          <Row gutter={12} className="section-gap">
            <Col xs={12} md={6}><Text type="secondary">耗时 Delta ms</Text><InputNumber className="full-width" value={draft.exit.durationDeltaMs} onChange={value => updateExit('durationDeltaMs', value)} /></Col>
            <Col xs={12} md={6}><Text type="secondary">Token 成本 Delta</Text><InputNumber className="full-width" value={draft.exit.tokenCostDelta} onChange={value => updateExit('tokenCostDelta', value)} /></Col>
            <Col xs={24} md={6}><Text type="secondary">决策人</Text><Input value={draft.exit.decidedBy} onChange={event => updateExit('decidedBy', event.target.value)} /></Col>
            <Col xs={24} md={6}><Text type="secondary">决策时间</Text><Input value={draft.exit.decidedAt} onChange={event => updateExit('decidedAt', event.target.value)} /></Col>
          </Row>
          <Input.TextArea className="section-gap" rows={2} placeholder="退出说明" value={draft.exit.notes} onChange={event => updateExit('notes', event.target.value)} />
        </Card>
        <Card size="small" title="Rule Gap 安全摘要 JSON">
          <Input.TextArea rows={4} value={draft.ruleGapSummaryText} onChange={event => update('ruleGapSummaryText', event.target.value)} placeholder='[{"gapType":"UNSUPPORTED_PLANNER_SIGNAL","signal":"CACHE_WRITE_DELETE_CHANGED","requestedContext":"CACHE_USAGE_CONTEXT","suggestedCapability":"Add cache retriever.","summaryKey":"cache-gap"}]' />
        </Card>
      </Space>
    </Modal>
  );
}

function AcceptanceGateDetailPage() {
  const { gateId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const backTarget = resolveBackTarget(location, ACCEPTANCE_GATES_ROUTE);
  const [gate, setGate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!gateId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchApi(`/api/review-quality/acceptance-gates/${gateId}`);
      setGate(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [gateId]);

  const ruleGapColumns = [
    { title: '缺口类型', dataIndex: 'gapType', width: 190, render: value => <Tag color="orange">{value || '-'}</Tag> },
    { title: 'Signal', dataIndex: 'signal', width: 190, ellipsis: true },
    { title: 'Requested Context', dataIndex: 'requestedContext', width: 190, ellipsis: true },
    { title: '建议能力', dataIndex: 'suggestedCapability', ellipsis: true },
    { title: 'Summary Key', dataIndex: 'summaryKey', width: 180, ellipsis: true }
  ];

  return (
    <GovernanceDiagnosticsShell
      title={gate?.title || '验收详情'}
      description="人工准入和退出验收记录，不阻断线上 Review 或合并流程。"
      backAction={<MuiButton size="small" variant="outlined" startIcon={<ArrowLeftOutlined />} onClick={() => navigate(backTarget)}>返回</MuiButton>}
    >
        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}
        <Spin spinning={loading}>
          {gate ? (
            <Space direction="vertical" size="large" className="full-width">
              <Card title="基础信息">
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="ID">{gate.id}</Descriptions.Item>
                  <Descriptions.Item label="项目">{gate.projectName || gate.projectId}</Descriptions.Item>
                  <Descriptions.Item label="改动类型"><Tag>{acceptanceGateChangeTypeLabel(gate.changeType)}</Tag></Descriptions.Item>
                  <Descriptions.Item label="状态"><Tag color={acceptanceGateStatusColor(gate.status)}>{acceptanceGateStatusLabel(gate.status)}</Tag></Descriptions.Item>
                  <Descriptions.Item label="Provider">{gate.provider || '-'}</Descriptions.Item>
                  <Descriptions.Item label="Profile">{gate.profile || '-'}</Descriptions.Item>
                  <Descriptions.Item label="风险类型">{gate.riskType || '-'}</Descriptions.Item>
                  <Descriptions.Item label="更新时间">{formatDateTime(gate.updatedAt)}</Descriptions.Item>
                </Descriptions>
              </Card>
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="准入信息">
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="问题说明">{gate.admission?.problemStatement || '-'}</Descriptions.Item>
                      <Descriptions.Item label="预期收益">{gate.admission?.expectedBenefit || '-'}</Descriptions.Item>
                      <Descriptions.Item label="风险评估">{gate.admission?.riskAssessment || '-'}</Descriptions.Item>
                      <Descriptions.Item label="成本估算">{gate.admission?.costEstimate || '-'}</Descriptions.Item>
                      <Descriptions.Item label="决策人">{gate.admission?.decisionBy || '-'}</Descriptions.Item>
                      <Descriptions.Item label="决策时间">{formatDateTime(gate.admission?.decisionAt)}</Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="退出结果">
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="结果状态"><Tag color={acceptanceGateResultStatusColor(gate.exit?.resultStatus)}>{acceptanceGateResultStatusLabel(gate.exit?.resultStatus)}</Tag></Descriptions.Item>
                      <Descriptions.Item label="误判 Delta">{gate.exit?.falsePositiveDelta ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="上下文不足 Delta">{gate.exit?.contextMissingDelta ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="漏报 Delta">{gate.exit?.missingFindingDelta ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="Finding 数 Delta">{gate.exit?.findingCountDelta ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="耗时 Delta">{gate.exit?.durationDeltaMs ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="Token 成本 Delta">{gate.exit?.tokenCostDelta ?? '-'}</Descriptions.Item>
                      <Descriptions.Item label="说明">{gate.exit?.notes || '-'}</Descriptions.Item>
                      <Descriptions.Item label="决策人">{gate.exit?.decidedBy || '-'}</Descriptions.Item>
                      <Descriptions.Item label="决策时间">{formatDateTime(gate.exit?.decidedAt)}</Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
              </Row>
              <Card title="关联对象">
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="Evaluation Cases">
                    <Space wrap>{safeArray(gate.evaluationCaseIds).map(id => <Tag key={id}>#{id}</Tag>)}</Space>
                  </Descriptions.Item>
                  <Descriptions.Item label="Evaluation Runs">
                    <Space wrap>{safeArray(gate.evaluationRunIds).map(id => <Button key={id} type="link" onClick={() => navigate(`${EVALUATION_RUNS_ROUTE}/${id}`, { state: { from: currentRoute(location) } })}>Run #{id}</Button>)}</Space>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
              <Card title="Rule Gap 安全摘要">
                <Table rowKey={(row, index) => row.summaryKey || `${row.gapType}-${row.signal}-${index}`} size="small" columns={ruleGapColumns} dataSource={safeArray(gate.ruleGapSummary)} pagination={false} scroll={{ x: 940 }} />
              </Card>
            </Space>
          ) : (
            !loading && <Empty description="暂无验收记录详情" />
          )}
        </Spin>
    </GovernanceDiagnosticsShell>
  );
}

function emptyAcceptanceGateDraft(source = {}) {
  return {
    projectId: source.projectId || null,
    title: source.title || '',
    changeType: source.changeType || 'OTHER',
    status: source.status || 'DRAFT',
    provider: source.provider || '',
    profile: source.profile || '',
    riskType: source.riskType || '',
    evaluationCaseIdsText: safeArray(source.evaluationCaseIds).join(','),
    evaluationRunIdsText: safeArray(source.evaluationRunIds).join(','),
    ruleGapSummaryText: JSON.stringify(safeArray(source.ruleGapSummary), null, 2),
    admission: {
      problemStatement: source.admission?.problemStatement || '',
      expectedBenefit: source.admission?.expectedBenefit || '',
      riskAssessment: source.admission?.riskAssessment || '',
      costEstimate: source.admission?.costEstimate || '',
      decisionBy: source.admission?.decisionBy || '',
      decisionAt: source.admission?.decisionAt || ''
    },
    exit: {
      resultStatus: source.exit?.resultStatus || null,
      falsePositiveDelta: source.exit?.falsePositiveDelta ?? null,
      contextMissingDelta: source.exit?.contextMissingDelta ?? null,
      missingFindingDelta: source.exit?.missingFindingDelta ?? null,
      findingCountDelta: source.exit?.findingCountDelta ?? null,
      durationDeltaMs: source.exit?.durationDeltaMs ?? null,
      tokenCostDelta: source.exit?.tokenCostDelta ?? null,
      notes: source.exit?.notes || '',
      decidedBy: source.exit?.decidedBy || '',
      decidedAt: source.exit?.decidedAt || ''
    }
  };
}

function acceptanceGateDraftToPayload(draft) {
  return {
    projectId: draft.projectId,
    title: draft.title,
    changeType: draft.changeType,
    status: draft.status,
    provider: draft.provider || null,
    profile: draft.profile || null,
    riskType: draft.riskType || null,
    evaluationCaseIds: parseIdList(draft.evaluationCaseIdsText),
    evaluationRunIds: parseIdList(draft.evaluationRunIdsText),
    ruleGapSummary: parseJsonArray(draft.ruleGapSummaryText),
    admission: draft.admission,
    exit: draft.exit
  };
}

function parseIdList(value) {
  return String(value || '')
    .split(/[,\s]+/)
    .map(item => Number(item))
    .filter(item => Number.isFinite(item) && item > 0);
}

function parseJsonArray(value) {
  const text = String(value || '').trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    message.warning('Rule Gap 摘要 JSON 无效，已按空数组提交');
    return [];
  }
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
    { title: '创建时间', dataIndex: 'createdAt', width: 210, render: formatDateTime }
  ];

  return (
    <GovernanceDiagnosticsShell
      title="回放记录"
      description="查看 evaluation run / review replay run 的版本记录和样本结果摘要，用于支撑能力改动验收。"
    >
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
        </Paper>
        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}
        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, backgroundColor: '#ffffff' }}>
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
        </Paper>
    </GovernanceDiagnosticsShell>
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
    <GovernanceDiagnosticsShell
      title="回放详情"
      description={`Run #${runId} 的版本记录、baseline / candidate 摘要和样本结果。`}
      backAction={<MuiButton size="small" variant="outlined" startIcon={<ArrowLeftOutlined />} onClick={() => navigate(backTarget)}>返回</MuiButton>}
    >
        {error && <MuiAlert severity="error" variant="outlined">{error}</MuiAlert>}
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
                  <Descriptions.Item label="创建时间">{formatDateTime(run.createdAt)}</Descriptions.Item>
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
    </GovernanceDiagnosticsShell>
  );
}

function HomePage() {
  const location = useLocation();
  const legacyTaskId = new URLSearchParams(location.search).get('taskId');

  if (legacyTaskId) {
    return <Navigate to={`/tasks/${legacyTaskId}`} replace />;
  }

  return <CommandCenterPage />;
}

const APP_SHELL_NAV_ICONS = {
  overview: <DashboardOutlined />,
  tasks: <FileSearchOutlined />,
  governance: <ClusterOutlined />,
  quality: <ClusterOutlined />,
  samples: <CommentOutlined />,
  gaps: <FileSearchOutlined />,
  acceptance: <SafetyCertificateOutlined />,
  replay: <ClockCircleOutlined />,
  feedback: <CommentOutlined />,
  settings: <SettingOutlined />
};

function appShellMenuItems(items) {
  return items.map(item => ({
    key: item.key,
    icon: APP_SHELL_NAV_ICONS[item.icon],
    label: item.label,
    title: item.label,
    children: item.children ? appShellMenuItems(item.children) : undefined
  }));
}

function AppShellBrand({ compact = false, onClick }) {
  return (
    <button
      aria-label="返回运行总览"
      className={`app-shell-brand${compact ? ' app-shell-brand-compact' : ''}`}
      type="button"
      onClick={onClick}
    >
      <SafetyCertificateOutlined className="app-shell-brand-icon" />
      {!compact && <span>AI代码质量审查平台</span>}
    </button>
  );
}

function AppShellMenu({ collapsed = false, items, openKeys, selectedKey, onNavigate }) {
  return (
    <Menu
      className="app-shell-menu"
      inlineCollapsed={collapsed}
      items={appShellMenuItems(items)}
      mode="inline"
      selectedKeys={selectedKey ? [selectedKey] : []}
      defaultOpenKeys={openKeys}
      onClick={({ key }) => onNavigate(key)}
    />
  );
}

function useAppShellViewport() {
  const [mode, setMode] = useState(() => (
    typeof window === 'undefined' ? 'desktop' : resolveAppShellViewport(window.innerWidth)
  ));

  useEffect(() => {
    const update = () => setMode(resolveAppShellViewport(window.innerWidth));
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  return mode;
}

function appShellLocalStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function AppFrame() {
  const location = useLocation();
  const navigate = useNavigate();
  const route = currentRoute(location);
  const isCommandCenterRoute = location.pathname === HOME_ROUTE;
  const isTaskDetailRoute = /^\/tasks\/[^/]+\/?$/.test(location.pathname);
  const isReleaseRoute = location.pathname.startsWith(RELEASES_ROUTE);
  const isHelpRoute = location.pathname.startsWith(HELP_ROUTE);
  const viewportMode = useAppShellViewport();
  const navigationTriggerRef = useRef(null);
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(() => (
    readSidebarCollapsedPreference(appShellLocalStorage())
  ));
  const [temporaryNavigationOpen, setTemporaryNavigationOpen] = useState(false);
  const [jobQueue, setJobQueue] = useState({ activeCount: 0, groups: [] });
  const [jobQueueOpen, setJobQueueOpen] = useState(false);
  const [failureNotifications, setFailureNotifications] = useState({ failureCount: 0, items: [] });
  const [failureNotificationsOpen, setFailureNotificationsOpen] = useState(false);
  const frameDrawerOpenRef = useRef({ queue: false, failures: false });
  const frameRequestsRef = useRef({ queue: null, failures: null });
  const frameMountedRef = useRef(false);
  const [reviewWorkspaceMode, setReviewWorkspaceMode] = useState('RESULT');
  const reportReviewWorkspaceMode = useCallback(mode => {
    setReviewWorkspaceMode(normalizeReviewWorkspaceMode(mode));
  }, []);
  const reviewWorkspaceFrame = resolveReviewWorkspaceFrame(
    reviewWorkspaceMode,
    isTaskDetailRoute
  );
  const reviewWorkspaceContextValue = useMemo(() => ({
    mode: reviewWorkspaceFrame.mode,
    reportMode: reportReviewWorkspaceMode
  }), [reviewWorkspaceFrame.mode, reportReviewWorkspaceMode]);
  const navigationItems = useMemo(() => buildAppShellNavigation({
    qualityGovernanceVisible: QUALITY_GOVERNANCE_NAV_VISIBLE,
    reviewLearningVisible: REVIEW_LEARNING_UI_ENABLED
  }), []);
  const selectedNavigationKey = resolveAppShellSelectedKey(location.pathname, navigationItems);
  const openNavigationKeys = resolveAppShellOpenKeys(selectedNavigationKey, navigationItems);

  const loadFrameResource = useCallback(kind => {
    if (
      !frameMountedRef.current
      || document.hidden === true
      || document.visibilityState === 'hidden'
    ) return Promise.resolve(null);
    const existing = frameRequestsRef.current[kind];
    if (existing) return existing.promise;

    const controller = new AbortController();
    const request = { controller, promise: null };
    frameRequestsRef.current[kind] = request;
    request.promise = (async () => {
      try {
        const data = await fetchApi(
          kind === 'queue'
            ? '/api/code-quality-reviews/job-queue'
            : '/api/code-quality-reviews/failure-notifications',
          { signal: controller.signal }
        );
        if (!frameMountedRef.current || controller.signal.aborted) return null;
        if (kind === 'queue') {
          setJobQueue(data || { activeCount: 0, groups: [] });
        } else {
          setFailureNotifications(data || { failureCount: 0, items: [] });
        }
        return data;
      } catch {
        if (!frameMountedRef.current || controller.signal.aborted) return null;
        if (kind === 'queue') {
          setJobQueue({ activeCount: 0, groups: [] });
        } else {
          setFailureNotifications({ failureCount: 0, items: [] });
        }
        return null;
      } finally {
        if (frameRequestsRef.current[kind] === request) {
          frameRequestsRef.current[kind] = null;
        }
      }
    })();
    return request.promise;
  }, []);

  const abortFrameRequests = useCallback(() => {
    for (const kind of ['queue', 'failures']) {
      frameRequestsRef.current[kind]?.controller.abort();
      frameRequestsRef.current[kind] = null;
    }
  }, []);

  const loadJobQueue = useCallback(
    () => loadFrameResource('queue'),
    [loadFrameResource]
  );

  const loadFailureNotifications = useCallback(
    () => loadFrameResource('failures'),
    [loadFrameResource]
  );

  const openJobQueue = useCallback(() => {
    frameDrawerOpenRef.current.queue = true;
    setJobQueueOpen(true);
    loadJobQueue();
  }, [loadJobQueue]);

  const openFailureNotifications = useCallback(() => {
    frameDrawerOpenRef.current.failures = true;
    setFailureNotificationsOpen(true);
    loadFailureNotifications();
  }, [loadFailureNotifications]);

  const closeJobQueue = useCallback(() => {
    frameDrawerOpenRef.current.queue = false;
    setJobQueueOpen(false);
  }, []);

  const closeFailureNotifications = useCallback(() => {
    frameDrawerOpenRef.current.failures = false;
    setFailureNotificationsOpen(false);
  }, []);

  const openTaskFromQueue = (taskId) => {
    if (!taskId) return;
    frameDrawerOpenRef.current.queue = false;
    frameDrawerOpenRef.current.failures = false;
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
    if (!isTaskDetailRoute) {
      setReviewWorkspaceMode('RESULT');
    }
  }, [isTaskDetailRoute, location.pathname]);

  useEffect(() => {
    frameMountedRef.current = true;
    let timer = null;
    let disposed = false;
    const clearTimer = () => {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    };
    const pause = () => {
      clearTimer();
      abortFrameRequests();
    };
    const refreshAndSchedule = async () => {
      clearTimer();
      if (
        disposed
        || document.hidden === true
        || document.visibilityState === 'hidden'
      ) return;
      if (isCommandCenterRoute) {
        const drawerRequests = [];
        if (frameDrawerOpenRef.current.queue) drawerRequests.push(loadJobQueue());
        if (frameDrawerOpenRef.current.failures) drawerRequests.push(loadFailureNotifications());
        await Promise.all(drawerRequests);
        return;
      }
      await Promise.all([loadJobQueue(), loadFailureNotifications()]);
      if (
        !disposed
        && !isCommandCenterRoute
        && document.hidden !== true
        && document.visibilityState !== 'hidden'
      ) {
        timer = window.setTimeout(refreshAndSchedule, 5000);
      }
    };
    const lifecycle = createVisibilityRefreshLifecycle({
      onPause: pause,
      onResume: refreshAndSchedule
    });
    lifecycle.start();

    return () => {
      disposed = true;
      frameMountedRef.current = false;
      lifecycle.dispose();
      pause();
    };
  }, [abortFrameRequests, isCommandCenterRoute, loadFailureNotifications, loadJobQueue]);

  useEffect(() => {
    window.addEventListener(JOB_QUEUE_REFRESH_EVENT, loadJobQueue);
    window.addEventListener(FAILURE_NOTIFICATION_REFRESH_EVENT, loadFailureNotifications);
    return () => {
      window.removeEventListener(JOB_QUEUE_REFRESH_EVENT, loadJobQueue);
      window.removeEventListener(FAILURE_NOTIFICATION_REFRESH_EVENT, loadFailureNotifications);
    };
  }, [loadFailureNotifications, loadJobQueue]);

  const appFrameOperationsValue = useMemo(() => ({
    jobQueue,
    failureNotifications,
    jobQueueOpen,
    failureNotificationsOpen,
    openJobQueue,
    openFailureNotifications
  }), [
    failureNotifications,
    failureNotificationsOpen,
    jobQueue,
    jobQueueOpen,
    openFailureNotifications,
    openJobQueue
  ]);

  const restoreNavigationTriggerFocus = useCallback(() => {
    window.setTimeout(() => navigationTriggerRef.current?.focus(), 0);
  }, []);

  const closeTemporaryNavigation = useCallback((restoreFocus = false) => {
    setTemporaryNavigationOpen(false);
    if (restoreFocus) restoreNavigationTriggerFocus();
  }, [restoreNavigationTriggerFocus]);

  const navigateFromShell = useCallback(key => {
    closeTemporaryNavigation(viewportMode !== 'desktop');
    navigate(key, { state: { from: route } });
  }, [closeTemporaryNavigation, navigate, route, viewportMode]);

  const toggleDesktopSidebar = useCallback(() => {
    setDesktopSidebarCollapsed(collapsed => {
      const next = !collapsed;
      writeSidebarCollapsedPreference(appShellLocalStorage(), next);
      return next;
    });
  }, []);

  useEffect(() => {
    setTemporaryNavigationOpen(false);
  }, [reviewWorkspaceFrame.immersive, viewportMode]);

  useEffect(() => {
    if (viewportMode !== 'tablet' || !temporaryNavigationOpen) return undefined;
    const onKeyDown = event => {
      if (event.key === 'Escape') closeTemporaryNavigation(true);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [closeTemporaryNavigation, temporaryNavigationOpen, viewportMode]);

  return (
    <AppFrameOperationsContext.Provider value={appFrameOperationsValue}>
      <ReviewWorkspaceModeContext.Provider value={reviewWorkspaceContextValue}>
      <Layout
        className={`app-layout${reviewWorkspaceFrame.immersive ? ' app-layout-review-immersive' : ''}`}
        data-app-frame-background-polling={isCommandCenterRoute ? 'paused' : 'active'}
        data-app-frame-job-queue-open={jobQueueOpen ? 'true' : 'false'}
        data-app-frame-failure-open={failureNotificationsOpen ? 'true' : 'false'}
      >
        {!reviewWorkspaceFrame.immersive && viewportMode !== 'mobile' && (
          <Sider
            className="app-sidebar"
            collapsed={viewportMode === 'tablet' || desktopSidebarCollapsed}
            collapsedWidth={72}
            theme="light"
            size={224}
          >
            <AppShellBrand
              compact={viewportMode === 'tablet' || desktopSidebarCollapsed}
              onClick={() => navigate(HOME_ROUTE)}
            />
            <nav aria-label="主导航" className="app-sidebar-navigation">
              <AppShellMenu
                collapsed={viewportMode === 'tablet' || desktopSidebarCollapsed}
                items={navigationItems}
                openKeys={openNavigationKeys}
                selectedKey={selectedNavigationKey}
                onNavigate={navigateFromShell}
              />
            </nav>
            <Tooltip
              placement="right"
              title={viewportMode === 'tablet'
                ? '展开菜单'
                : desktopSidebarCollapsed ? '展开菜单' : '收起菜单'}
            >
              <Button
                ref={viewportMode === 'tablet' ? navigationTriggerRef : undefined}
                aria-label={viewportMode === 'tablet'
                  ? '展开菜单'
                  : desktopSidebarCollapsed ? '展开菜单' : '收起菜单'}
                className="app-sidebar-toggle"
                icon={viewportMode === 'tablet'
                  ? <MenuUnfoldOutlined />
                  : desktopSidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                type="text"
                onClick={viewportMode === 'tablet'
                  ? () => setTemporaryNavigationOpen(true)
                  : toggleDesktopSidebar}
              />
            </Tooltip>
          </Sider>
        )}

        {!reviewWorkspaceFrame.immersive && viewportMode === 'tablet' && (
          <Drawer
            afterOpenChange={open => { if (!open) restoreNavigationTriggerFocus(); }}
            className="app-sidebar-tablet-drawer"
            closable={false}
            keyboard
            open={temporaryNavigationOpen}
            placement="left"
            rootStyle={{ left: 72 }}
            title={<AppShellBrand onClick={() => navigateFromShell(HOME_ROUTE)} />}
            width={224}
            onClose={() => closeTemporaryNavigation(false)}
          >
            <nav aria-label="展开的主导航">
              <AppShellMenu
                items={navigationItems}
                openKeys={openNavigationKeys}
                selectedKey={selectedNavigationKey}
                onNavigate={navigateFromShell}
              />
            </nav>
          </Drawer>
        )}

        {!reviewWorkspaceFrame.immersive && viewportMode === 'mobile' && (
          <Drawer
            afterOpenChange={open => { if (!open) restoreNavigationTriggerFocus(); }}
            className="app-sidebar-mobile-drawer"
            closable
            keyboard
            open={temporaryNavigationOpen}
            placement="left"
            title={<AppShellBrand onClick={() => navigateFromShell(HOME_ROUTE)} />}
            size="min(280px, 88vw)"
            onClose={() => closeTemporaryNavigation(false)}
          >
            <nav aria-label="移动端主导航">
              <AppShellMenu
                items={navigationItems}
                openKeys={openNavigationKeys}
                selectedKey={selectedNavigationKey}
                onNavigate={navigateFromShell}
              />
            </nav>
          </Drawer>
        )}

        <Layout className="app-main-layout">
          {!reviewWorkspaceFrame.immersive && (
            <Header className="app-header">
              <div className="app-global-header-leading">
                {viewportMode === 'mobile' && (
                  <>
                    <Button
                      ref={navigationTriggerRef}
                      aria-label="打开主菜单"
                      className="app-mobile-menu-trigger"
                      icon={<MenuOutlined />}
                      type="text"
                      onClick={() => setTemporaryNavigationOpen(true)}
                    />
                    <AppShellBrand compact onClick={() => navigate(HOME_ROUTE)} />
                  </>
                )}
              </div>
              <div className="header-actions">
                <Tooltip title="帮助">
                  <Button
                    aria-label="帮助"
                    icon={<QuestionCircleOutlined />}
                    type={isHelpRoute ? 'primary' : 'text'}
                    onClick={() => navigateFromShell(HELP_ROUTE)}
                  >
                    <span className="app-header-action-label">帮助</span>
                  </Button>
                </Tooltip>
                <Tooltip title="版本">
                  <Button
                    aria-label="版本"
                    icon={<ClockCircleOutlined />}
                    type={isReleaseRoute ? 'primary' : 'text'}
                    onClick={() => navigateFromShell(RELEASES_ROUTE)}
                  >
                    <span className="app-header-action-label">版本</span>
                  </Button>
                </Tooltip>
                <Tooltip title="AI Review 失败通知">
                  <Badge count={failureNotifications?.failureCount || 0} size="small">
                    <Button
                      aria-label="AI Review 失败通知"
                      danger={Boolean(failureNotifications?.failureCount)}
                      icon={<BellOutlined />}
                      type={failureNotifications?.failureCount ? 'primary' : 'text'}
                      onClick={openFailureNotifications}
                    />
                  </Badge>
                </Tooltip>
                <Tooltip title="AI Review 调度队列">
                  <Badge count={jobQueue?.activeCount || 0} size="small">
                    <Button
                      aria-label="AI Review 调度队列"
                      icon={<ClusterOutlined />}
                      type={jobQueue?.activeCount ? 'primary' : 'text'}
                      onClick={openJobQueue}
                    />
                  </Badge>
                </Tooltip>
              </div>
            </Header>
          )}
          <Content className={reviewWorkspaceFrame.immersive ? 'app-content-review-immersive' : 'app-content'}>
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
              <Route path={ACCEPTANCE_GATES_ROUTE} element={<AcceptanceGatesPage />} />
              <Route path={`${ACCEPTANCE_GATES_ROUTE}/:gateId`} element={<AcceptanceGateDetailPage />} />
              <Route path={EVALUATION_CASES_ROUTE} element={<EvaluationCasesPage />} />
              <Route path={EVALUATION_RUNS_ROUTE} element={<EvaluationRunsPage />} />
              <Route path={`${EVALUATION_RUNS_ROUTE}/:runId`} element={<EvaluationRunDetailPage />} />
              <Route path={SETTINGS_ROUTE} element={<SettingsPage />} />
              <Route path={RELEASES_ROUTE} element={<ReleaseNotesPage />} />
              <Route path={HELP_ROUTE} element={<HelpPage />} />
              <Route path="*" element={<Navigate to={HOME_ROUTE} replace />} />
            </Routes>
          </Content>
        </Layout>
        <JobQueueModal
          open={jobQueueOpen}
          queue={jobQueue}
          onClose={closeJobQueue}
          onOpenTask={openTaskFromQueue}
          onCancelJob={cancelJobFromQueue}
        />
        <FailureNotificationsModal
          open={failureNotificationsOpen}
          notifications={failureNotifications}
          onClose={closeFailureNotifications}
          onOpenTask={openTaskFromQueue}
        />
      </Layout>
      </ReviewWorkspaceModeContext.Provider>
    </AppFrameOperationsContext.Provider>
  );
}

export default function App() {
  return <AppFrame />;
}
