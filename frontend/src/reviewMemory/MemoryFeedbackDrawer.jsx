import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Descriptions, Drawer, Form, Input, Space, Tag, Typography } from 'antd';
import { fetchApi } from '../api.js';
import { getMemoryFeedback, getSource, getWriteback, mutateSource } from './api.js';
import { bytes, labelFor, STATE_LABELS } from './model.js';
import MemoryEntryFields from './MemoryEntryFields.jsx';
import {
  CASE_FIELDS, caseContent, caseDraft, caseValidation, feedbackError, FEEDBACK_STATUS_OPTIONS,
  isWritebackPending, MISSING_CONTEXT_TYPE_OPTIONS, REVIEW_FEEDBACK_REASON_OPTIONS, WRITEBACK_LABELS
} from './feedbackModel.js';
import './reviewMemory.css';

const { Text, Paragraph } = Typography;

export default function MemoryFeedbackDrawer({
  projectId, feedbackId, targetType, onClose, onDirtyChange, onBusyChange, onSaved
}) {
  const [detail, setDetail] = useState(null);
  const [source, setSource] = useState(null);
  const [legacyPolicies, setLegacyPolicies] = useState([]);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);
  const [validationAttempted, setValidationAttempted] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [needsCompare, setNeedsCompare] = useState(false);
  const [compared, setCompared] = useState(false);
  const [job, setJob] = useState(null);
  const [pollCycle, setPollCycle] = useState(0);
  const [pollStopped, setPollStopped] = useState(false);
  const [pollError, setPollError] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const draftRef = useRef(null);
  const hydratePendingCase = useRef(false);
  const submittedHere = useRef(false);
  const mounted = useRef(true);
  draftRef.current = draft;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { onBusyChange?.(busy ? 'save' : null); }, [busy, onBusyChange]);
  useEffect(() => () => { onDirtyChange?.(false); onBusyChange?.(null); }, [onDirtyChange, onBusyChange]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const data = await getMemoryFeedback(projectId, feedbackId, controller.signal);
        const [current, writeback, task, policies] = await Promise.all([
          data.memorySourceId ? getSource(projectId, data.memorySourceId, controller.signal) : null,
          data.writebackId ? getWriteback(projectId, data.writebackId, controller.signal) : null,
          !data.memorySourceId && !targetType ? fetchApi(`/api/review-tasks/${data.taskId}`, { signal: controller.signal }) : null,
          data.status === 'CONVERTED' ? fetchApi(`/api/projects/${projectId}/review-policies`, { signal: controller.signal }) : []
        ]);
        if (controller.signal.aborted) return;
        setDetail(data);
        setSource(current);
        setLegacyPolicies((Array.isArray(policies) ? policies : policies?.items || []).filter((item) => item.sourceFeedbackId === data.id));
        setJob(writeback);
        setConflict(false);
        if (hydratePendingCase.current && current && writeback?.state === 'SUCCEEDED') {
          setDraft(caseDraft(data, current, targetType || task?.targetType));
          hydratePendingCase.current = false;
        } else if (draftRef.current) { setNeedsCompare(true); setCompared(false); }
        else {
          setDraft(caseDraft(data, current, targetType || task?.targetType));
          hydratePendingCase.current = !current && isWritebackPending(writeback?.state);
        }
        setPollCycle((value) => value + 1);
      } catch (err) {
        if (!controller.signal.aborted) setError(feedbackError(err));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [projectId, feedbackId, targetType, refresh]);

  const jobId = job?.id;
  const pending = isWritebackPending(job?.state);
  useEffect(() => {
    if (!jobId || !pending) return undefined;
    const controller = new AbortController();
    const deadline = Date.now() + 30000;
    let timer;
    const stopTimer = window.setTimeout(() => {
      controller.abort();
      window.clearTimeout(timer);
      setPollStopped(true);
    }, 30000);
    setPollStopped(false);
    setPollError(null);
    const poll = async () => {
      try {
        const next = await getWriteback(projectId, jobId, controller.signal);
        if (controller.signal.aborted) return;
        setJob(next);
        if (!isWritebackPending(next.state)) {
          window.clearTimeout(stopTimer);
          if (next.state !== 'SUCCEEDED' && submittedHere.current) setDirty(true);
          onSaved?.();
          // Reload persisted digest/version and source while preserving the user's inputs.
          setRefresh((value) => value + 1);
          return;
        }
        if (Date.now() < deadline) timer = window.setTimeout(poll, 2000);
      } catch (err) {
        if (!controller.signal.aborted) {
          window.clearTimeout(stopTimer);
          setPollError(`状态查询失败；回写结果未知。${feedbackError(err)}`);
          setPollStopped(true);
        }
      }
    };
    timer = window.setTimeout(poll, 2000);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      window.clearTimeout(stopTimer);
    };
  }, [projectId, jobId, pending, pollCycle, onSaved]);

  const change = (value) => {
    hydratePendingCase.current = false;
    setDraft(value);
    setDirty(true);
    setError(null);
  };
  const submit = async () => {
    setValidationAttempted(true);
    const validation = caseValidation(draft);
    if (validation) { setError(validation); return; }
    setBusy(true);
    setError(null);
    try {
      const payload = Object.fromEntries(
        ['title', 'targetType', 'issueType', 'pathGlobs', 'keywords', ...CASE_FIELDS.map(([key]) => key)]
          .map((key) => [key, typeof draft[key] === 'string' ? draft[key].trim() : draft[key]])
      );
      const next = await mutateSource(projectId, `feedbacks/${feedbackId}/confirm`, 'POST', {
        ...payload,
        expectedFeedbackDigest: detail.feedbackDigest,
        expectedSourceVersion: detail.sourceVersion
      });
      if (!mounted.current) return;
      submittedHere.current = true;
      setJob(next);
      setDirty(['FAILED', 'CANCELLED_STALE_SOURCE'].includes(next.state));
      setPollCycle((value) => value + 1);
      onSaved?.();
      // Keep the submitted digest on unknown outcomes for an idempotent retry.
      // A known response can safely refresh current versions, including PENDING -> VALID.
      setRefresh((value) => value + 1);
    } catch (err) {
      if (!mounted.current) return;
      setError(feedbackError(err));
      if (err.status === 409) setConflict(true);
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const blocked = !detail?.findingAvailable || detail?.feedbackType !== 'FALSE_POSITIVE'
    || !['PENDING', 'VALID'].includes(detail?.status) || source?.state === 'DELETED';
  const snapshot = detail?.itemSnapshot || {};
  return (
    <Drawer
      open title="误报反馈与踩坑案例" size="min(860px, 100vw)" className="memory-source-drawer memory-feedback-drawer"
      styles={{ wrapper: { maxWidth: '100vw', minWidth: 0 } }}
      onClose={onClose} mask={{ closable: !busy }} keyboard={!busy}
      footer={
        <Space wrap>
          <Button disabled={busy} onClick={onClose}>关闭</Button>
          {(conflict || needsCompare || error) && <Button disabled={busy || loading} onClick={() => setRefresh((value) => value + 1)}>刷新版本并对照（保留输入）</Button>}
          {detail && !blocked && <Button type="primary" loading={busy} disabled={loading || !draft || conflict || (needsCompare && !compared) || pending}
            onClick={submit}>{source ? '确认并更新记忆' : '确认并加入记忆'}</Button>}
        </Space>
      }
    >
      {loading && <Paragraph role="status">正在加载反馈与案例…</Paragraph>}
      {detail && <section className="memory-feedback-risk">
        <Typography.Title level={4}>{snapshot.title || detail.riskTitle || '未命名风险'}</Typography.Title>
        <Space wrap><Tag>{snapshot.severity || '未记录等级'}</Tag><Tag>{snapshot.category || detail.riskType || '未分类'}</Tag></Space>
        <Paragraph type="secondary" className="memory-top-space">{snapshot.filePath || '未记录路径'}{snapshot.startLine ? `:${snapshot.startLine}` : ''}</Paragraph>
        {snapshot.body && <Paragraph ellipsis={{ rows: 2 }}>{snapshot.body}</Paragraph>}
        {(snapshot.body || snapshot.suggestion) && <details className="memory-usage-notes">
          <summary>查看原审查详情</summary>
          {snapshot.body && <pre className="memory-plain-text">{snapshot.body}</pre>}
          {snapshot.suggestion && <pre className="memory-plain-text">建议：{snapshot.suggestion}</pre>}
        </details>}
      </section>}
      {error && <Alert type="error" showIcon title={error} />}
      {conflict && <Alert type="warning" title="当前输入已保留。请刷新最新反馈和案例，核对差异后重新确认。" />}
      {job && (job.state === 'SUCCEEDED' || pending ? (
        <Space wrap role="status" className="memory-top-space">
          <Tag color={pending ? 'processing' : 'success'}>{WRITEBACK_LABELS[job.state]}</Tag>
          <Text type="secondary">{pending ? '关闭后可重新查看结果' : source ? `当前案例：${STATE_LABELS[source.state] || source.state}` : '正在读取案例状态'}</Text>
        </Space>
      ) : (
        <Alert showIcon type="warning" title={WRITEBACK_LABELS[job.state] || job.state}
          description={job.lastErrorCode ? feedbackError(job.lastErrorCode) : '请核对案例当前状态。'} />
      ))}
      {pollError && <Alert type="warning" title={pollError} />}
      {submittedHere.current && ['FAILED', 'CANCELLED_STALE_SOURCE'].includes(job?.state) && <Alert type="warning"
        title="本次案例未生效，输入仍保留在当前窗口。" description="请刷新对照并修正后重新确认；相同内容可能返回原失败记录。关闭后需重新整理尚未写入来源的内容。" />}
      {pending && pollStopped && <Alert type="info" title="本次状态查询已停止，回写仍由服务端处理。"
        action={<Button onClick={() => setPollCycle((value) => value + 1)}>重新查询状态</Button>} />}
      {detail && (
        <>
          {detail.status === 'CONVERTED' && <Paragraph type="secondary">
            <Text>此反馈已转为旧项目策略，不重复生成记忆案例。</Text>
            {legacyPolicies.length > 0 && <><br />{legacyPolicies.map((item) => `#${item.id} ${item.title}`).join('、')}</>}
          </Paragraph>}
          {blocked && detail.status !== 'CONVERTED' && <Alert type="warning" title="当前反馈不能确认案例"
            description={!detail.findingAvailable ? '原 finding 已不存在或发生变化。' : source?.state === 'DELETED' ? '来源已删除，不能重新确认恢复。' : '仅待分析或有效的误报反馈可确认；已撤回或信息不足的反馈不能直接发布。'} />}
          {!blocked && needsCompare && <Checkbox className="memory-top-space" checked={compared} disabled={loading || busy || pending}
            onChange={(event) => setCompared(event.target.checked)}>
            已核对下方最新反馈及案例，保留当前输入作为本次确认内容
          </Checkbox>}
          {draft && !blocked && <>
            <Form layout="vertical" disabled={busy || loading || pending} className="memory-top-space">
              <Form.Item label="误判原因" required
                validateStatus={validationAttempted && !draft.misjudgmentCause.trim() ? 'error' : undefined}
                help={validationAttempted && !draft.misjudgmentCause.trim() ? '请填写误判原因。' : undefined}>
                <Input.TextArea aria-label="误判原因" value={draft.misjudgmentCause} maxLength={4000}
                  autoSize={{ minRows: 4, maxRows: 10 }} placeholder="说明为什么这条风险是误判，可补充已有兜底、项目约定或相关证据。"
                  onChange={(event) => change({ ...draft, misjudgmentCause: event.target.value })} />
              </Form.Item>
            </Form>
            <details className="memory-usage-notes">
              <summary>高级设置与补充信息</summary>
              <Form layout="vertical" disabled={busy || loading || pending} className="memory-top-space">
                <Form.Item label="案例标题" validateStatus={validationAttempted && !draft.title.trim() ? 'error' : undefined}
                  help={validationAttempted && !draft.title.trim() ? '请填写案例标题。' : undefined}>
                  <Input aria-label="案例标题" maxLength={255} value={draft.title}
                    onChange={(event) => change({ ...draft, title: event.target.value })} />
                </Form.Item>
                {CASE_FIELDS.filter(([key]) => key !== 'misjudgmentCause').map(([key, label]) => <Form.Item label={label} key={key}>
                  <Input.TextArea aria-label={label} value={draft[key]} maxLength={4000} autoSize={{ minRows: 2, maxRows: 8 }}
                    onChange={(event) => change({ ...draft, [key]: event.target.value })} />
                </Form.Item>)}
              </Form>
              <MemoryEntryFields kind="PITFALL" content={false} value={draft} onChange={change}
                disabled={busy || loading || pending} />
            </details>
            <Paragraph type={bytes(caseContent(draft)) > 4000 ? 'danger' : 'secondary'}>
              案例 {bytes(caseContent(draft))} / 4000 UTF-8 字节
            </Paragraph>
          </>}
          {blocked && (draft?.misjudgmentCause || detail.reasonText) && <>
            <Text strong>误判原因</Text>
            <Paragraph className="memory-top-space">{draft?.misjudgmentCause || detail.reasonText}</Paragraph>
          </>}
          <details className="memory-usage-notes" open={needsCompare || undefined}>
            <summary>来源与版本</summary>
            <Descriptions column={1} size="small" className="memory-top-space" items={[
              { key: 'feedback', label: '原反馈', children: `#${detail.id} · ${labelFor(FEEDBACK_STATUS_OPTIONS, detail.status)} · ${labelFor(REVIEW_FEEDBACK_REASON_OPTIONS, detail.reasonType) || '未填原因'}` },
              { key: 'source', label: '案例来源', children: source ? `#${source.id} · v${source.version} · ${STATE_LABELS[source.state] || source.state}` : '尚未生成案例' },
              { key: 'task', label: '关联任务', children: <a href={`/tasks/${detail.taskId}`} target="_blank" rel="noreferrer">查看任务 #{detail.taskId}</a> }
            ]} />
            {detail.reasonText && <><Text strong>原人工说明 / 参考证据</Text><pre className="memory-plain-text">{detail.reasonText}</pre></>}
            {!!detail.missingContextTypes?.length && <Paragraph>缺失背景：{detail.missingContextTypes.map((value) => labelFor(MISSING_CONTEXT_TYPE_OPTIONS, value)).join('、')}</Paragraph>}
            {source?.entries?.map((entry) => <div key={entry.id}>
              <Text strong>当前案例正文 · v{source.version}</Text>
              <pre className="memory-plain-text">{entry.content}</pre>
            </div>)}
            <Paragraph type="secondary">反馈独立保存，关闭不会撤销。案例仅供后续查证；使用时仍需本次代码证据，并受项目开关、范围和预算约束。</Paragraph>
          </details>
        </>
      )}
    </Drawer>
  );
}
