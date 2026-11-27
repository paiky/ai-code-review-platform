import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Card, Col, Descriptions, Empty, Input, Modal, Row, Select, Space, Spin, Tag, Timeline, Typography, message } from 'antd';
import { fetchApi } from '../api.js';

const { Text } = Typography;
const API = '/api/review-quality/monitoring/governance';
const STATUSES = {
  QUEUED: '待执行', RUNNING: '验证中', PAUSED: '已暂停', CANCELLED: '已取消',
  SUCCEEDED: '已完成', FAILED: '运行失败', OBSERVE: '持续观察', NEEDS_INPUT: '需要介入',
  OVERRIDDEN: '人工覆盖', VERIFIED: '已验证', DISMISSED: '已排除', REPLAY: '待回放'
};
const EVENTS = {
  ENQUEUED: '进入治理队列', CLAIMED: 'Worker 已领取', RECLAIMED: '租约到期后接管',
  DECIDED: 'Agent 已完成判断', REPLAY_STARTED: '开始隔离回放', REPLAY_FINISHED: '隔离回放完成',
  ASSESSED: 'Agent 已复核回放', RETRY_QUEUED: '等待重试', FAILED: '运行失败',
  SUCCEEDED: '运行完成', PAUSE: '人工暂停', RESUME: '人工恢复', CANCEL: '人工取消',
  OVERRIDE: '人工覆盖结论', PRIORITIZE: '人工调整优先级', MODEL_REQUESTED: '请求治理模型',
  NO_ISSUES: '报告无异常', AUTO_CLOSED: '验证通过后自动关闭'
};
const PRIORITIES = [
  { value: 'HIGH', label: '高优先级' }, { value: 'MEDIUM', label: '中优先级' }, { value: 'LOW', label: '低优先级' }
];

export function governanceRequest(projectId, path = '', { method, body, pageNo, signal } = {}) {
  const query = new URLSearchParams({ projectId, ...(pageNo ? { pageNo } : {}) });
  return fetchApi(`${API}${path}?${query}`, { method, body: body ? JSON.stringify(body) : undefined, signal });
}

export function StartGovernanceButton({ projectId, reportId, issueId, href }) {
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const start = async () => {
    setBusy(true);
    try {
      const runs = await governanceRequest(projectId, '/runs', { method: 'POST', body: { reportId, issueId } });
      setSubmitted(runs.length > 0);
      message.success(runs.length ? '治理运行已提交或复用' : '没有可提交的治理问题');
    } catch (error) {
      message.error(error.message || '提交治理失败');
    } finally {
      setBusy(false);
    }
  };

  return <Space wrap>
    <Button loading={busy} onClick={start}>启动治理</Button>
    {submitted && <Link to={href}>查看质量治理</Link>}
  </Space>;
}

function GovernanceActions({ projectId, issue, onChange }) {
  const [busy, setBusy] = useState(false);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [conclusion, setConclusion] = useState('');
  const active = ['QUEUED', 'RUNNING', 'PAUSED'].includes(issue.run.status);

  const intervene = async (action, fields = {}) => {
    setBusy(true);
    try {
      await governanceRequest(projectId, `/issues/${issue.id}`, {
        method: 'PATCH', body: { action, revision: issue.revision, ...fields }
      });
      setOverrideOpen(false);
      message.success('治理状态已更新');
    } catch (failure) {
      message.error(failure.status === 409 ? '治理状态已更新，请刷新后重试。' : failure.message || '操作失败');
    } finally {
      setBusy(false);
      onChange();
    }
  };

  return <Space wrap>
    <Select aria-label="治理优先级" size="small" options={PRIORITIES} value={issue.priority}
      disabled={busy} onChange={priority => intervene('PRIORITIZE', { priority })} />
    <Button size="small" disabled={busy} onClick={() => intervene(issue.paused ? 'RESUME' : 'PAUSE')}>
      {issue.paused ? '恢复' : '暂停'}
    </Button>
    {active && <Button size="small" disabled={busy} onClick={() => intervene('CANCEL')}>取消待执行动作</Button>}
    <Button size="small" disabled={busy} onClick={() => { setOverrideOpen(true); setConclusion(issue.override || ''); }}>覆盖结论</Button>
    <Modal title="覆盖治理结论" open={overrideOpen} onCancel={() => setOverrideOpen(false)}
      okText="保存" cancelText="取消" okButtonProps={{ disabled: !conclusion.trim() }}
      confirmLoading={busy} onOk={() => intervene('OVERRIDE', { conclusion: conclusion.trim() })}>
      <Input.TextArea aria-label="人工结论" maxLength={1000} rows={4} value={conclusion} onChange={event => setConclusion(event.target.value)} />
    </Modal>
  </Space>;
}

