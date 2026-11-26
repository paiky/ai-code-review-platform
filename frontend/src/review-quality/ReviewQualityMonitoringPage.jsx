import { useEffect, useRef, useState } from 'react';
import { Link, useMatch, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Pagination,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography
} from 'antd';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  SaveOutlined
} from '@ant-design/icons';

import { fetchApi } from '../api.js';
import { REVIEW_QUALITY_MONITOR_ROUTE } from '../appShell.js';

const { Text, Title } = Typography;
const MONITORING_API = '/api/review-quality/monitoring';
const ISSUE_STATUSES = [
  { value: 'PENDING_REVIEW', label: '待复核' },
  { value: 'CONFIRMED', label: '已确认' },
  { value: 'VERIFYING', label: '验证中' },
  { value: 'CLOSED', label: '已关闭' },
  { value: 'DISMISSED', label: '已排除' }
];
const HISTORY_PAGE_SIZE = 10;
const SHANGHAI_DATETIME = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short'
});
const SHANGHAI_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
});
const NUMBER_FORMAT = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });
const RATIO_FORMAT = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 2 });
const GROUP_LABELS = { MR: 'MR', PUSH: 'Push', MANUAL: '手动', OTHER: '其他', STANDARD: 'Standard' };
const METRIC_UNITS = { BYTES: ' B', MS: ' ms', CHARS: ' 字符', ROWS: ' 行' };
const ISSUE_PRIORITIES = { HIGH: ['red', '高'], MEDIUM: ['gold', '中'], LOW: ['blue', '低'] };

function monitoringHref(projectId, path = '', params = {}) {
  const query = new URLSearchParams({ ...(projectId ? { projectId } : {}), ...params });
  return `${REVIEW_QUALITY_MONITOR_ROUTE}${path}${query.size ? `?${query}` : ''}`;
}

function makeRequest(projectId, path, { method, body, params, signal } = {}) {
  const query = new URLSearchParams({ projectId, ...params });
  return fetchApi(`${MONITORING_API}${path}?${query}`, {
    method,
    body: body ? JSON.stringify(body) : undefined,
    signal
  });
}

function statusLabel(value) {
  return {
    RUNNING: '生成中', SUCCEEDED: '已生成', FAILED: '失败',
    PENDING_REVIEW: '待复核', CONFIRMED: '已确认', VERIFYING: '验证中',
    CLOSED: '已关闭', DISMISSED: '已排除'
  }[value] || value || '未知';
}

function statusColor(value) {
  return {
    RUNNING: 'processing', SUCCEEDED: 'success', FAILED: 'error',
    CONFIRMED: 'blue', VERIFYING: 'processing', CLOSED: 'success', DISMISSED: 'default'
  }[value] || 'warning';
}

function formatTimestamp(value) {
  if (!value) return '-';
  const time = String(value).replace(' ', 'T');
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(time) ? time : `${time}Z`);
  if (Number.isNaN(date.valueOf())) return '-';
  return SHANGHAI_DATETIME.format(date);
}

function makeDefaultRange() {
  const today = SHANGHAI_DATE.format(new Date());
  const end = new Date(`${today}T00:00:00+08:00`);
  return [SHANGHAI_DATE.format(new Date(end.getTime() - 7 * 86400000)), today];
}

function formatMetric(value, unit) {
  if (value == null) return '未知';
  if (unit === 'RATIO') return RATIO_FORMAT.format(value);
  return `${NUMBER_FORMAT.format(value)}${METRIC_UNITS[unit] || ''}`;
}

function requestError(error) {
  return {
    404: '记录不可用，或审查质量监测已关闭。',
    409: '记录已更新。请刷新后重试。',
    422: '请求数据有误。请核对观察区间或关联记录 ID。'
  }[error?.status] || error?.message || '请求未完成，请重试。';
}

