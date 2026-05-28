import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
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
  Select,
  Space,
  Spin,
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
  CopyOutlined,
  ExportOutlined,
  EyeOutlined,
  FileSearchOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  QuestionCircleOutlined,
  UnorderedListOutlined
} from '@ant-design/icons';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
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
const SETTINGS_ROUTE = '/settings';
const RELEASES_ROUTE = '/releases';
const HELP_ROUTE = '/help';
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
  triggerOnPush: false,
  triggerOnlyWhenRiskMatched: false,
  autoFixPreviewEnabled: false,
  autoFixPreviewSeverities: ['CRITICAL'],
  pushBranchPatterns: ['master'],
  pushMinChangedFiles: 10,
  pushMinDiffBytes: 30000,
  pushMinCommitCount: 3,
  pushMaxChangedFiles: -1,
  pushMaxDiffBytes: -1,
  pushDebounceSeconds: 300
};

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

function isBackendRuleTemplate(template) {
  if (!template) return false;
  return template.templateCode === 'backend-default' || template.targetType === 'BACKEND';
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
      return 'Anthropic / Claude';
    case 'DEEPSEEK':
      return 'DeepSeek';
    case 'XIAOMIMO':
      return 'XiaoMIMO / Xiaomi MiMo';
    case 'CUSTOM':
      return '自定义模型';
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
    const hunkMatch = line.match(/^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/);
    if (hunkMatch) {
      current = {
        id: `hunk-${hunks.length}`,
        header: line,
        oldStart: Number(hunkMatch[1]),
        newStart: Number(hunkMatch[2]),
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
    rows.push({
      id: `${hunk.id}-header`,
      type: 'hunk',
      oldLine: '',
      newLine: '',
      oldText: hunk.header,
      newText: hunk.header,
      highlight: false
    });
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
  DB: { label: 'DB配置', titleColor: '#526a7a', sort: 1 },
  MQ: { label: 'MQ配置', titleColor: '#d48806', sort: 2 },
  CACHE: { label: 'Redis配置', titleColor: '#cf1322', sort: 3 },
  CONFIG: { label: 'Nacos配置', titleColor: '#1677ff', sort: 4 },
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

function FocusIndicatorTags({ indicators, muted = false }) {
  const matchedIndicators = orderedFocusIndicators(indicators).filter(item => item.matched);
  if (matchedIndicators.length === 0) return muted ? <Text type="secondary">-</Text> : null;

  return (
    <Space wrap size={[4, 4]}>
      {matchedIndicators.map(item => (
        <Tag key={item.code} color={focusIndicatorMeta[item.code]?.color || 'default'}>
          {focusIndicatorMeta[item.code]?.label || item.name}
        </Tag>
      ))}
    </Space>
  );
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

function JobQueueModal({ open, queue, onClose, onOpenTask, onOpenFixPreview }) {
  const groups = Array.isArray(queue?.groups) ? queue.groups : [];
  const metaItems = (group, reviewJob) => [
    {
      label: 'Review 状态',
      value: <Tag color={schedulerStatusColor(reviewJob.status)}>{schedulerStatusLabel(reviewJob.status)}</Tag>
    },
    { label: '排队时间', value: reviewJob.queuedAt || '-' },
    { label: '耗时', value: jobDurationText(reviewJob) },
    { label: '触发类型', value: group.triggerType || '-' },
    { label: '分支', value: taskListBranchText(group), wide: true },
    { label: '错误', value: reviewJob.errorMessage || '-', wide: true }
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
      width: 130,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => onOpenTask?.(row.taskId)}>详情</Button>
          {row.findingIndex != null && (
            <Button type="link" size="small" onClick={() => onOpenFixPreview?.(row.taskId, row.findingIndex)}>
              风险点
            </Button>
          )}
        </Space>
      )
    }
  ];
  return (
    <Modal title="AI Review 调度队列" open={open} onCancel={onClose} footer={null} width="min(1100px, 96vw)">
      {groups.length === 0 ? (
        <Empty description="暂无调度任务" />
      ) : (
        <Collapse
          items={groups.map(group => {
            const reviewJob = group.reviewJob;
            const activeFixCount = (group.fixPreviewJobs || []).filter(job => ['QUEUED', 'RUNNING'].includes(job.status)).length;
            return {
              key: group.taskId,
              label: (
                <Space wrap>
                  <Text strong>任务 #{group.taskId}</Text>
                  <Text>{group.projectName || '-'}</Text>
                  {reviewJob && <Tag color={schedulerStatusColor(reviewJob.status)}>Review {schedulerStatusLabel(reviewJob.status)}</Tag>}
                  {activeFixCount > 0 && <Tag color="processing">修复预览 {activeFixCount} 个进行中</Tag>}
                </Space>
              ),
              children: (
                <Space direction="vertical" className="full-width">
                  {reviewJob ? (
                    <div className="job-queue-review-row">
                      <div className="job-queue-review-meta">
                        {metaItems(group, reviewJob).map(item => (
                          <div key={item.label} className={item.wide ? 'job-queue-meta-item is-wide' : 'job-queue-meta-item'}>
                            <Text type="secondary" className="job-queue-meta-label">{item.label}：</Text>
                            <span className="job-queue-meta-value">{item.value}</span>
                          </div>
                        ))}
                      </div>
                      <Button type="link" onClick={() => onOpenTask?.(group.taskId)}>查看任务详情</Button>
                    </div>
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

async function copyTextToClipboard(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success('已复制可维护内容');
  } catch (err) {
    message.error(err?.message || '复制失败');
  }
}

function MaintenanceArtifacts({ artifacts }) {
  const items = Array.isArray(artifacts) ? artifacts.filter(item => item?.content) : [];
  if (items.length === 0) return null;
  return (
    <Space direction="vertical" size="small" className="full-width">
      <Text strong>可维护内容</Text>
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
          <pre className="maintenance-artifact-code">{artifact.content}</pre>
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
    { title: '状态', dataIndex: 'status', width: 95, render: value => <Tag color={statusColor(value)}>{value || '-'}</Tag> },
    { title: '重点变更', dataIndex: 'focusIndicators', width: 220, render: value => <FocusIndicatorTags indicators={value} muted /> },
    { title: '风险', dataIndex: 'riskItemCount', width: 60, render: value => value ?? 0 },
    { title: '创建时间', dataIndex: 'createdAt', width: 125, ellipsis: true },
    { title: '操作', width: 70, render: (_, row) => <Button type="link" onClick={() => onOpen(row.id)}>详情</Button> }
  ];

  return (
    <div className="page-shell">
      <div className="page-heading">
        <Space>
          <Select
            allowClear
            className="task-filter-select"
            placeholder="项目组"
            value={groupId}
            options={groups.map(group => ({ label: group.groupName, value: group.id }))}
            onChange={value => {
              setGroupId(value || null);
              setProjectId(null);
            }}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            className="task-filter-select"
            placeholder="项目"
            value={projectId}
            options={projects
              .filter(project => !groupId || project.groupId === groupId)
              .map(project => ({ label: project.name, value: project.id }))}
            onChange={value => setProjectId(value || null)}
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

function RiskCardView({ riskCard, changedFilesSummary }) {
  const location = useLocation();
  const [diffTarget, setDiffTarget] = useState(null);
  const [activeReminderGroupKeys, setActiveReminderGroupKeys] = useState([]);
  const [activeReminderItemKeys, setActiveReminderItemKeys] = useState([]);

  const riskItems = useMemo(
    () => (riskCard?.riskItems || []).filter(item => item.ruleCode !== 'API_COMPATIBILITY_CHECK' && item.category !== 'API'),
    [riskCard]
  );
  const reminderGroups = useMemo(() => buildReminderGroups(riskItems), [riskItems]);
  const firstReminderGroupKey = reminderGroups[0]?.key;
  const firstReminderItemKey = reminderGroups[0]?.items?.[0]?.riskId;
  const roles = riskCard?.suggestedReviewRoles || [];

  useEffect(() => {
    if (!riskCard) return;
    setActiveReminderGroupKeys(firstReminderGroupKey ? [firstReminderGroupKey] : []);
    setActiveReminderItemKeys(firstReminderItemKey ? [firstReminderItemKey] : []);
  }, [riskCard, firstReminderGroupKey, firstReminderItemKey]);

  useEffect(() => {
    if (!riskCard) return;
    const match = /^#risk-item-(.+)$/.exec(location.hash || '');
    if (!match) return;
    const riskId = decodeURIComponent(match[1]);
    const group = reminderGroups.find(item => item.items.some(riskItem => riskItem.riskId === riskId));
    if (!group) return;
    setActiveReminderGroupKeys(current => current.includes(group.key) ? current : [...current, group.key]);
    setActiveReminderItemKeys(current => current.includes(riskId) ? current : [...current, riskId]);
    window.setTimeout(() => {
      document.getElementById(`risk-item-${riskId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 180);
  }, [location.hash, riskCard, reminderGroups]);

  if (!riskCard) return <Empty description="暂无提醒卡片" />;

  const evidenceColumns = [
    { title: '文件', dataIndex: 'filePath', ellipsis: true },
    { title: '规则', dataIndex: 'matcher', width: 180, ellipsis: true },
    {
      title: '片段',
      dataIndex: 'snippet',
      ellipsis: true,
      render: value => value ? <Text code className="evidence-snippet">{value}</Text> : '-'
    },
    {
      title: 'Diff',
      width: 92,
      render: (_, evidence) => (
        <Tooltip title="查看 Diff">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setDiffTarget({
              finding: { filePath: evidence.filePath, startLine: evidence.lineStart, endLine: evidence.lineEnd },
              changedFile: findChangedFileForEvidence(evidence, changedFilesSummary)
            })}
          />
        </Tooltip>
      )
    }
  ];

  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Space direction="vertical" size="small">
          <Paragraph>{riskCardSummaryText(riskCard, riskItems)}</Paragraph>
          <Space wrap>{roles.map(role => <Tag key={role}>{role}</Tag>)}</Space>
        </Space>
      </Card>
      <FocusIndicatorPanel indicators={riskCard.focusIndicators} />
      <Card title="提醒项">
        {reminderGroups.length === 0 ? (
          <Empty description="暂无提醒项" />
        ) : <Collapse
          key={riskCard.cardId || firstReminderGroupKey || 'reminder-groups'}
          activeKey={activeReminderGroupKeys}
          onChange={keys => setActiveReminderGroupKeys(Array.isArray(keys) ? keys : [keys].filter(Boolean))}
          items={reminderGroups.map(group => ({
            key: group.key,
            label: (
              <Space className="risk-item-heading" wrap>
                <Tag>{group.items.length} 条</Tag>
                <Text strong style={{ color: group.titleColor }}>{group.label}</Text>
                {group.categories.map(category => (
                  <Tag key={category} color={fineChangeTypes.has(category) ? 'blue' : 'default'}>
                    {changeTypeLabel(category)}
                  </Tag>
                ))}
              </Space>
            ),
            children: (
              <Collapse
                className="reminder-item-list"
                ghost
                activeKey={activeReminderItemKeys}
                onChange={keys => setActiveReminderItemKeys(Array.isArray(keys) ? keys : [keys].filter(Boolean))}
                items={group.items.map(item => ({
                  key: item.riskId,
                  label: (
                    <Space className="risk-item-heading" wrap>
                      <Tag color={fineChangeTypes.has(item.category) ? 'blue' : 'default'}>{changeTypeLabel(item.category)}</Tag>
                      <Text strong>{item.title}</Text>
                    </Space>
                  ),
                  children: (
                    <Space id={`risk-item-${item.riskId}`} direction="vertical" className="full-width">
                      <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                        <Descriptions.Item label="规则">{item.ruleCode || '-'}</Descriptions.Item>
                        <Descriptions.Item label="类型">{changeTypeLabel(item.category)}</Descriptions.Item>
                      </Descriptions>
                      <Paragraph>{item.description}</Paragraph>
                      {item.reason && <Alert type="info" showIcon message="命中原因" description={item.reason} />}
                      {item.impact && <Text type="secondary">{item.impact}</Text>}
                      {(item.relatedSignals || []).length > 0 && (
                        <Space direction="vertical" size="small">
                          <Text strong>关联信号</Text>
                          <Space wrap>{item.relatedSignals.map(signal => <Tag key={signal}>{signal}</Tag>)}</Space>
                        </Space>
                      )}
                      <MaintenanceArtifacts artifacts={item.maintenanceArtifacts} />
                      <Divider />
                      <Text strong>命中证据</Text>
                      <Table
                        rowKey={(row, index) => `${row.filePath}-${row.matcher}-${index}`}
                        size="small"
                        columns={evidenceColumns}
                        dataSource={item.evidences || []}
                        pagination={false}
                        locale={{ emptyText: '暂无命中证据' }}
                      />
                    </Space>
                  )
                }))}
              />
            )
          }))}
        />}
      </Card>
      <DiffViewerModal
        open={!!diffTarget}
        finding={diffTarget?.finding}
        changedFile={diffTarget?.changedFile}
        onClose={() => setDiffTarget(null)}
      />
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
  const runningStartedAt = startedAt || parseEventTime(reviewEvents[0]?.createdAt) || fallbackStartedAtRef.current;
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
    LARGE_CHANGE: '大变更',
    BRANCH_NOT_MATCHED: '分支不匹配',
    DEBOUNCED: '频率保护',
    DIFF_TOO_LARGE: '超过硬上限',
    NO_DIFF_TEXT: '无可审查 diff',
    PROFILE_DISABLED: 'Profile 未开启',
    GLOBAL_DISABLED: '全局未开启',
    NOT_SIGNIFICANT: '未达到阈值',
    NOT_EVALUATED: '未审核'
  };
  return labels[value] || value || '-';
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
            message={gate.reasonSummary || gateReasonLabel(gate.reasonCode)}
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

function DiffViewerModal({ open, finding, changedFile, onClose }) {
  const diffText = changedFile?.diffText;
  const rows = useMemo(() => {
    if (!diffText) return [];
    return buildSideBySideRows(parseUnifiedDiff(diffText), finding?.startLine, finding?.endLine);
  }, [diffText, finding?.startLine, finding?.endLine]);
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
          <div className="diff-viewer-table" role="table" aria-label="Side by side diff">
            {rows.map(row => (
              <div
                key={row.id}
                className={[
                  'diff-viewer-row',
                  `diff-row-${row.type}`,
                  row.highlight ? 'diff-row-highlight' : ''
                ].filter(Boolean).join(' ')}
              >
                <div className="diff-line-number">{row.oldLine}</div>
                <pre className="diff-code-cell diff-code-old">{row.oldText}</pre>
                <div className="diff-line-number">{row.newLine}</div>
                <pre className="diff-code-cell diff-code-new">{row.newText}</pre>
              </div>
            ))}
          </div>
        )}
      </Space>
    </Modal>
  );
}

function PatchPreviewTable({ patchText }) {
  const rows = useMemo(() => buildSideBySideRows(parseUnifiedDiff(patchText), null, null), [patchText]);
  return (
    <div className="diff-viewer-table" role="table" aria-label="Fix preview patch">
      {rows.map(row => (
        <div
          key={row.id}
          className={['diff-viewer-row', `diff-row-${row.type}`].join(' ')}
        >
          <div className="diff-line-number">{row.oldLine}</div>
          <pre className="diff-code-cell diff-code-old">{row.oldText}</pre>
          <div className="diff-line-number">{row.newLine}</div>
          <pre className="diff-code-cell diff-code-new">{row.newText}</pre>
        </div>
      ))}
    </div>
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
            <PatchPreviewTable patchText={preview.patchText} />
          </>
        ) : (
          <Empty description="暂无修复预览" />
        )}
      </Space>
    </Modal>
  );
}

function CodeQualityReviewView({ taskId, review, progress, changedFilesSummary, initialFixPreviews, onRetry, retrying }) {
  const location = useLocation();
  const [diffTarget, setDiffTarget] = useState(null);
  const [fixPreviewTarget, setFixPreviewTarget] = useState(null);
  const [fixPreviewByIndex, setFixPreviewByIndex] = useState({});
  const [fixPreviewLoadingIndex, setFixPreviewLoadingIndex] = useState(null);
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
      <Space direction="vertical" size="large" className="full-width">
        <Card>
          <Empty description="暂无代码质量 Review 结果" />
          <div className="empty-action-row">
            <Button type="primary" loading={retrying} onClick={onRetry}>重试 AI Review</Button>
          </div>
        </Card>
        <CodeQualityProgressView progress={progress} />
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
        body: JSON.stringify({ findingIndex: index, forceRegenerate: cached?.status === 'FAILED' })
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
  return (
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
            <Button loading={retrying} disabled={review.status === 'RUNNING'} onClick={onRetry}>重试 AI Review</Button>
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
            items={findings.map((finding, index) => ({
              key: `finding-${index}`,
              label: (
                <Space className="risk-item-heading" wrap>
                  <Tag color={severityColor(finding.severity)}>{severityLabel(finding.severity)}</Tag>
                  {finding.category && <Tag color="blue">{categoryLabel(finding.category)}</Tag>}
                  {finding.confidence && <Tag color={confidenceColor(finding.confidence)}>置信度 {confidenceLabel(finding.confidence)}</Tag>}
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
                          type="primary"
                          ghost
                          loading={fixPreviewLoadingIndex === index || fixPreviewByIndex[index]?.status === 'RUNNING'}
                          disabled={!taskId || review.status === 'RUNNING' || !finding.filePath}
                          onClick={() => generateFixPreview(index)}
                        >
                          {fixPreviewByIndex[index]?.status === 'SUCCESS'
                            ? '查看修复预览'
                            : (fixPreviewByIndex[index]?.status === 'RUNNING'
                                ? '修复预览生成中'
                                : (fixPreviewByIndex[index]?.status === 'QUEUED'
                                    ? '修复预览排队中'
                                : (fixPreviewByIndex[index]?.status === 'FAILED' || fixPreviewByIndex[index]?.status === 'SKIPPED'
                                    ? '重新生成修复预览'
                                    : '生成修复预览')))}
                        </Button>
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="来源">{sourceLabel(finding.source || review.provider)}</Descriptions.Item>
                    <Descriptions.Item label="分类">{categoryLabel(finding.category)}</Descriptions.Item>
                  </Descriptions>
                  {finding.body && <Paragraph>{cleanAiMarkdown(finding.body)}</Paragraph>}
                  {finding.suggestion && <Alert type="info" showIcon message="建议" description={finding.suggestion} />}
                </Space>
              )
            }))}
          />
        )}
      </Card>
      <CodeQualityProgressView
        progress={progress}
        running={review.status === 'RUNNING'}
        reviewStartedAt={review.startedAt}
        reviewFinishedAt={review.finishedAt}
      />
      {review.rawOutput && (
        <Collapse
          items={[{
            key: 'raw-output',
            label: 'Raw Output',
            children: <pre className="raw-output-block">{review.rawOutput}</pre>
          }]}
        />
      )}
      <DiffViewerModal
        open={Boolean(diffTarget)}
        finding={diffTarget?.finding}
        changedFile={activeChangedFile}
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

function TaskDetail({ taskId, onBack, onOpen }) {
  const location = useLocation();
  const [detail, setDetail] = useState(null);
  const [result, setResult] = useState(null);
  const [codeQualityResult, setCodeQualityResult] = useState(null);
  const [codeQualityProgress, setCodeQualityProgress] = useState([]);
  const [codeQualityGate, setCodeQualityGate] = useState(null);
  const [fixPreviews, setFixPreviews] = useState([]);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [rerunning, setRerunning] = useState(false);
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
        const qualityResult = await fetchApi(`/api/review-tasks/${taskId}/code-quality-result`);
        setCodeQualityResult(qualityResult);
      } catch {
        setCodeQualityResult(null);
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
    if (codeQualityResult?.status !== 'RUNNING' && !hasRunningFixPreview) return undefined;
    const timer = window.setInterval(() => load({ silent: true }), 5000);
    return () => window.clearInterval(timer);
  }, [taskId, codeQualityResult?.status, fixPreviews]);

  const retryCodeQualityReview = async () => {
    setRetrying(true);
    setError(null);
    try {
      const retryResult = await fetchApi(`/api/code-quality-reviews/tasks/${taskId}/retry`, { method: 'POST' });
      setCodeQualityResult({
        taskId: retryResult.taskId,
        projectId: detail?.projectId,
        profileCode: retryResult.profileCode,
        provider: retryResult.provider,
        status: retryResult.status,
        overallLevel: retryResult.overallLevel,
        summary: 'AI code review is running',
        findingCount: retryResult.findingCount,
        findings: []
      });
      setCodeQualityProgress([{
        id: 'local-queued',
        taskId,
        phase: 'QUEUED',
        level: 'INFO',
        message: 'AI Review 已重新进入执行队列',
        detail: `provider=${retryResult.provider}, profile=${retryResult.profileCode}`,
        createdAt: new Date().toISOString()
      }]);
      setFixPreviews([]);
      requestJobQueueRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRetrying(false);
    }
  };

  const rerunReviewTask = async () => {
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
    { key: 'quality', label: '代码质量 Review', children: <CodeQualityReviewView taskId={taskId} review={codeQualityResult} progress={codeQualityProgress} changedFilesSummary={detail?.changedFilesSummary} initialFixPreviews={fixPreviews} onRetry={retryCodeQualityReview} retrying={retrying} /> },
    ...(detail?.triggerType === 'GITLAB_PUSH_WEBHOOK'
      ? [{ key: 'gate', label: 'Push 审核', children: <CodeQualityGateView gate={codeQualityGate} detail={detail} /> }]
      : []),
    ...(result?.reminderCardEnabled !== false
      ? [{ key: 'risk', label: '提醒卡片', children: <RiskCardView riskCard={result?.riskCard} changedFilesSummary={detail?.changedFilesSummary} /> }]
      : []),
    { key: 'analysis', label: '分析结果', children: <AnalysisView changeAnalysis={result?.changeAnalysis} /> },
    { key: 'event', label: '原始事件摘要', children: <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card title="changedFiles 摘要"><JsonBlock value={detail?.changedFilesSummary} /></Card></Col><Col xs={24} lg={12}><Card title="raw payload"><JsonBlock value={detail?.rawPayload} /></Card></Col></Row> }
  ], [taskId, detail, result, codeQualityResult, codeQualityProgress, codeQualityGate, fixPreviews, retrying]);
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
          重新触发审阅
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
                  <Tag color={statusColor(detail.status)}>{detail.status}</Tag>
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
  const [templates, setTemplates] = useState([]);
  const [groups, setGroups] = useState([]);
  const [groupDraft, setGroupDraft] = useState({ groupName: '', groupCode: '', description: '', defaultCodeQualityProfileCode: null, defaultProviderCode: null, dingtalkWebhooks: [] });
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
  const [selectedTemplateCode, setSelectedTemplateCode] = useState(null);
  const [notificationRules, setNotificationRules] = useState(null);
  const [notificationRuleDraftCodes, setNotificationRuleDraftCodes] = useState([]);
  const [selectedNotificationRuleCode, setSelectedNotificationRuleCode] = useState(null);
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
  const [targetConfigSaving, setTargetConfigSaving] = useState(false);
  const [targetPathMappingSaving, setTargetPathMappingSaving] = useState(false);
  const [projectConfigReloading, setProjectConfigReloading] = useState(false);
  const [notificationSaving, setNotificationSaving] = useState(false);
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
      const [settingsData, profileData, providerData, templateData, groupData, projectData, pathMappingData] = await Promise.all([
        fetchApi('/api/code-quality-reviews/settings'),
        fetchApi('/api/code-quality-review-profiles'),
        fetchApi('/api/code-quality-review-providers'),
        fetchApi('/api/rule-templates'),
        fetchApi('/api/project-groups'),
        fetchApi('/api/projects?includeDisabled=true'),
        fetchApi('/api/target-type-path-mappings')
      ]);
      const profileItems = Array.isArray(profileData) ? profileData : (profileData.items || []);
      const selectableProfileItems = selectableReviewProfiles(profileItems);
      const providerItems = Array.isArray(providerData) ? providerData : (providerData.items || []);
      const templateItems = Array.isArray(templateData) ? templateData : (templateData.items || []);
      const nextSelectedProfileCode = (
        selectedProfileCode && selectableProfileItems.some(profile => profile.profileCode === selectedProfileCode)
      )
        ? selectedProfileCode
        : selectableProfileItems[0]?.profileCode || null;
      const nextSelectedProviderCode = settingsData?.defaultProviderCode || selectedProviderCode || providerItems[0]?.providerCode || 'DEEPSEEK';
      const nextSelectedTemplateCode = selectedTemplateCode || templateItems.find(item => isBackendRuleTemplate(item))?.templateCode || templateItems[0]?.templateCode || null;
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
      setTemplates(templateItems);
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
      setSelectedTemplateCode(nextSelectedTemplateCode);
      setProviders(providerItems);
      setSelectedProviderCode(nextSelectedProviderCode);
      setProviderDraft(providerItems.find(item => item.providerCode === nextSelectedProviderCode) || providerItems[0] || null);
      setProviderApiKeyDraft('');
      setProfiles(profileItems);
      setSelectedProfileCode(nextSelectedProfileCode);
      setProfileDraft(profileItems.find(item => item.profileCode === nextSelectedProfileCode) || selectableProfileItems[0] || null);
      setPromptPreview(null);
      if (nextSelectedTemplateCode && isBackendRuleTemplate(templateItems.find(item => item.templateCode === nextSelectedTemplateCode))) {
        const rules = await fetchApi(`/api/rule-templates/${nextSelectedTemplateCode}/notification-rules`);
        setNotificationRules(rules);
        setNotificationRuleDraftCodes(rules.focusRuleCodes || []);
        const firstRule = rules.groups?.flatMap(group => group.rules || [])?.[0]?.ruleCode;
        setSelectedNotificationRuleCode(firstRule || null);
      } else {
        setNotificationRules(null);
        setNotificationRuleDraftCodes([]);
        setSelectedNotificationRuleCode(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const loadNotificationRules = async (templateCode) => {
    const rules = await fetchApi(`/api/rule-templates/${templateCode}/notification-rules`);
    setNotificationRules(rules);
    setNotificationRuleDraftCodes(rules.focusRuleCodes || []);
    const firstRule = rules.groups?.flatMap(group => group.rules || [])?.[0]?.ruleCode;
    setSelectedNotificationRuleCode(firstRule || null);
  };

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
    setEditingGroupDraft({ ...group });
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
          dingtalkWebhooks: normalizeWebhookPayload(groupDraft.dingtalkWebhooks || [])
        })
      });
      setGroupDraft({ groupName: '', groupCode: '', description: '', defaultCodeQualityProfileCode: null, defaultProviderCode: null, dingtalkWebhooks: [] });
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
          providerCode: existing?.providerCode || null,
          pathPatterns: existing?.pathPatterns?.length ? existing.pathPatterns : ['**/*'],
          reminderCardEnabled: existing?.reminderCardEnabled ?? defaultReminderCardEnabledForTargetType(normalizedTargetType),
          enabled: true
        })
      });
      const disableTargets = projectTargetConfigs
        .filter(item => item.targetType !== normalizedTargetType && item.enabled !== false)
        .map(item => fetchApi(`/api/projects/${selectedProjectId}/target-configs/${item.targetType}`, {
          method: 'PUT',
          body: JSON.stringify({
            templateCode: item.templateCode || defaultTemplateCodeForTargetType(item.targetType),
            providerCode: item.providerCode || null,
            pathPatterns: item.pathPatterns || [],
            reminderCardEnabled: item.reminderCardEnabled,
            enabled: false
          })
        }));
      if (disableTargets.length > 0) await Promise.all(disableTargets);
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

  const saveProjectTargetConfig = async () => {
    if (!selectedProjectId || !targetConfigDraft) return;
    setTargetConfigSaving(true);
    try {
      const updated = await fetchApi(`/api/projects/${selectedProjectId}/target-configs/${selectedTargetType}`, {
        method: 'PUT',
        body: JSON.stringify({
          templateCode: defaultTemplateCodeForTargetType(selectedTargetType),
          providerCode: targetConfigDraft.providerCode || null,
          pathPatterns: targetConfigDraft.pathPatterns?.length
            ? targetConfigDraft.pathPatterns
            : defaultPathPatternsForTargetType(selectedTargetType),
          reminderCardEnabled: targetConfigDraft.reminderCardEnabled,
          enabled: targetConfigDraft.enabled
        })
      });
      const configs = projectTargetConfigs.some(item => item.targetType === updated.targetType)
        ? projectTargetConfigs.map(item => item.targetType === updated.targetType ? updated : item)
        : [...projectTargetConfigs, updated];
      setProjectTargetConfigs(configs);
      setTargetConfigDraft(updated);
      await reloadProjectGroupsAndProjects(selectedProjectId);
      messageApi.success('项目端类型配置已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setTargetConfigSaving(false);
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

  const selectTemplate = async (templateCode) => {
    setSelectedTemplateCode(templateCode);
    setNotificationRules(null);
    setNotificationRuleDraftCodes([]);
    const template = templates.find(item => item.templateCode === templateCode);
    if (!isBackendRuleTemplate(template)) {
      setSelectedNotificationRuleCode(null);
      return;
    }
    try {
      await loadNotificationRules(templateCode);
    } catch (err) {
      messageApi.error(err.message);
    }
  };

  const toggleNotificationRule = (ruleCode) => {
    if (!notificationRules || notificationSaving) return;
    setSelectedNotificationRuleCode(ruleCode);
    setNotificationRuleDraftCodes(currentCodes => (
      currentCodes.includes(ruleCode)
        ? currentCodes.filter(code => code !== ruleCode)
        : [...currentCodes, ruleCode]
    ));
  };

  const saveNotificationRules = async () => {
    if (!notificationRules || !selectedTemplateCode || notificationSaving) return;
    setNotificationSaving(true);
    try {
      const updated = await fetchApi(`/api/rule-templates/${selectedTemplateCode}/notification-rules`, {
        method: 'PUT',
        body: JSON.stringify({ focusRuleCodes: notificationRuleDraftCodes })
      });
      setNotificationRules(updated);
      setNotificationRuleDraftCodes(updated.focusRuleCodes || []);
      messageApi.success('启用的卡片提醒类型已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setNotificationSaving(false);
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
  const groupProviderOptions = [{ label: '不指定', value: '' }, ...providerOptions];
  const groupProfileOptions = [{ label: '不指定', value: '' }, ...profileOptions];
  const profileProviderOptions = [{ label: '使用当前模型 Provider', value: '' }, ...providerOptions];
  const providerApiKeyPlaceholder = '留空表示不更新当前 API Key';
  const templateOptions = templates.map(template => ({
    label: `${template.templateName} (${template.templateCode})`,
    value: template.templateCode
  }));
  const selectedTemplate = templates.find(template => template.templateCode === selectedTemplateCode) || null;
  const selectedTemplateSupportsNotificationRules = isBackendRuleTemplate(selectedTemplate);
  const notificationRuleItems = notificationRules?.groups?.flatMap(group => group.rules || []) || [];
  const selectedNotificationRule = notificationRuleItems.find(rule => rule.ruleCode === selectedNotificationRuleCode) || notificationRuleItems[0] || null;
  const notificationRulesDirty = JSON.stringify(notificationRuleDraftCodes) !== JSON.stringify(notificationRules?.focusRuleCodes || []);
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
      title: '默认 Provider',
      dataIndex: 'defaultProviderCode',
      width: 180,
      render: (_, group) => editingGroupId === group.id ? (
        <Select className="full-width" value={editingGroupDraft?.defaultProviderCode || ''} options={groupProviderOptions} onChange={value => updateEditingGroupDraft('defaultProviderCode', value || null)} />
      ) : (group.defaultProviderCode || '-')
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
                    <Text strong>默认 Provider</Text>
                    <Select
                      className="full-width prompt-field"
                      value={groupDraft.defaultProviderCode || ''}
                      options={groupProviderOptions}
                      onChange={value => updateGroupDraft('defaultProviderCode', value || null)}
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
                <div className="settings-inline-head">
                  <Space wrap>
                    <Text strong>新项目组钉钉机器人</Text>
                    <Text type="secondary">可先留空，后续编辑项目组时再配置</Text>
                  </Space>
                  <Button icon={<PlusOutlined />} onClick={() => addGroupWebhookDraft('create')}>新增机器人</Button>
                </div>
                {renderWebhookDraftList(groupDraft.dingtalkWebhooks || [], 'create')}
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
                    <Col xs={24} md={8}>
                      <Text strong>当前项目所属项目组</Text>
                      <Select
                        className="full-width prompt-field"
                        value={projectConfigDraft?.groupId || undefined}
                        options={groups.map(group => ({ label: group.groupName, value: group.id }))}
                        onChange={value => updateProjectConfigDraft('groupId', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>当前项目所属端类型</Text>
                      <Select
                        className="full-width prompt-field"
                        value={projectConfigDraft?.targetType || undefined}
                        options={PROJECT_TARGET_TYPE_OPTIONS}
                        loading={projectConfigSaving}
                        onChange={value => updateProjectConfigDraft('targetType', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
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
              {targetConfigDraft ? (
                <>
                <Space direction="vertical" size="middle" className="full-width">
                <div className="settings-inline-head">
                  <Space wrap>
                    <Text strong>端类型</Text>
                    {selectedTargetType && <Tag>{targetTypeLabel(selectedTargetType)}</Tag>}
                  </Space>
                </div>
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={8}>
                    <Text strong>编辑端类型</Text>
                    <Select
                      className="full-width prompt-field"
                      value={selectedTargetType}
                      options={PROJECT_TARGET_TYPE_OPTIONS}
                      onChange={selectTargetTypeForConfig}
                    />
                  </Col>
                  <Col xs={24} md={8}>
                    <Text strong>Provider 覆盖</Text>
                    <Select
                      className="full-width prompt-field"
                      value={targetConfigDraft.providerCode || ''}
                      options={profileProviderOptions}
                      onChange={value => updateTargetConfigDraft('providerCode', value || null)}
                    />
                  </Col>
                  <Col xs={24}>
                    <Text type="secondary">
                      规则模板随端类型自动选择：{defaultTemplateCodeForTargetType(selectedTargetType)}。AI Review 默认使用项目组配置的模板和 Provider；如当前项目端类型配置了 Provider 覆盖，则优先使用端类型覆盖。
                    </Text>
                  </Col>
                  <Col xs={24} md={8}>
                    <Space direction="vertical">
                      <Text strong>提醒卡片</Text>
                      <Switch
                        checked={targetConfigDraft.reminderCardEnabled !== false}
                        checkedChildren="显示"
                        unCheckedChildren="隐藏"
                        onChange={checked => updateTargetConfigDraft('reminderCardEnabled', checked)}
                      />
                    </Space>
                  </Col>
                  <Col xs={24} md={8}>
                    <Space direction="vertical">
                      <Text strong>启用该端类型</Text>
                      <Switch
                        checked={targetConfigDraft.enabled !== false}
                        checkedChildren="启用"
                        unCheckedChildren="停用"
                        onChange={checked => updateTargetConfigDraft('enabled', checked)}
                      />
                      <Text type="secondary">停用后不参与该项目的审查端类型选择。</Text>
                    </Space>
                  </Col>
                </Row>
                <div className="settings-action-row">
                  <Button type="primary" loading={targetConfigSaving} onClick={saveProjectTargetConfig}>保存端类型配置</Button>
                </div>
                </Space>
                </>
              ) : (
                <Empty description="请选择项目和端类型" />
              )}
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
                  message="Webhook 新项目只按这里的全局路径映射识别端类型。同一次变更命中多个端类型时会生成失败任务，提示调整映射。"
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
      key: 'notification-rules',
      label: (
        <Space wrap>
          <Text strong>启用的卡片提醒类型</Text>
          <Tag>{notificationRuleDraftCodes.length} 个已选</Tag>
          {notificationRulesDirty && <Tag color="gold">未保存</Tag>}
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
        >
          <Space direction="vertical" size="middle" className="full-width">
            <Row gutter={[16, 16]} align="middle">
              <Col xs={24} md={10}>
                <Text strong>规则模板</Text>
                <Select
                  className="full-width prompt-field"
                  value={selectedTemplateCode}
                  options={templateOptions}
                  loading={notificationSaving}
                  onChange={selectTemplate}
                />
              </Col>
              <Col xs={24} md={14}>
                <Space wrap>
                  {selectedTemplateSupportsNotificationRules ? (
                    <>
                      <Text type="secondary">已启用 {notificationRuleDraftCodes.length} 个卡片提醒类型</Text>
                      {notificationRuleDraftCodes.map(code => <Tag key={code} color="blue">{code}</Tag>)}
                    </>
                  ) : (
                    <Text type="secondary">当前端类型模板暂不配置后端提醒卡片类型。</Text>
                  )}
                </Space>
              </Col>
            </Row>
            {selectedTemplateSupportsNotificationRules ? (
              <>
                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={12}>
                    {notificationRules ? (
                      <Collapse
                        key={selectedTemplateCode}
                        defaultActiveKey={(notificationRules.groups || [])[0]?.groupCode ? [(notificationRules.groups || [])[0].groupCode] : []}
                        items={(notificationRules.groups || []).map(group => ({
                          key: group.groupCode,
                          label: (
                            <Space wrap>
                              <Tag color={group.color}>{group.rules?.length || 0}</Tag>
                              <Text strong>{group.groupName}</Text>
                            </Space>
                          ),
                          children: (
                            <Space wrap size={[8, 8]}>
                              {(group.rules || []).map(rule => {
                                const checked = notificationRuleDraftCodes.includes(rule.ruleCode);
                                return (
                                  <Tag.CheckableTag
                                    key={rule.ruleCode}
                                    checked={checked}
                                    className={`notification-rule-tag ${checked ? 'is-selected' : ''}`}
                                    onClick={() => toggleNotificationRule(rule.ruleCode)}
                                  >
                                    {rule.title}
                                  </Tag.CheckableTag>
                                );
                              })}
                            </Space>
                          )
                        }))}
                      />
                    ) : (
                      <Empty description="暂无提醒类型配置" />
                    )}
                  </Col>
                  <Col xs={24} lg={12}>
                    {selectedNotificationRule ? (
                      <div className="notification-rule-detail">
                        <Space direction="vertical" size="middle" className="full-width">
                          <Space wrap>
                            <Tag color={riskColor(selectedNotificationRule.riskLevel)}>{severityLabel(selectedNotificationRule.riskLevel)}</Tag>
                            <Tag>{selectedNotificationRule.changeType}</Tag>
                            {!selectedNotificationRule.enabledInTemplate && <Tag color="warning">模板未启用</Tag>}
                          </Space>
                          <Title level={5}>{selectedNotificationRule.title}</Title>
                          <Paragraph>{selectedNotificationRule.description}</Paragraph>
                          <Text type="secondary">{selectedNotificationRule.impact}</Text>
                          <Divider />
                          <Text strong>建议检查</Text>
                          <ul className="notification-rule-checks">
                            {(selectedNotificationRule.recommendedChecks || []).map(check => <li key={check}>{check}</li>)}
                          </ul>
                          <Text strong>示例</Text>
                          <pre className="notification-rule-example">{selectedNotificationRule.example || '-'}</pre>
                        </Space>
                      </div>
                    ) : (
                      <Empty description="请选择提醒类型" />
                    )}
                  </Col>
                </Row>
                <div className="settings-action-row">
                  <Button type="primary" loading={notificationSaving} disabled={!notificationRules || !notificationRulesDirty} onClick={saveNotificationRules}>保存配置</Button>
                </div>
              </>
            ) : (
              <Empty description="当前模板暂无卡片提醒类型配置" />
            )}
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
          <Text strong>AI Review 设置</Text>
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
        >
          {profileDraft ? (
            <Space direction="vertical" size="middle" className="full-width">
              <div className="settings-subsection">
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
              <div className="settings-subsection">
                <Space direction="vertical" size="middle" className="full-width">
                  <Space direction="vertical" size={4}>
                    <Text strong>项目组 AI Review 策略</Text>
                    <Text type="secondary">
                      按项目组控制是否自动触发 AI Review、是否生成修复预览，以及 Push 触发策略。
                    </Text>
                  </Space>
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
                        <Text strong>自动生成风险等级</Text>
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
                    <Text type="secondary">按项目组判断 GitLab Push 事件是否允许自动进入 AI Review；未放行的 Push 仍会保留规则提醒和审查记录。</Text>
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
                        min={0}
                        value={pushPolicyDraft?.pushMinChangedFiles}
                        onChange={value => updatePushPolicyDraft('pushMinChangedFiles', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最小 Diff 字节</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={0}
                        value={pushPolicyDraft?.pushMinDiffBytes}
                        onChange={value => updatePushPolicyDraft('pushMinDiffBytes', value)}
                      />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最小 Commit 数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={0}
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
                      <Text type="secondary">-1 表示无限制</Text>
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>最大 Diff 字节</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={-1}
                        value={pushPolicyDraft?.pushMaxDiffBytes}
                        onChange={value => updatePushPolicyDraft('pushMaxDiffBytes', value)}
                      />
                      <Text type="secondary">-1 表示无限制</Text>
                    </Col>
                    <Col xs={24} md={8}>
                      <Text strong>Debounce 秒数</Text>
                      <InputNumber
                        className="full-width prompt-field"
                        min={0}
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
            </Space>
          ) : (
            <Empty description="暂无 AI Review 设置" />
          )}
        </Card>
      )
    }
  ];

  const orderedCollapseItems = ['global-settings', 'project-target-configs', 'provider-settings', 'profile-settings', 'notification-rules']
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
  const verificationItems = [
    '创建测试分支并提交变更。',
    '创建或更新 Merge Request。',
    '打开平台“任务”页，确认出现新的审查任务。',
    '进入任务详情，确认能看到提醒卡片和分析结果。',
    '打开钉钉群，确认收到包含“变更审查结果”的消息。',
    '点击钉钉消息中的详情链接，确认能打开对应任务详情页。'
  ];

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
            <Paragraph>先创建或复用已有项目组。项目组通常按业务线、团队或产品域划分，用于：</Paragraph>
            <HelpCodeBlock>{`归类多个 GitLab 项目
筛选任务列表
配置项目组钉钉机器人
配置默认 AI Review Profile
配置默认模型 Provider
维护 Push 审核策略`}</HelpCodeBlock>
            <Paragraph>
              给项目组配置钉钉机器人时，把上一步从钉钉复制的 Webhook URL 填入该项目组的机器人配置，并启用它。
              平台只会按项目所属项目组发送通知；该项目组未配置机器人时，本次通知会记录为跳过。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-27_11-10-57.png"
              alt="平台项目组与钉钉机器人配置示例"
            />
          </div>
        </section>

        <section className="help-section">
          <div className="help-section-number">四</div>
          <div className="help-section-content">
            <Title level={3}>配置 GitLab 项目</Title>
            <Paragraph>
              首次收到某个 GitLab 项目的 Webhook 后，平台可以自动创建项目记录。自动创建的项目会进入默认项目组，后续可以再人工调整。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/cd00250a14cb455e95f79c07f7cd6a03.png"
              alt="平台 GitLab 项目配置示例"
            />
          </div>
        </section>

        <section className="help-section">
          <div className="help-section-number">五</div>
          <div className="help-section-content">
            <Title level={3}>配置模型 Provider 和默认模型</Title>
            <Paragraph>
              如果项目只需要规则提醒和钉钉通知，可以先跳过模型配置。需要启用代码质量 AI Review 时，
              先在设置页配置全局 Provider，再为项目组选择默认 AI Review Profile 和默认 Provider。
            </Paragraph>
            <HelpCodeBlock>{`Provider 已启用
API Key 已填写
Endpoint URL 已填写
Model 名称已填写
点击“测试联通性”确认模型服务可访问
全局默认 Provider 已设置`}</HelpCodeBlock>
            <Paragraph>
              当前内置 Provider 包括 OpenAI、Anthropic、DeepSeek、XiaoMIMO 和自定义 OpenAI-compatible。
              “测试联通性”会使用当前表单中的端点、模型名称和临时输入的 API Key 发起一次最小请求，不会保存临时 Key。
            </Paragraph>
            <Paragraph>
              项目组默认 Provider 会作为该组项目的默认模型选择。单个项目或端类型如果有特殊需要，仍可以在项目端类型配置中覆盖 Provider 和 Profile。
            </Paragraph>
            <HelpImage
              src="https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-27_11-27-25.png"
              alt="模型 Provider 和默认模型配置示例"
            />
          </div>
        </section>

        <section className="help-section">
          <div className="help-section-number">六</div>
          <div className="help-section-content">
            <Title level={3}>首次验证</Title>
            <Paragraph>配置完成后，用一次真实 Merge Request 做端到端验证。</Paragraph>
            <Timeline
              className="help-timeline"
              items={verificationItems.map(item => ({
                content: item
              }))}
            />
          </div>
        </section>
      </div>
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

  const openFixPreviewFromQueue = (taskId, findingIndex) => {
    if (!taskId || findingIndex == null) return;
    setJobQueueOpen(false);
    navigate(`/tasks/${taskId}#fix-preview-${findingIndex}`, { state: { from: route } });
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
          AI 变更提醒与代码质量审查平台
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
        onOpenFixPreview={openFixPreviewFromQueue}
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
