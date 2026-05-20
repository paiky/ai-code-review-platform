import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  Layout,
  message,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography
} from 'antd';
import {
  ArrowLeftOutlined,
  CloseOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined
} from '@ant-design/icons';
import { fetchApi, riskColor, statusColor } from './api.js';

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
      return '严重';
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

function codeQualitySummary(review, findings) {
  if (review?.status === 'RUNNING') return 'AI Review 正在执行，完成后会自动刷新。';
  if (review?.status === 'FAILED') return review?.errorMessage || 'AI Review 执行失败。';
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

const focusIndicatorMeta = {
  DB_SCHEMA_CHANGE: { label: 'DB 表/字段', color: 'volcano' },
  MQ_CONFIG_CHANGE: { label: 'MQ 配置', color: 'blue' },
  REDIS_CONFIG_CHANGE: { label: 'Redis 配置', color: 'green' },
  VALUE_CONFIG_CHANGE: { label: '@Value', color: 'purple' }
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
  if (['DB', 'DB_SCHEMA', 'DB_SQL', 'ORM_MAPPING', 'ENTITY_MODEL', 'DATA_MIGRATION'].includes(category)) return 'DB';
  if (['MQ', 'MQ_PRODUCER', 'MQ_CONSUMER', 'MQ_MESSAGE_SCHEMA', 'MQ_TOPIC_CONFIG', 'MQ_RETRY_DLQ'].includes(category)) return 'MQ';
  if (['CACHE', 'CACHE_KEY', 'CACHE_TTL', 'CACHE_INVALIDATION', 'CACHE_READ_WRITE', 'CACHE_SERIALIZATION'].includes(category)) return 'CACHE';
  if (category === 'CONFIG') return 'CONFIG';
  return category || 'OTHER';
}

const reminderGroupMeta = {
  DB: { label: 'DB 变更提醒', color: 'volcano', sort: 1 },
  MQ: { label: 'MQ 变更提醒', color: 'blue', sort: 2 },
  CACHE: { label: 'Redis/缓存提醒', color: 'green', sort: 3 },
  CONFIG: { label: '配置提醒', color: 'purple', sort: 4 },
  OTHER: { label: '其他提醒', color: 'default', sort: 99 }
};

function buildReminderGroups(riskItems) {
  const groups = new Map();
  for (const item of riskItems) {
    const key = reminderGroupKey(item.category);
    const meta = reminderGroupMeta[key] || {
      label: `${changeTypeLabel(item.category)}提醒`,
      color: 'default',
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

function TaskList({ onOpen }) {
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
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
    load({ pageNo: 1 });
  }, []);

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '项目', dataIndex: 'projectName', ellipsis: true },
    { title: '类型', dataIndex: 'triggerType', width: 90, render: value => <Tag>{taskTypeLabel(value)}</Tag> },
    { title: '分支', width: 260, render: (_, row) => <Text>{row.sourceBranch || '-'}{' -> '}{row.targetBranch || '-'}</Text> },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={statusColor(value)}>{value || '-'}</Tag> },
    { title: '重点变更', dataIndex: 'focusIndicators', width: 240, render: value => <FocusIndicatorTags indicators={value} muted /> },
    { title: '提醒项', dataIndex: 'riskItemCount', width: 90, render: value => value ?? 0 },
    { title: '创建时间', dataIndex: 'createdAt', width: 180 },
    { title: '操作', width: 90, render: (_, row) => <Button type="link" onClick={() => onOpen(row.id)}>详情</Button> }
  ];

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <Title level={3}>审查任务</Title>
          <Text type="secondary">查看 GitLab MR 触发的变更风险审查记录</Text>
        </div>
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="项目、分支或任务"
            value={keyword}
            onChange={event => setKeyword(event.target.value)}
            onPressEnter={() => load({ pageNo: 1 })}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load({ pageNo: 1 })}>刷新</Button>
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
          pagination={{
            current: pagination.pageNo,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
          }}
        />
      </Card>
    </div>
  );
}

