import { useEffect, useState } from 'react';
import { Alert, Button, Collapse, Drawer, Space, Spin, Tag, Typography } from 'antd';
import { Link, useLocation } from 'react-router-dom';
import { fetchApi } from './api.js';
import './autoFixProgress.css';

const { Text } = Typography;
const ACTIVE_STATUSES = new Set(['QUEUED', 'RUNNING']);
const STATUS_TEXT = {
  QUEUED: '已排队',
  RUNNING: '执行中',
  AWAITING_APPROVAL: '修复已完成，等待合并',
  MERGED: '已合并',
  STOPPED: '已停止',
  CANCELLED: '已取消',
  STALE: '分支已更新',
  MR_CLOSED: '修复 MR 已关闭'
};
const STEPS = {
  PREPARING: '准备修复',
  GENERATING_PATCH: '生成补丁',
  PUSHING: '写入修复分支',
  REVIEW_QUEUED: '复审排队中',
  REVIEWING: '复审中',
  CREATING_MR: '创建修复 MR'
};
const FINDING_STATUSES = {
  PERSISTS: ['仍存在', 'orange'],
  NOT_REOBSERVED: ['复审未再发现', 'green'],
  NEW: ['本轮新发现', 'blue'],
  UNCERTAIN: ['待核对', 'gold'],
  UNDETERMINED: ['无法判定', 'default']
};
const NOTIFICATION_STATUSES = {
  PENDING: '待发送',
  QUEUED: '待发送',
  SENDING: '发送中',
  SENT: '已发送',
  SUCCESS: '已发送',
  SKIPPED: '已跳过',
  FAILED: '投递失败',
  UNKNOWN: '投递结果未知'
};
const SEVERITY_TEXT = {
  CRITICAL: '紧急',
  HIGH: '高风险',
  MAJOR: '高风险',
  MEDIUM: '中风险',
  MINOR: '中风险',
  LOW: '低风险'
};

function externalUrl(value) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function shortSha(value) {
  return typeof value === 'string' ? value.slice(0, 8) : '';
}

function reviewPath(round, index) {
  if (!Number.isSafeInteger(round?.reviewTaskId) || round.reviewTaskId < 1) return undefined;
  const query = round.reviewKey ? `?reviewKey=${encodeURIComponent(round.reviewKey)}` : '';
  const hash = Number.isInteger(index) && index >= 0 ? `#finding-${index}` : '';
  return `/tasks/${round.reviewTaskId}${query}${hash}`;
}

function ReviewLink({ round, index, children }) {
  const to = reviewPath(round, index);
  const location = useLocation();
  return to ? (
    <Link to={to} state={{ from: `${location.pathname}${location.search}` }}>{children}</Link>
  ) : null;
}

function GitLabLink({ url, children }) {
  const href = externalUrl(url);
  return href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : null;
}

function CandidateFindings({ candidates, round }) {
  if (!Array.isArray(candidates) || candidates.length === 0) return null;
  return (
    <ul className="auto-fix-candidates">
      {candidates.map(finding => (
        <li key={finding.index}>
          {reviewPath(round, finding.index) ? (
            <ReviewLink round={round} index={finding.index}>{finding.title || finding.filePath}</ReviewLink>
          ) : finding.title || finding.filePath}
        </li>
      ))}
    </ul>
  );
}

function FindingSide({ label, finding, round }) {
  if (!finding) return null;
  const lines = finding.startLine
    ? `:${finding.startLine}${finding.endLine && finding.endLine !== finding.startLine ? `–${finding.endLine}` : ''}`
    : '';
  return (
    <div className="auto-fix-finding-side">
      <Space size={4} wrap>
        <Text type="secondary">{label}</Text>
        {finding.severity && (
          <Tag color={finding.severity === 'CRITICAL' ? 'red' : undefined}>
            {SEVERITY_TEXT[finding.severity] || finding.severity}
          </Tag>
        )}
      </Space>
      {finding.title && <Text strong>{finding.title}</Text>}
      {finding.filePath && <Text type="secondary">{finding.filePath}{lines}</Text>}
      {finding.body && <Text>{finding.body}</Text>}
      <ReviewLink round={Number.isInteger(finding.index) ? round : null} index={finding.index}>
        定位 Finding
      </ReviewLink>
    </div>
  );
}