function MonitoringSummary({ report }) {
  const metrics = Array.isArray(report?.snapshot?.metrics) ? report.snapshot.metrics : [];
  const issues = Array.isArray(report?.snapshot?.issues) ? report.snapshot.issues : [];
  if (report?.status !== 'SUCCEEDED') return null;

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      {metrics.length > 0 && (
        <Card size="small" title="监测指标">
          <Table
            rowKey={row => `${row.engine}-${row.key}-${row.group || ''}`}
            size="small"
            pagination={false}
            dataSource={metrics}
            scroll={{ x: 720 }}
            columns={[
              { title: '范围', width: 140, render: (_, row) => [row.engine, GROUP_LABELS[row.group] || row.group].filter(Boolean).join(' · ') || '全部' },
              { title: '指标', dataIndex: 'label', width: 230 },
              { title: '可观测', dataIndex: 'observedCount', width: 100, render: value => value ?? '未知' },
              { title: '适用样本', dataIndex: 'eligibleCount', width: 100, render: value => value ?? '未知' },
              { title: '未知', dataIndex: 'unknownCount', width: 90, render: value => value ?? '未知' },
              { title: '结果', dataIndex: 'value', width: 130, render: (value, row) => formatMetric(value, row.unit) }
            ]}
          />
        </Card>
      )}
      {report.snapshot.truncated && <Alert type="warning" showIcon message="报告已截断，指标和问题列表按记录上限保存。" />}
      <IssueList issues={issues} projectId={report.projectId} />
    </Space>
  );
}

function IssueList({ issues, projectId }) {
  if (issues.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本期未生成待跟进问题" />;
  return (
    <Card size="small" title="待跟进问题">
      <Table
        rowKey="issueId"
        size="small"
        pagination={false}
        dataSource={issues}
        scroll={{ x: 1070 }}
        columns={[
          { title: '优先级', dataIndex: 'priority', width: 100, render: value => {
            const [color, label] = ISSUE_PRIORITIES[value] || ['default', '待复核'];
            return <Tag color={color}>{label}</Tag>;
          } },
          { title: '问题', dataIndex: 'title', width: 290, render: (value, row) => <Space direction="vertical" size={0}><Text strong>{value}</Text><Text type="secondary">{row.engine} · {row.issueType} · {row.diagnosticType}</Text></Space> },
          { title: '影响任务', dataIndex: 'affectedTaskCount', width: 105, render: value => value ?? '未知' },
          { title: '异常 / 可观测', width: 120, render: (_, row) => `${row.eventCount ?? '未知'} / ${row.observedCount ?? '未知'}` },
          { title: '最后出现', dataIndex: 'lastSeenAt', width: 160, render: formatTimestamp },
          {
            title: '样本任务', dataIndex: 'samples', width: 190,
            render: samples => samples?.length ? (
              <Space direction="vertical" size={3}>
                {samples.map(sample => (
                  <Link key={`${sample.taskId}-${sample.reviewKey}-${sample.runId}-${sample.eventId}`} to={taskHref(sample)}>
                    #{sample.taskId}{sample.runId ? ` · Run #${sample.runId}` : ''}
                  </Link>
                ))}
              </Space>
            ) : '-'
          },
          {
            title: '操作', width: 100, fixed: 'right',
            render: (_, row) => <Link to={monitoringHref(projectId, `/issues/${row.issueId}`)}>处置</Link>
          }
        ]}
      />
    </Card>
  );
}

function taskHref(sample) {
  const query = sample.reviewKey ? `?reviewKey=${encodeURIComponent(sample.reviewKey)}` : '';
  return `/tasks/${sample.taskId}${query}`;
}

function ReportDetail({ report, onRetry, retrying }) {
  const isFailed = report.status === 'FAILED';
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small">
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
          <Descriptions.Item label="报告">#{report.id}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color={statusColor(report.status)}>{statusLabel(report.status)}</Tag></Descriptions.Item>
          <Descriptions.Item label="来源">{report.source === 'SCHEDULED' ? '定时' : '手动'}</Descriptions.Item>
          <Descriptions.Item label="项目">{report.projectId}</Descriptions.Item>
          <Descriptions.Item label="观察区间">{formatTimestamp(report.startAt)} 至 {formatTimestamp(report.endAt)}</Descriptions.Item>
          <Descriptions.Item label="规则版本">{report.ruleVersion || '未知'}</Descriptions.Item>
          <Descriptions.Item label="生成时间">{formatTimestamp(report.createdAt)}</Descriptions.Item>
          {report.errorCode && <Descriptions.Item label="错误码">{report.errorCode}</Descriptions.Item>}
        </Descriptions>
        {isFailed && (
          <Button icon={<ReloadOutlined />} loading={retrying} onClick={() => onRetry(report.id)}>
            重试报告生成
          </Button>
        )}
        {report.status === 'SUCCEEDED' && <Link to={monitoringHref(report.projectId, '/compare', { baselineId: report.id })}>以本报告为基线</Link>}
      </Card>
      {report.snapshot ? <MonitoringSummary report={report} /> : (
        <Alert showIcon type={report.status === 'FAILED' ? 'error' : 'info'} message={report.status === 'FAILED' ? '报告生成失败' : '报告正在生成'} description={report.errorCode || undefined} />
      )}
    </Space>
  );
}