export function GovernanceHome({ projectId, initial, href, formatTimestamp }) {
  const [data, setData] = useState(initial);
  const [pageNo, setPageNo] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => governanceRequest(projectId, '', { pageNo, signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) { setData(result); setError(null); } })
      .catch(failure => { if (!controller.signal.aborted) setError(failure); });
    load();
    const timer = setInterval(load, 8000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [projectId, pageNo, refresh]);

  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    {error && <Alert showIcon type="error" message={error.message || '读取治理结果失败'} />}
    <Card size="small" title="最近治理运行" extra={<Button size="small" onClick={() => setRefresh(value => value + 1)}>刷新</Button>}>
      {data.latestRun ? <Space wrap>
        <Tag color={data.latestRun.status === 'FAILED' ? 'error' : 'processing'}>{STATUSES[data.latestRun.status]}</Tag>
        <Link to={href(`/governance/${data.latestRun.id}`)}>运行 #{data.latestRun.id}</Link>
        <Text type="secondary">{formatTimestamp(data.latestRun.updatedAt)}</Text>
        {data.latestRun.errorCode && <Text type="danger">{data.latestRun.errorCode}</Text>}
      </Space> : <Text type="secondary">等待首次治理运行。可从监测报告启动。</Text>}
    </Card>
    {data.latestRun && data.issues.length === 0 && data.latestRun.status === 'SUCCEEDED' && (
      <Empty description="暂无需要治理的问题" />
    )}
    <Row gutter={[16, 16]}>
      {data.issues.map(issue => {
        const { run } = issue;
        const judgment = issue.effectiveRun || run;
        const rationale = issue.override || judgment.assessment?.conclusion || judgment.decision?.rationale;
        return <Col key={issue.id} xs={24} lg={12} style={{ minWidth: 0 }}>
          <Card size="small" title={<span style={{ whiteSpace: 'normal' }}>{issue.title}</span>} style={{ height: '100%' }}>
            <Space direction="vertical" style={{ width: '100%', overflowWrap: 'anywhere' }}>
              <Space wrap>
                <Tag color={issue.status === 'NEEDS_INPUT' || issue.status === 'FAILED' ? 'warning' : 'blue'}>
                  {STATUSES[issue.status] || issue.status}
                </Tag>
                <Text>影响 {issue.affectedTaskCount} 个任务</Text>
                <Link to={href(`/governance/${run.id}`)}>判断与执行记录</Link>
                {issue.effectiveRun && <Link to={href(`/governance/${judgment.id}`)}>上次有效判断</Link>}
              </Space>
              {rationale && <Text>{rationale}</Text>}
              {judgment.replay && <Text>隔离回放{judgment.replay.passed ? '通过' : '未通过'}</Text>}
              {!issue.override && (judgment.assessment?.nextStep || judgment.decision?.missingEvidence) && (
                <Text type="secondary">{judgment.assessment?.nextStep || judgment.decision.missingEvidence}</Text>
              )}
              <GovernanceActions projectId={projectId} issue={issue} onChange={() => setRefresh(value => value + 1)} />
            </Space>
          </Card>
        </Col>;
      })}
    </Row>
    {(pageNo > 1 || data.hasMore) && <Space>
      <Button disabled={pageNo <= 1} onClick={() => setPageNo(value => value - 1)}>上一页</Button>
      <Text>第 {pageNo} 页</Text>
      <Button disabled={!data.hasMore} onClick={() => setPageNo(value => value + 1)}>下一页</Button>
    </Space>}
  </Space>;
}