function RoundFindings({ path, round, previousRound, runStatus }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    fetchApi(`${path}/rounds/${round.number}/findings`, { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setResult(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [path, round.number, round.criticalCount, round.commitSha, round.reviewStatus, round.step, runStatus, reload]);

  if (error) {
    return <Alert type="warning" showIcon title="暂时无法读取本轮风险处理详情" action={(
      <Button size="small" onClick={() => setReload(value => value + 1)}>重试</Button>
    )} />;
  }
  if (!result) return <Spin size="small" aria-label="正在加载风险处理详情" />;
  if (result.status === 'PENDING') return <Text type="secondary">待复审</Text>;
  if (result.status === 'UNAVAILABLE') {
    return <Text type="secondary">无法判定。{result.reason || '本轮没有可用的完整复审。'}</Text>;
  }
  if (result.status !== 'COMPLETE') return <Text type="secondary">暂无本轮风险对照</Text>;

  const items = Array.isArray(result.items) ? result.items : [];
  const urgent = item => [item.before?.severity, item.after?.severity].includes('CRITICAL');
  const needsAttention = item => item.after?.severity === 'CRITICAL' || item.status === 'UNCERTAIN';
  const urgentItems = items.filter(urgent).sort((left, right) => Number(needsAttention(right)) - Number(needsAttention(left)));
  const otherItems = items.filter(item => !urgent(item));
  const renderItems = findings => findings.map((item, index) => {
    const [label, color] = FINDING_STATUSES[item.status] || FINDING_STATUSES.UNCERTAIN;
    const downgraded = item.status === 'PERSISTS'
      && item.before?.severity === 'CRITICAL'
      && item.after?.severity !== 'CRITICAL';
    return (
      <div className="auto-fix-finding-comparison" key={`${item.before?.index ?? ''}:${item.after?.index ?? ''}:${index}`}>
        <div><Tag color={color}>{label}{downgraded ? ' · 已降级' : ''}</Tag></div>
        <div className="auto-fix-finding-sides">
          <FindingSide label={previousRound ? '上一轮 Finding' : '原风险'} finding={item.before} round={previousRound} />
          <FindingSide label="本轮 Finding" finding={item.after} round={round} />
        </div>
        {item.reason && <Text type="secondary">{item.reason}</Text>}
        {(item.beforeCandidates?.length > 0 || item.afterCandidates?.length > 0) && (
          <div>
            <Text type="secondary">可能对应的 Finding</Text>
            <CandidateFindings candidates={item.beforeCandidates} round={previousRound} />
            <CandidateFindings candidates={item.afterCandidates} round={round} />
          </div>
        )}
      </div>
    );
  });

  return (
    <div className="auto-fix-findings">
      {result.diffUrl && !round.diffUrl && <GitLabLink url={result.diffUrl}>本轮差异</GitLabLink>}
      {urgentItems.length > 0 ? renderItems(urgentItems) : <Text type="secondary">本轮无紧急风险对照项</Text>}
      {otherItems.length > 0 && (
        <details>
          <summary>查看其它等级风险（{otherItems.length}）</summary>
          {renderItems(otherItems)}
        </details>
      )}
    </div>
  );
}

export default function AutoFixProgress({ taskId, reviewKey }) {
  const [summary, setSummary] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(false);
  const [openedRunId, setOpenedRunId] = useState(null);
  const [expandedRounds, setExpandedRounds] = useState(null);
  const [canceling, setCanceling] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const root = `/api/review-tasks/${taskId}/auto-fix`;
  const runId = summary?.runId;
  const runPath = runId ? `${root}/${runId}` : null;
  const drawerOpen = Boolean(runId && openedRunId === runId);

  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const load = async () => {
      try {
        const response = await fetchApi(`${root}?reviewKey=${encodeURIComponent(reviewKey)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setSummary(response || null);
        if (ACTIVE_STATUSES.has(response?.status)) {
          timer = window.setTimeout(load, 5000);
        } else if (response?.status === 'AWAITING_APPROVAL' || (response?.status === 'STALE' && response?.mergeRequest)) {
          timer = window.setTimeout(load, 15000);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if ([401, 403, 404].includes(err.status)) {
          setSummary(null);
          return;
        }
        timer = window.setTimeout(load, 10000);
      }
    };
    load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [root, reviewKey, refresh]);

  useEffect(() => {
    if (!drawerOpen || !runPath) return undefined;
    const controller = new AbortController();
    fetchApi(runPath, { signal: controller.signal })
      .then(response => {
        if (controller.signal.aborted) return;
        setDetail(response);
        setDetailError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setDetailError(true);
      });
    return () => controller.abort();
  }, [drawerOpen, runPath, summary]);

  if (!summary?.status) return null;
  if (!runId) {
    return summary.reason ? <Alert type="info" showIcon title="自动修复未启动" description={summary.reason} /> : null;
  }
  if (!STATUS_TEXT[summary.status]) return null;

  const run = detail?.runId === runId ? detail : summary;
  const status = summary.status;
  const rounds = Array.isArray(run.rounds) ? run.rounds : [];
  const lastRound = rounds.findLast(round => Number.isInteger(round.criticalCount));
  const currentRound = summary.currentRound ?? run.currentRound;
  const maxRounds = summary.maxRounds ?? run.maxRounds;
  const lastCount = summary.remainingCriticalCount ?? lastRound?.criticalCount ?? summary.criticalCount;
  const hitLimit = summary.reasonCode === 'ROUND_LIMIT_REACHED';
  const pendingCancel = ACTIVE_STATUSES.has(status) && Boolean(summary.cancelRequestedAt || run.cancelRequestedAt);
  const description = hitLimit && Number.isInteger(lastCount)
    ? `已完成 ${currentRound || maxRounds || 3} 轮，仍有 ${lastCount} 项紧急风险`
    : summary.reason || run.reason;
  const latestSha = run.currentSha || rounds.at(-1)?.commitSha;
  const startSha = run.developerSha || run.startSha || run.sourceSha;
  const mergeUrl = run.mergeRequest?.webUrl;
  const canCancel = (summary.canCancel ?? run.canCancel) === true && ACTIVE_STATUSES.has(status);
  const alertType = status === 'MERGED' || status === 'AWAITING_APPROVAL'
    ? 'success'
    : ['STOPPED', 'STALE', 'CANCELLED', 'MR_CLOSED'].includes(status) ? 'warning' : 'info';
  const notification = typeof run.notificationStatus === 'string'
    ? { status: run.notificationStatus, reason: run.notificationReason }
    : run.notificationStatus;
  const stepText = pendingCancel ? '正在取消' : STEPS[summary.step ?? run.step];
  const activeRoundKeys = expandedRounds ?? (currentRound && rounds.some(round => round.number === currentRound)
    ? [String(currentRound)]
    : []);
  const label = status === 'RUNNING'
    ? [currentRound ? `第 ${currentRound} / ${maxRounds || 3} 轮` : null, stepText || STATUS_TEXT[status]].filter(Boolean).join(' · ')
    : pendingCancel ? '正在取消' : STATUS_TEXT[status];

  const cancel = async () => {
    setCancelError('');
    setCanceling(true);
    try {
      await fetchApi(`${runPath}/cancel`, { method: 'POST' });
      setRefresh(value => value + 1);
    } catch {
      setCancelError('暂时无法取消修复，请刷新后重试。');
    } finally {
      setCanceling(false);
    }
  };

  return (
    <>
      <Alert
        className="auto-fix-status"
        type={alertType}
        showIcon
        title={`自动修复 · ${label}`}
        description={description || summary.fixBranch}
        action={(
          <Button size="small" onClick={() => {
            setExpandedRounds(null);
            setCancelError('');
            setOpenedRunId(runId);
          }}>查看修复进度</Button>
        )}
      />
      <Drawer
        title="自动修复"
        open={drawerOpen}
        onClose={() => setOpenedRunId(null)}
        size="min(560px, 100vw)"
        footer={drawerOpen && (
          <Space wrap>
            {canCancel && (
              <Button danger loading={canceling || pendingCancel} onClick={cancel}>
                {pendingCancel ? '正在取消' : '取消修复'}
              </Button>
            )}
            {status === 'AWAITING_APPROVAL' && externalUrl(mergeUrl) && (
              <Button type="primary" href={externalUrl(mergeUrl)} target="_blank" rel="noopener noreferrer">
                前往 GitLab 确认
              </Button>
            )}
            {status !== 'AWAITING_APPROVAL' && <GitLabLink url={mergeUrl}>查看修复 MR</GitLabLink>}
          </Space>
        )}
      >
        {drawerOpen && (
          <div className="auto-fix-drawer-content">
            <Alert type={alertType} showIcon title={label} description={description} />
            {detailError && <Alert type="warning" showIcon title="暂时无法刷新修复详情" action={(
              <Button size="small" onClick={() => setRefresh(value => value + 1)}>重试</Button>
            )} />}
            {cancelError && <Alert type="error" showIcon title={cancelError} />}
            <div className="auto-fix-run-facts">
              {run.fixBranch && run.developerBranch && (
                <Text><Text code>{run.fixBranch}</Text> → <Text code>{run.developerBranch}</Text></Text>
              )}
              {startSha && <Text type="secondary">起始提交 <Text code>{shortSha(startSha)}</Text></Text>}
              {latestSha && <Text type="secondary">修复提交 <Text code>{shortSha(latestSha)}</Text></Text>}
              {run.mergeCommitSha && <Text type="secondary">合并提交 <Text code>{shortSha(run.mergeCommitSha)}</Text></Text>}
              {run.mergedAt && <Text type="secondary">合并时间 {run.mergedAt.replace('T', ' ')}</Text>}
              {status === 'AWAITING_APPROVAL' && Number.isInteger(run.originalCriticalCount) && (
                <Text type="secondary">原 Review · 紧急 {run.originalCriticalCount}</Text>
              )}
              {Number.isInteger(lastRound?.criticalCount) && (
                <Text type="secondary">最近有效复审 · 第 {lastRound.number} 轮 · 紧急 {lastRound.criticalCount}</Text>
              )}
              {notification?.status && (
                <Text type="secondary">钉钉通知 · {NOTIFICATION_STATUSES[notification.status] || notification.status}
                  {notification.reason ? ` · ${notification.reason}` : ''}
                </Text>
              )}
              <GitLabLink url={run.cumulativeDiffUrl}>累计修复差异</GitLabLink>
              {status === 'STALE' && <GitLabLink url={run.sourceMergeRequest?.webUrl}>打开原 MR</GitLabLink>}
              {status === 'AWAITING_APPROVAL' && <ReviewLink round={lastRound}>查看最终复审</ReviewLink>}
            </div>
            {rounds.length > 0 ? (
              <Collapse
                activeKey={activeRoundKeys}
                onChange={keys => setExpandedRounds(Array.isArray(keys) ? keys : [keys])}
                destroyOnHidden
                items={rounds.map((round, index) => {
                  const previousRound = index > 0 ? rounds[index - 1] : null;
                  const previousCount = previousRound?.criticalCount ?? run.originalCriticalCount;
                  const roundSummary = Number.isInteger(round.criticalCount)
                    ? `紧急 ${Number.isInteger(previousCount) ? `${previousCount} → ` : ''}${round.criticalCount}`
                    : round.number === currentRound && ACTIVE_STATUSES.has(status)
                      ? stepText || '待复审'
                      : '无有效复审';
                  return {
                    key: String(round.number),
                    label: <Space wrap size={6}><strong>第 {round.number} 轮</strong><Text type="secondary">{roundSummary}</Text></Space>,
                    children: (
                      <div className="auto-fix-findings">
                        {round.commitSha && <Text type="secondary">本轮提交 <Text code>{shortSha(round.commitSha)}</Text></Text>}
                        <Space wrap>
                          <GitLabLink url={round.diffUrl}>本轮差异</GitLabLink>
                          <ReviewLink round={round}>查看复审</ReviewLink>
                        </Space>
                        <Text strong>风险处理详情</Text>
                        <RoundFindings path={runPath} round={round} previousRound={previousRound} runStatus={status} />
                      </div>
                    )
                  };
                })}
              />
            ) : !detailError && <Text type="secondary">{detail ? '暂无已执行轮次' : '正在读取修复详情…'}</Text>}
          </div>
        )}
      </Drawer>
    </>
  );
}