function IssueDetail({ issueId, projectId }) {
  const [issue, setIssue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [refresh, setRefresh] = useState(0);

  const setSavedIssue = data => {
    setIssue(data);
    setDraft({
      version: data.version,
      status: data.status,
      assignee: data.assignee || '',
      resolution: data.resolution || '',
      acceptanceCriteria: data.acceptanceCriteria || '',
      evaluationCaseId: data.evaluationCaseId ?? null,
      evaluationRunId: data.evaluationRunId ?? null
    });
  };

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    makeRequest(projectId, `/issues/${issueId}`, { signal: controller.signal })
      .then(setSavedIssue)
      .catch(error => {
        if (!controller.signal.aborted) setError(error);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, issueId, refresh]);

  const saveIssue = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const data = await makeRequest(projectId, `/issues/${issueId}`, {
        method: 'PATCH',
        body: {
          ...draft,
          assignee: draft.assignee.trim() || null,
          resolution: draft.resolution.trim() || null,
          acceptanceCriteria: draft.acceptanceCriteria.trim() || null
        }
      });
      setSavedIssue(data);
      message.success('问题状态已保存');
    } catch (error) {
      setError(error);
    } finally {
      setSaving(false);
    }
  };

  if (loading && !issue) return <Spin />;
  const errorView = error && (
    <Alert
      type={error.status === 409 ? 'warning' : 'error'}
      showIcon
      title={error.status === 409 ? '问题已被其他人更新。重新读取会替换当前草稿。' : requestError(error)}
      action={<Button size="small" onClick={() => setRefresh(value => value + 1)}>重新读取</Button>}
    />
  );
  if (!issue || !draft) return errorView || <Empty description="问题记录不可用" />;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {errorView}
      <Card size="small" title={issue.title} extra={<Tag color={statusColor(issue.status)}>{statusLabel(issue.status)}</Tag>}>
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
          <Descriptions.Item label="问题 ID">{issue.id}</Descriptions.Item>
          <Descriptions.Item label="引擎 / 类型">{issue.engine} · {issue.issueType}</Descriptions.Item>
          <Descriptions.Item label="诊断分类">{issue.diagnosticType}</Descriptions.Item>
          <Descriptions.Item label="影响首次出现">{formatTimestamp(issue.firstSeenAt)}</Descriptions.Item>
          <Descriptions.Item label="最近出现">{formatTimestamp(issue.lastSeenAt)}</Descriptions.Item>
          <Descriptions.Item label="最近报告">{issue.lastReportId ? <Link to={monitoringHref(projectId, `/${issue.lastReportId}`)}>#{issue.lastReportId}</Link> : '-'}</Descriptions.Item>
          {issue.evaluationCaseId && <Descriptions.Item label="评估样本"><Link to={`/evaluation-cases?caseId=${issue.evaluationCaseId}`}>#{issue.evaluationCaseId}</Link></Descriptions.Item>}
          {issue.evaluationRunId && <Descriptions.Item label="回放记录"><Link to={`/evaluation-runs/${issue.evaluationRunId}`}>#{issue.evaluationRunId}</Link></Descriptions.Item>}
        </Descriptions>
      </Card>
      <Card size="small" title="处置记录">
        <Form layout="vertical" disabled={loading || saving} onFinish={saveIssue}>
          <Form.Item label="状态">
            <Select aria-label="状态" value={draft.status} options={ISSUE_STATUSES} onChange={status => setDraft(value => ({ ...value, status }))} />
          </Form.Item>
          <Form.Item label="负责人">
            <Input aria-label="负责人" maxLength={128} value={draft.assignee} onChange={event => setDraft(value => ({ ...value, assignee: event.target.value }))} />
          </Form.Item>
          <Form.Item label="裁决或修复说明">
            <Input.TextArea aria-label="裁决或修复说明" rows={3} maxLength={2048} value={draft.resolution} onChange={event => setDraft(value => ({ ...value, resolution: event.target.value }))} />
          </Form.Item>
          <Form.Item label="验收条件">
            <Input.TextArea aria-label="验收条件" rows={3} maxLength={2048} value={draft.acceptanceCriteria} onChange={event => setDraft(value => ({ ...value, acceptanceCriteria: event.target.value }))} />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} sm={12}><Form.Item label="评估样本 ID"><InputNumber aria-label="评估样本 ID" min={1} precision={0} style={{ width: '100%' }} value={draft.evaluationCaseId} onChange={evaluationCaseId => setDraft(value => ({ ...value, evaluationCaseId }))} /></Form.Item></Col>
            <Col xs={24} sm={12}><Form.Item label="回放记录 ID"><InputNumber aria-label="回放记录 ID" min={1} precision={0} style={{ width: '100%' }} value={draft.evaluationRunId} onChange={evaluationRunId => setDraft(value => ({ ...value, evaluationRunId }))} /></Form.Item></Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving} disabled={error?.status === 409}>保存处置</Button>
        </Form>
      </Card>
    </Space>
  );
}