function RiskCardView({ riskCard }) {
  if (!riskCard) return <Empty description="暂无提醒卡片" />;

  const riskItems = (riskCard.riskItems || []).filter(item => item.ruleCode !== 'API_COMPATIBILITY_CHECK' && item.category !== 'API');
  const reminderGroups = buildReminderGroups(riskItems);
  const roles = riskCard.suggestedReviewRoles || [];

  const evidenceColumns = [
    { title: '文件', dataIndex: 'filePath', ellipsis: true },
    { title: '规则', dataIndex: 'matcher', width: 180, ellipsis: true },
    {
      title: '片段',
      dataIndex: 'snippet',
      ellipsis: true,
      render: value => value ? <Text code className="evidence-snippet">{value}</Text> : '-'
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
          items={reminderGroups.map(group => ({
            key: group.key,
            label: (
              <Space className="risk-item-heading" wrap>
                <Tag color={group.color}>{group.items.length} 条</Tag>
                <Text strong>{group.label}</Text>
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
                items={group.items.map(item => ({
                  key: item.riskId,
                  label: (
                    <Space className="risk-item-heading" wrap>
                      <Tag color={fineChangeTypes.has(item.category) ? 'blue' : 'default'}>{changeTypeLabel(item.category)}</Tag>
                      <Text strong>{item.title}</Text>
                    </Space>
                  ),
                  children: (
                    <Space direction="vertical" className="full-width">
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
  'CUSTOM_FAILED'
]);

function isDebugProgressEvent(event) {
  return event?.level === 'DEBUG' || event?.phase === 'CODEX_OUTPUT';
}

function isKeyProgressEvent(event) {
  return keyProgressPhases.has(event?.phase) || ['WARN', 'ERROR'].includes(event?.level);
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

function CodeQualityProgressView({ progress }) {
  const events = Array.isArray(progress) ? progress : [];
  const keyEvents = events.filter(isKeyProgressEvent);
  const debugEvents = events.filter(isDebugProgressEvent);
  const hiddenEvents = events.filter(event => !isKeyProgressEvent(event) && !isDebugProgressEvent(event));
  const totalDurationText = formatDuration(totalProgressDuration(events));
  return (
    <Card title="执行过程">
      {events.length === 0 ? (
        <Empty description="暂无执行过程记录" />
      ) : (
        <Space direction="vertical" size="middle" className="full-width">
          <Alert
            type="info"
            showIcon
            message={totalDurationText ? `总计耗时 ${totalDurationText}` : '默认只展示关键阶段'}
            description={`已折叠 ${debugEvents.length} 条 Codex stdout/stderr 调试输出${hiddenEvents.length > 0 ? `，以及 ${hiddenEvents.length} 条辅助事件` : ''}。`}
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

function CodeQualityReviewView({ review, progress, onRetry, retrying }) {
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
          {review.errorMessage && <Alert type="error" showIcon message="AI Review 执行失败" description={review.errorMessage} />}
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
            items={findings.map((finding, index) => ({
              key: `${finding.filePath || 'file'}-${finding.startLine || index}-${index}`,
              label: (
                <Space className="risk-item-heading" wrap>
                  <Tag color={severityColor(finding.severity)}>{severityLabel(finding.severity)}</Tag>
                  {finding.category && <Tag color="blue">{categoryLabel(finding.category)}</Tag>}
                  {finding.confidence && <Tag color={confidenceColor(finding.confidence)}>置信度 {confidenceLabel(finding.confidence)}</Tag>}
                  <Text strong>{cleanAiMarkdown(finding.title) || '未命名问题'}</Text>
                </Space>
              ),
              children: (
                <Space direction="vertical" className="full-width">
                  <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                    <Descriptions.Item label="位置" span={2}>
                      <Text code className="code-location-text">
                        {codeLocationText(finding.filePath, finding.startLine, finding.endLine)}
                      </Text>
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
      <CodeQualityProgressView progress={progress} />
      {review.rawOutput && (
        <Collapse
          items={[{
            key: 'raw-output',
            label: 'Raw Output',
            children: <pre className="raw-output-block">{review.rawOutput}</pre>
          }]}
        />
      )}
    </Space>
  );
}

function TaskDetail({ taskId, onBack, onOpen }) {
  const [detail, setDetail] = useState(null);
  const [result, setResult] = useState(null);
  const [codeQualityResult, setCodeQualityResult] = useState(null);
  const [codeQualityProgress, setCodeQualityProgress] = useState([]);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
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
        const progress = await fetchApi(`/api/review-tasks/${taskId}/code-quality-progress`);
        setCodeQualityProgress(Array.isArray(progress) ? progress : []);
      } catch {
        setCodeQualityProgress([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [taskId]);

  useEffect(() => {
    if (codeQualityResult?.status !== 'RUNNING') return undefined;
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [taskId, codeQualityResult?.status]);

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
    { key: 'quality', label: '代码质量 Review', children: <CodeQualityReviewView review={codeQualityResult} progress={codeQualityProgress} onRetry={retryCodeQualityReview} retrying={retrying} /> },
    { key: 'risk', label: '提醒卡片', children: <RiskCardView riskCard={result?.riskCard} /> },
    { key: 'analysis', label: '分析结果', children: <AnalysisView changeAnalysis={result?.changeAnalysis} /> },
    { key: 'event', label: '原始事件摘要', children: <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card title="changedFiles 摘要"><JsonBlock value={detail?.changedFilesSummary} /></Card></Col><Col xs={24} lg={12}><Card title="raw payload"><JsonBlock value={detail?.rawPayload} /></Card></Col></Row> }
  ], [detail, result, codeQualityResult, codeQualityProgress, retrying]);

  return (
    <div className="page-shell">
      <Space className="detail-toolbar">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
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
                  <Title level={3}>{detail.projectName} MR !{detail.mrId}</Title>
                  <Text type="secondary">{detail.sourceBranch || '-'}{' -> '}{detail.targetBranch || '-'}</Text>
                </div>
                <Space>
                  <Tag color={statusColor(detail.status)}>{detail.status}</Tag>
                </Space>
              </div>
              <Divider />
              <Descriptions column={{ xs: 1, md: 2, xl: 3 }} size="small">
                <Descriptions.Item label="任务 ID">{detail.id}</Descriptions.Item>
                <Descriptions.Item label="GitLab 项目">{detail.gitProjectId}</Descriptions.Item>
                <Descriptions.Item label="触发类型">{detail.triggerType}</Descriptions.Item>
                <Descriptions.Item label="作者">{detail.authorName || detail.authorUsername || '-'}</Descriptions.Item>
                <Descriptions.Item label="模板">{detail.templateCode}</Descriptions.Item>
                <Descriptions.Item label="事件时间">{detail.eventTime || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
            <Tabs items={tabItems} />
          </Space>
        ) : !loading ? <Empty description="任务不存在" /> : null}
      </Spin>
    </div>
  );
}


function TemplateConfig() {
  const [templates, setTemplates] = useState([]);
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
  const [promptPreview, setPromptPreview] = useState(null);
  const [aiSettings, setAiSettings] = useState(null);
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [providerApiKeyDraft, setProviderApiKeyDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [notificationSaving, setNotificationSaving] = useState(false);
  const [providerSaving, setProviderSaving] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false);
  const [error, setError] = useState(null);
  const [messageApi, contextHolder] = message.useMessage();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsData, profileData, providerData, templateData] = await Promise.all([
        fetchApi('/api/code-quality-reviews/settings'),
        fetchApi('/api/code-quality-review-profiles'),
        fetchApi('/api/code-quality-review-providers'),
        fetchApi('/api/rule-templates')
      ]);
      const profileItems = Array.isArray(profileData) ? profileData : (profileData.items || []);
      const providerItems = Array.isArray(providerData) ? providerData : (providerData.items || []);
      const templateItems = Array.isArray(templateData) ? templateData : (templateData.items || []);
      const nextSelectedProfileCode = selectedProfileCode || profileItems[0]?.profileCode || null;
      const nextSelectedProviderCode = settingsData?.defaultProviderCode || selectedProviderCode || providerItems[0]?.providerCode || 'DEEPSEEK';
      const nextSelectedTemplateCode = selectedTemplateCode || templateItems.find(item => item.templateCode === 'backend-default')?.templateCode || templateItems[0]?.templateCode || null;
      setAiSettings(settingsData);
      setSettingsDraft({
        mrAutoReviewEnabled: settingsData?.mrAutoReviewEnabled ?? true,
        dingtalkNotificationEnabled: settingsData?.dingtalkNotificationEnabled ?? true,
        dingtalkWebhooks: (settingsData?.dingtalkWebhooks || []).map(item => ({ ...item }))
      });
      setTemplates(templateItems);
      setSelectedTemplateCode(nextSelectedTemplateCode);
      setProviders(providerItems);
      setSelectedProviderCode(nextSelectedProviderCode);
      setProviderDraft(providerItems.find(item => item.providerCode === nextSelectedProviderCode) || providerItems[0] || null);
      setProviderApiKeyDraft('');
      setProfiles(profileItems);
      setSelectedProfileCode(nextSelectedProfileCode);
      setProfileDraft(profileItems.find(item => item.profileCode === nextSelectedProfileCode) || profileItems[0] || null);
      setPromptPreview(null);
      if (nextSelectedTemplateCode) {
        const rules = await fetchApi(`/api/rule-templates/${nextSelectedTemplateCode}/notification-rules`);
        setNotificationRules(rules);
        setNotificationRuleDraftCodes(rules.focusRuleCodes || []);
        const firstSelected = rules.focusRuleCodes?.[0];
        const firstRule = rules.groups?.flatMap(group => group.rules || [])?.[0]?.ruleCode;
        setSelectedNotificationRuleCode(firstSelected || firstRule || null);
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
    const firstSelected = rules.focusRuleCodes?.[0];
    const firstRule = rules.groups?.flatMap(group => group.rules || [])?.[0]?.ruleCode;
    setSelectedNotificationRuleCode(firstSelected || firstRule || null);
  };

  const updateSettingsDraft = (field, value) => {
    setSettingsDraft(current => current ? { ...current, [field]: value } : current);
  };

  const updateWebhookDraft = (index, field, value) => {
    setSettingsDraft(current => {
      if (!current) return current;
      const dingtalkWebhooks = current.dingtalkWebhooks.map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      ));
      return { ...current, dingtalkWebhooks };
    });
  };

  const addWebhookDraft = () => {
    setSettingsDraft(current => {
      if (!current) return current;
      return {
        ...current,
        dingtalkWebhooks: [
          ...current.dingtalkWebhooks,
          { id: null, name: '', channel: 'DINGTALK', webhookUrl: '', enabled: true, status: 'ENABLED' }
        ]
      };
    });
  };

  const removeWebhookDraft = (index) => {
    setSettingsDraft(current => {
      if (!current) return current;
      return {
        ...current,
        dingtalkWebhooks: current.dingtalkWebhooks.filter((_, itemIndex) => itemIndex !== index)
      };
    });
  };

  const validateSettingsDraft = () => {
    const webhooks = settingsDraft?.dingtalkWebhooks || [];
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
      if (item.enabled) {
        const normalized = webhookUrl.toLowerCase();
        if (enabledUrls.has(normalized)) return '已启用的 webhook 地址不能重复';
        enabledUrls.add(normalized);
      }
    }
    return null;
  };

  const saveAiSettings = async () => {
    if (!settingsDraft) return;
    const validationError = validateSettingsDraft();
    if (validationError) {
      messageApi.error(validationError);
      return;
    }
    setSettingsSaving(true);
    try {
      const settings = await fetchApi('/api/code-quality-reviews/settings', {
        method: 'PUT',
        body: JSON.stringify({
          mrAutoReviewEnabled: settingsDraft.mrAutoReviewEnabled,
          dingtalkNotificationEnabled: settingsDraft.dingtalkNotificationEnabled,
          dingtalkWebhooks: settingsDraft.dingtalkWebhooks.map(item => ({
            id: item.id || undefined,
            name: (item.name || '').trim(),
            channel: 'DINGTALK',
            webhookUrl: (item.webhookUrl || '').trim(),
            enabled: item.enabled !== false
          }))
        })
      });
      setAiSettings(settings);
      setSettingsDraft({
        mrAutoReviewEnabled: settings?.mrAutoReviewEnabled ?? true,
        dingtalkNotificationEnabled: settings?.dingtalkNotificationEnabled ?? true,
        dingtalkWebhooks: (settings?.dingtalkWebhooks || []).map(item => ({ ...item }))
      });
      const testResults = settings?.webhookTestResults || [];
      const failedTestCount = testResults.filter(item => item.status !== 'SUCCESS').length;
      if (testResults.length === 0) {
        messageApi.success('全局设置已保存');
      } else if (failedTestCount === 0) {
        messageApi.success(`全局设置已保存，已向 ${testResults.length} 个新 webhook 发送测试通知`);
      } else {
        messageApi.warning(`全局设置已保存，但有 ${failedTestCount} 个新 webhook 测试通知未成功`);
      }
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  const selectTemplate = async (templateCode) => {
    setSelectedTemplateCode(templateCode);
    setNotificationRules(null);
    setNotificationRuleDraftCodes([]);
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
      messageApi.success('提醒类型已保存');
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
  };

  const updateProviderDraft = (field, value) => {
    setProviderDraft(current => current ? { ...current, [field]: value } : current);
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
      messageApi.success(`${sourceLabel(providerDraft.providerCode)} Key 已清除`);
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProviderSaving(false);
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
      messageApi.success('AI Review Profile 已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProfileSaving(false);
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
    setProfileSaving(true);
    try {
      const updated = await fetchApi(`/api/code-quality-review-profiles/${profileDraft.profileCode}/reset-default-prompt`, {
        method: 'POST'
      });
      setProfiles(current => current.map(item => item.profileCode === updated.profileCode ? updated : item));
      setProfileDraft(updated);
      setPromptPreview(null);
      messageApi.success('Agent Prompt 已恢复默认');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const profileOptions = profiles.map(profile => ({
    label: `${profile.profileName} (${profile.profileCode})`,
    value: profile.profileCode
  }));
  const providerOptions = providers.map(provider => ({
    label: provider.providerName || sourceLabel(provider.providerCode),
    value: provider.providerCode
  }));
  const profileProviderOptions = [{ label: '使用当前模型 Provider', value: '' }, ...providerOptions];
  const providerApiKeyPlaceholder = '留空表示不更新当前 API Key';
  const templateOptions = templates.map(template => ({
    label: `${template.templateName} (${template.templateCode})`,
    value: template.templateCode
  }));
  const notificationRuleItems = notificationRules?.groups?.flatMap(group => group.rules || []) || [];
  const selectedNotificationRule = notificationRuleItems.find(rule => rule.ruleCode === selectedNotificationRuleCode) || notificationRuleItems[0] || null;
  const notificationRulesDirty = JSON.stringify(notificationRuleDraftCodes) !== JSON.stringify(notificationRules?.focusRuleCodes || []);
  const settingsDirty = JSON.stringify({
    mrAutoReviewEnabled: settingsDraft?.mrAutoReviewEnabled ?? true,
    dingtalkNotificationEnabled: settingsDraft?.dingtalkNotificationEnabled ?? true,
    dingtalkWebhooks: settingsDraft?.dingtalkWebhooks || []
  }) !== JSON.stringify({
    mrAutoReviewEnabled: aiSettings?.mrAutoReviewEnabled ?? true,
    dingtalkNotificationEnabled: aiSettings?.dingtalkNotificationEnabled ?? true,
    dingtalkWebhooks: aiSettings?.dingtalkWebhooks || []
  });
  const configuredWebhookCount = (settingsDraft?.dingtalkWebhooks || []).filter(item => item.enabled !== false).length;

  const collapseItems = [
    {
      key: 'global-settings',
      label: (
        <Space wrap>
          <Text strong>AI Review 全局设置</Text>
          <Tag color={(settingsDraft?.mrAutoReviewEnabled ?? true) ? 'green' : 'default'}>MR 自动 {(settingsDraft?.mrAutoReviewEnabled ?? true) ? '开启' : '关闭'}</Tag>
          <Tag color={(settingsDraft?.dingtalkNotificationEnabled ?? true) ? 'blue' : 'default'}>钉钉 {(settingsDraft?.dingtalkNotificationEnabled ?? true) ? '开启' : '关闭'}</Tag>
          <Tag>{configuredWebhookCount} 个 webhook</Tag>
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
          extra={<Button type="primary" loading={settingsSaving} disabled={!settingsDraft || !settingsDirty} onClick={saveAiSettings}>保存设置</Button>}
        >
          <Space direction="vertical" size="middle" className="global-settings-stack">
            <div className="global-setting-field">
              <div className="settings-inline-head">
                <Text strong>GitLab MR 自动触发 AI Review</Text>
                <Switch
                  checked={settingsDraft?.mrAutoReviewEnabled ?? true}
                  loading={settingsSaving}
                  checkedChildren="开启"
                  unCheckedChildren="关闭"
                  onChange={checked => updateSettingsDraft('mrAutoReviewEnabled', checked)}
                />
              </div>
              <Text type="secondary" className="settings-description">
                关闭后，新的 MR webhook 仍会执行规则风险审查，但不会启动代码质量 Review。
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
                  onChange={checked => updateSettingsDraft('dingtalkNotificationEnabled', checked)}
                />
              </div>
              <Text type="secondary" className="settings-description">
                关闭后，规则审查和 AI Review 仍会正常执行与落库，但不会向钉钉发送消息。
              </Text>
            </div>
            <div className="global-setting-field full-width">
              <div className="settings-inline-head">
                <Text strong>钉钉机器人 Webhook</Text>
                <Button icon={<PlusOutlined />} onClick={addWebhookDraft}>新增 Webhook</Button>
              </div>
              <Text type="secondary" className="settings-description">
                支持配置多个 webhook。开启钉钉推送后，平台会向所有已启用的 webhook 群发通知。
              </Text>
              <Space direction="vertical" size="middle" className="full-width webhook-list">
                {(settingsDraft?.dingtalkWebhooks || []).length > 0 ? (
                  (settingsDraft?.dingtalkWebhooks || []).map((item, index) => (
                    <div key={item.id || `draft-${index}`} className="webhook-item">
                      <Row gutter={[12, 12]} align="middle">
                        <Col xs={24} lg={6}>
                          <Text strong>名称</Text>
                          <Input
                            className="prompt-field"
                            value={item.name || ''}
                            placeholder="例如 研发群"
                            onChange={event => updateWebhookDraft(index, 'name', event.target.value)}
                          />
                        </Col>
                        <Col xs={24} lg={13}>
                          <Text strong>Webhook URL</Text>
                          <Input
                            className="prompt-field"
                            value={item.webhookUrl || ''}
                            placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
                            onChange={event => updateWebhookDraft(index, 'webhookUrl', event.target.value)}
                          />
                        </Col>
                        <Col xs={12} lg={3}>
                          <Text strong>启用</Text>
                          <div className="prompt-field">
                            <Switch
                              checked={item.enabled !== false}
                              checkedChildren="开启"
                              unCheckedChildren="关闭"
                              onChange={checked => updateWebhookDraft(index, 'enabled', checked)}
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
                              onClick={() => removeWebhookDraft(index)}
                            />
                          </div>
                        </Col>
                      </Row>
                    </div>
                  ))
                ) : (
                  <Empty description="暂未配置钉钉 webhook" />
                )}
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
          <Text strong>卡片提醒类型</Text>
          <Tag>{notificationRuleDraftCodes.length} 个已选</Tag>
          {notificationRulesDirty && <Tag color="gold">未保存</Tag>}
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
          extra={<Button type="primary" loading={notificationSaving} disabled={!notificationRules || !notificationRulesDirty} onClick={saveNotificationRules}>保存配置</Button>}
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
                  <Text type="secondary">已选择 {notificationRuleDraftCodes.length} 个提醒类型</Text>
                  {notificationRuleDraftCodes.map(code => <Tag key={code} color="blue">{code}</Tag>)}
                </Space>
              </Col>
            </Row>
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                {notificationRules ? (
                  <Collapse
                    defaultActiveKey={(notificationRules.groups || []).map(group => group.groupCode)}
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
          extra={<Button type="primary" loading={providerSaving} onClick={saveProviderSettings} disabled={!providerDraft}>保存 Provider</Button>}
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
        </Card>
      )
    },
    {
      key: 'profile-settings',
      label: (
        <Space wrap>
          <Text strong>AI Review Profile</Text>
          {selectedProfileCode && <Tag>{selectedProfileCode}</Tag>}
        </Space>
      ),
      children: (
        <Card
          bordered={false}
          className="settings-inner-card"
          extra={
            <Space wrap>
              <Button loading={promptPreviewLoading} onClick={previewRenderedPrompt} disabled={!profileDraft}>预览 Prompt</Button>
              <Button loading={profileSaving} onClick={resetProfilePrompt} disabled={!profileDraft}>恢复默认</Button>
              <Button type="primary" loading={profileSaving} onClick={saveProfilePrompt} disabled={!profileDraft}>保存 Profile</Button>
            </Space>
          }
        >
          {profileDraft ? (
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
                <Col xs={24} lg={14}>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={12}>
                      <Text strong>Provider 覆盖</Text>
                      <Select
                        className="full-width prompt-field"
                        value={profileDraft.providerCode || ''}
                        options={profileProviderOptions}
                        onChange={value => updateProfileDraft('providerCode', value || null)}
                      />
                    </Col>
                    <Col xs={24} md={12}>
                      <Text strong>模型覆盖</Text>
                      <Input
                        className="prompt-field"
                        placeholder="留空使用后端默认模型"
                        value={profileDraft.model || ''}
                        onChange={event => updateProfileDraft('model', event.target.value)}
                      />
                    </Col>
                    <Col xs={24}>
                      <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                        <Descriptions.Item label="MR 自动">{profileDraft.triggerOnMr ? '开启' : '关闭'}</Descriptions.Item>
                        <Descriptions.Item label="手动触发">{profileDraft.triggerOnManual ? '开启' : '关闭'}</Descriptions.Item>
                      </Descriptions>
                    </Col>
                  </Row>
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
            </Space>
          ) : (
            <Empty description="暂无 AI Review Profile" />
          )}
        </Card>
      )
    }
  ];

  return (
    <div className="page-shell">
      {contextHolder}
      <div className="settings-actions">
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </div>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        <Collapse className="settings-collapse" items={collapseItems} />
      </Spin>
    </div>
  );
}
export default function App() {
  const initialTaskId = new URLSearchParams(window.location.search).get('taskId');
  const [selectedTaskId, setSelectedTaskId] = useState(initialTaskId ? Number(initialTaskId) : null);
  const [view, setView] = useState('tasks');

  const openTasks = () => {
    setSelectedTaskId(null);
    setView('tasks');
    window.history.replaceState({}, '', window.location.pathname);
  };

  const openTemplates = () => {
    setSelectedTaskId(null);
    setView('templates');
    window.history.replaceState({}, '', window.location.pathname);
  };

  const openTaskDetail = (taskId) => {
    setSelectedTaskId(taskId);
    setView('tasks');
    window.history.replaceState({}, '', `${window.location.pathname}?taskId=${taskId}`);
  };

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="brand">AI 变更风险审查平台</div>
        <Space className="top-nav">
          <Button icon={<UnorderedListOutlined />} type={view === 'tasks' ? 'primary' : 'default'} onClick={openTasks}>任务</Button>
          <Button icon={<SettingOutlined />} type={view === 'templates' ? 'primary' : 'default'} onClick={openTemplates}>设置</Button>
        </Space>
      </Header>
      <Content>
        {selectedTaskId ? (
          <TaskDetail taskId={selectedTaskId} onBack={openTasks} onOpen={openTaskDetail} />
        ) : view === 'templates' ? (
          <TemplateConfig />
        ) : (
          <TaskList onOpen={openTaskDetail} />
        )}
      </Content>
    </Layout>
  );
}