export function GovernanceDetail({ projectId, runId, href, taskHref, formatTimestamp }) {
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => governanceRequest(projectId, `/runs/${runId}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) { setRun(result); setError(null); } })
      .catch(failure => { if (!controller.signal.aborted) setError(failure); });
    load();
    const timer = setInterval(load, 8000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [projectId, runId, refresh]);

  if (error) return <Alert showIcon type="error" message={error.message || '读取治理运行失败'} />;
  if (!run) return <Spin />;
  const refs = [...new Set([...(run.decision?.evidenceRefs || []), ...(run.assessment?.evidenceRefs || [])])];
  const metrics = refs.filter(ref => ref.startsWith('METRIC:')).map(ref => run.evidence.metrics[Number(ref.slice(7))]).filter(Boolean);
  const issue = { id: run.issueId, revision: run.controlRevision, paused: run.paused, priority: run.priority,
    override: run.override, run };

  return <Row gutter={[16, 16]}>
    <Col xs={24} lg={13} style={{ minWidth: 0 }}>
      <Card size="small" title={`治理运行 #${run.id}`} style={{ overflowWrap: 'anywhere' }}>
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="状态">{STATUSES[run.status]} {run.errorCode}</Descriptions.Item>
          <Descriptions.Item label="来源报告"><Link to={href(`/${run.reportId}`)}>报告 #{run.reportId}</Link></Descriptions.Item>
          {run.issueId && <Descriptions.Item label="监测问题"><Link to={href(`/issues/${run.issueId}`)}>问题 #{run.issueId}</Link></Descriptions.Item>}
          {run.decision && <Descriptions.Item label="Agent 判断">{run.decision.rationale}</Descriptions.Item>}
          {run.decision?.hypothesis && <Descriptions.Item label="验证假设">{run.decision.hypothesis}</Descriptions.Item>}
          {run.assessment && <Descriptions.Item label="验证结果">{run.assessment.conclusion}</Descriptions.Item>}
          {run.override && <Descriptions.Item label="人工覆盖">{run.override}</Descriptions.Item>}
          {(run.assessment?.nextStep || run.decision?.missingEvidence) && (
            <Descriptions.Item label="下一步">{run.assessment?.nextStep || run.decision.missingEvidence}</Descriptions.Item>
          )}
        </Descriptions>
        <Space wrap>
          {run.evidence.issue?.samples?.map(sample => <Link key={`${sample.taskId}/${sample.runId}/${sample.eventId}`}
            to={taskHref(sample)}>任务 #{sample.taskId}</Link>)}
        </Space>
        {metrics.map(metric => <div key={`${metric.key}/${metric.group}`}>
          <Text>{metric.label || metric.key}　{metric.value ?? '未知'}（可观测 {metric.observedCount}/{metric.eligibleCount}）</Text>
        </div>)}
        {run.replay && <Descriptions title="回放指标" size="small" column={1} style={{ marginTop: 12 }}>
          <Descriptions.Item label="结果"><Tag color={run.replay.passed ? 'success' : 'warning'}>{run.replay.passed ? '通过' : '未通过'}</Tag></Descriptions.Item>
          {run.replay.kind === 'STANDARD_CONTEXT' ? <>
            <Descriptions.Item label="预期证据保留">{run.replay.retainedExpectedEvidenceCount}/{run.replay.expectedEvidenceCount}</Descriptions.Item>
            <Descriptions.Item label="上下文字符数 / 目标">{run.replay.contextPromptChars}/{run.replay.targetContextChars}</Descriptions.Item>
            <Descriptions.Item label="查询与引用">查询 {run.replay.queryCount} 次，引用 {run.replay.includedSnippetCount} 段</Descriptions.Item>
          </> : <>
            <Descriptions.Item label="可读 Patch">{run.replay.readablePatchCount}</Descriptions.Item>
            <Descriptions.Item label="通过的分页验证">{run.replay.probes.filter(probe => probe.passed).length}/{run.replay.probes.length}</Descriptions.Item>
          </>}
        </Descriptions>}
        {run.replay?.evaluationRunId && <Link to={`/evaluation-runs/${run.replay.evaluationRunId}`}>
          评估回放 #{run.replay.evaluationRunId}
        </Link>}
        {run.issueId && <div style={{ marginTop: 12 }}>
          <GovernanceActions projectId={projectId} issue={issue} onChange={() => setRefresh(value => value + 1)} />
        </div>}
      </Card>
    </Col>
    <Col xs={24} lg={11} style={{ minWidth: 0 }}>
      <Card size="small" title="执行记录" style={{ overflowWrap: 'anywhere' }}>
        <Timeline items={run.events.map(event => ({ children: <>
          <Text>{EVENTS[event.kind] || event.kind}</Text><br />
          <Text type="secondary">{formatTimestamp(event.createdAt)}</Text>
          {(event.details.conclusion || event.details.errorCode) && <div>{event.details.conclusion || event.details.errorCode}</div>}
        </> }))} />
      </Card>
    </Col>
  </Row>;
}