function ReportHistory({ projectId }) {
  const navigate = useNavigate();
  const [range, setRange] = useState(makeDefaultRange);
  const [reports, setReports] = useState([]);
  const [pageNo, setPageNo] = useState(1);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const requestRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    makeRequest(projectId, '/reports', { params: { pageNo, pageSize: HISTORY_PAGE_SIZE }, signal: controller.signal })
      .then(data => { setReports(data.items || []); setTotal(data.total || 0); })
      .catch(error => { if (!controller.signal.aborted) setError(error); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, pageNo, refresh]);

  const generateReport = async () => {
    if (requestRef.current?.running) return;
    const startAt = `${range[0]}T00:00:00+08:00`;
    const endAt = `${range[1]}T00:00:00+08:00`;
    const duration = new Date(endAt) - new Date(startAt);
    if (!Number.isFinite(duration) || duration <= 0 || duration > 31 * 86400000) {
      setError(new Error('请选择大于 0 天且不超过 31 天的观察区间。结束日期当天不计入。'));
      return;
    }
    const scope = `${startAt}/${endAt}`;
    const idempotencyKey = requestRef.current?.scope === scope
      ? requestRef.current.key
      : `manual-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
    requestRef.current = { scope, key: idempotencyKey, running: true };
    setGenerating(true);
    setError(null);
    try {
      const report = await makeRequest(projectId, '/reports', {
        method: 'POST', body: { startAt, endAt, idempotencyKey }
      });
      requestRef.current = null;
      navigate(monitoringHref(projectId, `/${report.id}`));
    } catch (error) {
      setError(error);
    } finally {
      if (requestRef.current) requestRef.current.running = false;
      setGenerating(false);
    }
  };

  const columns = [
    { title: '报告', dataIndex: 'id', width: 90, render: id => <Link to={monitoringHref(projectId, `/${id}`)}>#{id}</Link> },
    { title: '观察区间', width: 260, render: (_, row) => `${formatTimestamp(row.startAt)} 至 ${formatTimestamp(row.endAt)}` },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag> },
    { title: '来源', dataIndex: 'source', width: 90, render: value => value === 'SCHEDULED' ? '定时' : '手动' },
    { title: '生成时间', dataIndex: 'createdAt', width: 170, render: formatTimestamp }
  ];

  return (
    <Space vertical size={16} style={{ width: '100%' }}>
      {error && <Alert showIcon type="error" title={requestError(error)} />}
      <Card size="small" title="生成监测报告">
        <Form layout="vertical" onFinish={generateReport}>
          <Row gutter={[12, 12]} align="bottom">
            <Col xs={24} md={8}><Form.Item label="观察开始（北京时间）" style={{ marginBottom: 0 }}><Input aria-label="观察开始" type="date" value={range[0]} onChange={event => setRange([event.target.value, range[1]])} /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item label="结束日期（当天不计入）" style={{ marginBottom: 0 }}><Input aria-label="结束日期" type="date" value={range[1]} onChange={event => setRange([range[0], event.target.value])} /></Form.Item></Col>
            <Col xs={24} md={8}><Button type="primary" htmlType="submit" loading={generating}>立即生成</Button></Col>
          </Row>
        </Form>
      </Card>
      <Card size="small" title="报告历史" extra={<Space wrap>
        <Link to={monitoringHref(projectId, '/compare')}>对比报告</Link>
        <Button icon={<ReloadOutlined />} onClick={() => setRefresh(value => value + 1)} loading={loading}>刷新</Button>
      </Space>}>
        <Table rowKey="id" size="small" columns={columns} dataSource={reports} loading={loading} pagination={false} scroll={{ x: 740 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无监测报告" /> }} />
        {total > HISTORY_PAGE_SIZE && <Pagination style={{ marginTop: 16, textAlign: 'right' }} current={pageNo} pageSize={HISTORY_PAGE_SIZE} total={total} onChange={setPageNo} showSizeChanger={false} />}
      </Card>
    </Space>
  );
}

function ReportRoute({ reportId, projectId }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    makeRequest(projectId, `/reports/${reportId}`, { signal: controller.signal })
      .then(setReport)
      .catch(error => { if (!controller.signal.aborted) setError(error); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, reportId, refresh]);

  const retryReport = async id => {
    setRetrying(true);
    setError(null);
    try {
      setReport(await makeRequest(projectId, `/reports/${id}/retry`, { method: 'POST' }));
    } catch (error) {
      setError(error);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <Space vertical size={16} style={{ width: '100%' }}>
      {error && <Alert showIcon type="error" title={requestError(error)} />}
      {report && <ReportDetail report={report} onRetry={retryReport} retrying={retrying} />}
      {loading ? <Spin /> : (error || report?.status === 'RUNNING') && (
        <Button icon={<ReloadOutlined />} onClick={() => setRefresh(value => value + 1)}>刷新报告</Button>
      )}
    </Space>
  );
}

function comparisonError(baseline, candidate) {
  if (!baseline?.snapshot || !candidate?.snapshot || baseline.status !== 'SUCCEEDED' || candidate.status !== 'SUCCEEDED') {
    return '请选择两份已生成的报告。';
  }
  if (baseline.projectId !== candidate.projectId || baseline.ruleVersion !== candidate.ruleVersion) {
    return '两份报告需要使用同一项目和规则版本。';
  }
  const baselineStart = Date.parse(baseline.startAt);
  const baselineEnd = Date.parse(baseline.endAt);
  const candidateStart = Date.parse(candidate.startAt);
  const candidateEnd = Date.parse(candidate.endAt);
  if (baselineEnd - baselineStart !== candidateEnd - candidateStart) return '请选择相同长度的观察窗口。';
  if (!(baselineEnd <= candidateStart)) return '候选窗口须在基线窗口结束后开始。';
  return null;
}

function knownRelease(report, engine) {
  if (report.snapshot.truncated) return null;
  const cohort = report.snapshot.releaseCohorts?.find(item => item.engine === engine);
  const release = cohort?.releases?.[0];
  if (
    cohort?.status !== 'KNOWN' || !cohort.eligibleCount || cohort.observedCount !== cohort.eligibleCount ||
    cohort.releases?.length !== 1 || release.count !== cohort.eligibleCount || !release.backendRelease ||
    (engine === 'AGENT' && !release.workerRelease)
  ) return null;
  return release;
}

function compareReleases(baseline, candidate, engine) {
  const before = knownRelease(baseline, engine);
  const after = knownRelease(candidate, engine);
  if (!before || !after) return null;
  if (
    before.backendRelease === after.backendRelease &&
    (engine !== 'AGENT' || before.workerRelease === after.workerRelease)
  ) return null;
  return { engine, before, after };
}

function comparisonRows(baseline, candidate) {
  const valueKey = metric => `${metric.engine}/${metric.group || ''}/${metric.key}/${metric.unit}`;
  const matched = new Map();
  for (const metric of baseline.snapshot.metrics) matched.set(valueKey(metric), { baseline: metric });
  for (const metric of candidate.snapshot.metrics) {
    const key = valueKey(metric);
    matched.set(key, { ...matched.get(key), candidate: metric });
  }
  return Array.from(matched, ([key, row]) => {
    const before = row.baseline;
    const after = row.candidate;
    const metric = before || after;
    let comparison;
    if (before?.value == null || after?.value == null || !before.observedCount || !after.observedCount) {
      comparison = '记录不足，待复核';
    } else if (
      !before.eligibleCount || !after.eligibleCount ||
      before.observedCount * after.eligibleCount !== after.observedCount * before.eligibleCount ||
      (metric.unit === 'COUNT' && before.observedCount !== after.observedCount)
    ) {
      comparison = '样本覆盖不一致，待复核';
    } else {
      const delta = after.value - before.value;
      comparison = metric.unit === 'RATIO'
        ? `${NUMBER_FORMAT.format(delta * 100)} 个百分点`
        : formatMetric(delta, metric.unit);
    }
    return { key, ...row, metric, comparison };
  });
}

function ReleaseLabel({ release }) {
  return <Space wrap>
    <Text code title={release.backendRelease}>Backend {release.backendRelease.slice(0, 12)}</Text>
    {release.workerRelease && <Text code title={release.workerRelease}>Worker {release.workerRelease.slice(0, 12)}</Text>}
  </Space>;
}

function ReportComparison({ projectId }) {
  const [params] = useSearchParams();
  const defaultBaseline = Number(params.get('baselineId')) || null;
  const [baselineId, setBaselineId] = useState(defaultBaseline);
  const [candidateId, setCandidateId] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const compare = async () => {
    if (!Number.isSafeInteger(baselineId) || !Number.isSafeInteger(candidateId) || baselineId < 1 || candidateId < 1 || baselineId === candidateId) {
      setError('请输入两份不同报告的 ID。');
      return;
    }
    setError(null);
    setComparison(null);
    setLoading(true);
    try {
      const [baseline, candidate] = await Promise.all([
        makeRequest(projectId, `/reports/${baselineId}`),
        makeRequest(projectId, `/reports/${candidateId}`)
      ]);
      const reason = comparisonError(baseline, candidate);
      if (reason) setError(reason);
      else {
        const rows = comparisonRows(baseline, candidate);
        const engines = [...new Set(rows.map(row => row.metric.engine))];
        const releases = engines.map(engine => compareReleases(baseline, candidate, engine)).filter(Boolean);
        setComparison({ baseline, candidate, rows, releases, usesTimeWindow: releases.length < engines.length || engines.length === 0 });
      }
    } catch (error) {
      setError(requestError(error));
    } finally {
      setLoading(false);
    }
  };

  const formatCell = metric => !metric ? '未知' : (
    <Space vertical size={0}>
      <Text>{formatMetric(metric.value, metric.unit)}</Text>
      <Text type="secondary">覆盖 {metric.observedCount}/{metric.eligibleCount}</Text>
    </Space>
  );

  return (
    <Space vertical size={16} style={{ width: '100%' }}>
      <Card size="small" title="报告对比">
        <Form layout="vertical" onFinish={compare} disabled={loading}>
          <Row gutter={[12, 12]} align="bottom">
            <Col xs={24} md={8}><Form.Item label="基线报告 ID" style={{ marginBottom: 0 }}><InputNumber aria-label="基线报告 ID" min={1} precision={0} style={{ width: '100%' }} value={baselineId} onChange={setBaselineId} /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item label="候选报告 ID" style={{ marginBottom: 0 }}><InputNumber aria-label="候选报告 ID" min={1} precision={0} style={{ width: '100%' }} value={candidateId} onChange={setCandidateId} /></Form.Item></Col>
            <Col xs={24} md={8}><Button htmlType="submit" type="primary" loading={loading}>比较报告</Button></Col>
          </Row>
        </Form>
      </Card>
      {error && <Alert type="warning" showIcon title={error} />}
      {comparison && (
        <Card size="small" title={comparison.releases.length ? '部署版本对比' : '时间窗口对比'}>
          <Space vertical size={12} style={{ width: '100%' }}>
            {comparison.usesTimeWindow && (
              <Alert type="info" showIcon title="无法核实为不同部署版本的指标按时间窗口展示。" />
            )}
            {(comparison.baseline.snapshot.truncated || comparison.candidate.snapshot.truncated) && (
              <Alert type="warning" showIcon title="至少一份报告已截断，请留意缺失指标。" />
            )}
            <Descriptions size="small" column={{ xs: 1, md: 2 }}>
              {[['基线窗口', comparison.baseline], ['候选窗口', comparison.candidate]].map(([label, report]) => (
                <Descriptions.Item key={label} label={label}><Space wrap>
                  <Link to={monitoringHref(projectId, `/${report.id}`)}>#{report.id}</Link>
                  <Text>{formatTimestamp(report.startAt)} 至 {formatTimestamp(report.endAt)}</Text>
                </Space></Descriptions.Item>
              ))}
            </Descriptions>
            {comparison.releases.map(({ engine, before, after }) => (
              <Descriptions key={engine} size="small" column={{ xs: 1, md: 2 }}>
                <Descriptions.Item label={`${engine} 基线版本`}><ReleaseLabel release={before} /></Descriptions.Item>
                <Descriptions.Item label={`${engine} 候选版本`}><ReleaseLabel release={after} /></Descriptions.Item>
              </Descriptions>
            ))}
            <Table
              size="small" rowKey="key" scroll={{ x: 760 }} pagination={false} dataSource={comparison.rows}
              columns={[
                { title: '指标', width: 245, render: (_, row) => <Space vertical size={0}><Text>{row.metric.label}</Text><Text type="secondary">{row.metric.engine} {GROUP_LABELS[row.metric.group] || ''}</Text></Space> },
                ...(comparison.releases.length && comparison.usesTimeWindow ? [{
                  title: '对比依据', width: 105,
                  render: (_, row) => comparison.releases.some(release => release.engine === row.metric.engine) ? '部署版本' : '时间窗口'
                }] : []),
                { title: '基线', width: 125, render: (_, row) => formatCell(row.baseline) },
                { title: '候选', width: 125, render: (_, row) => formatCell(row.candidate) },
                { title: '变化', dataIndex: 'comparison', width: 170 }
              ]}
            />
          </Space>
        </Card>
      )}
    </Space>
  );
}

export default function ReviewQualityMonitoringPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const detailMatch = useMatch(`${REVIEW_QUALITY_MONITOR_ROUTE}/:reportId`);
  const issueMatch = useMatch(`${REVIEW_QUALITY_MONITOR_ROUTE}/issues/:issueId`);
  const compareMatch = useMatch(`${REVIEW_QUALITY_MONITOR_ROUTE}/compare`);
  const reportId = compareMatch ? null : detailMatch?.params.reportId;
  const issueId = issueMatch?.params.issueId;
  const [projects, setProjects] = useState(null);
  const [projectError, setProjectError] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const requestedProjectId = Number(params.get('projectId'));
  const projectId = projects?.find(project => project.id === requestedProjectId)?.id
    ?? (params.has('projectId') ? null : projects?.[0]?.id);

  useEffect(() => {
    const controller = new AbortController();
    setProjectError(null);
    fetchApi('/api/projects?includeDisabled=true', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setProjects(data.items || []); })
      .catch(error => { if (!controller.signal.aborted) setProjectError(error); });
    return () => controller.abort();
  }, [refresh]);

  return (
    <div style={{ padding: '20px clamp(16px, 3vw, 32px)', minHeight: 'calc(100dvh - 56px)', background: '#f5f7f8' }}>
      <Space vertical size={16} style={{ width: '100%', maxWidth: 1440, margin: '0 auto' }}>
        <Card size="small">
          <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space align="start">
              {(reportId || issueId || compareMatch) && <Link aria-label="返回报告历史" to={monitoringHref(projectId)}><ArrowLeftOutlined /></Link>}
              <Title level={4} style={{ margin: 0 }}>审查质量监测</Title>
            </Space>
            <Space wrap>
              <Select
                aria-label="项目"
                placeholder="选择项目"
                value={projectId ?? undefined}
                loading={!projects && !projectError}
                options={projects?.map(project => ({ value: project.id, label: project.name || `#${project.id}` })) || []}
                showSearch
                optionFilterProp="label"
                onChange={id => navigate(monitoringHref(id))}
                style={{ minWidth: 180 }}
              />
            </Space>
          </Space>
        </Card>
        {projectError ? <Alert showIcon type="error" title={requestError(projectError)} action={<Button onClick={() => setRefresh(value => value + 1)}>重试</Button>} />
          : !projects ? <Spin />
            : !projectId ? <Empty description={projects.length ? '请选择项目' : '暂无项目'} />
              : compareMatch ? <ReportComparison key={projectId} projectId={projectId} />
                : issueId ? <IssueDetail key={`${projectId}/${issueId}`} issueId={issueId} projectId={projectId} />
                  : reportId ? <ReportRoute key={`${projectId}/${reportId}`} reportId={reportId} projectId={projectId} />
                    : <ReportHistory key={projectId} projectId={projectId} />}
      </Space>
    </div>
  );
}
