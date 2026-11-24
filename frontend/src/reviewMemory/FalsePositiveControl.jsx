import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Alert, Button, Checkbox, Form, Input, message, Modal, Select, Tag, Typography } from 'antd';
import { fetchApi } from '../api.js';
import { registerSettingsNavigationGuard } from '../settingsNavigation.js';
import { saveFindingFeedback, withdrawFeedback } from './api.js';
import { FEEDBACK_STATUS_OPTIONS, MISSING_CONTEXT_TYPE_OPTIONS, REVIEW_FEEDBACK_REASON_OPTIONS, feedbackError } from './feedbackModel.js';
import { labelFor } from './model.js';
import MemoryFeedbackDrawer from './MemoryFeedbackDrawer.jsx';

export default function FalsePositiveControl({ projectId, taskId, review, finding, findingIndex, onRefresh }) {
  const location = useLocation();
  const [messageApi, contextHolder] = message.useMessage();
  const [feedback, setFeedback] = useState(finding.feedback || null);
  const [modalOpen, setModalOpen] = useState(false);
  const [caseId, setCaseId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState({ reasonType: 'OTHER', reasonText: '', missingContextTypes: [], organize: false });
  const dirty = useRef(false);
  const busy = useRef(null);
  const opened = useRef(false);
  const openSequence = useRef(0);
  const currentUrl = useRef('');
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;
  currentUrl.current = `${location.pathname}${location.search}${location.hash}`;
  const handleDirty = useCallback((value) => { dirty.current = value; }, []);
  const handleBusy = useCallback((value) => { busy.current = value; }, []);
  const handleSaved = useCallback(() => { refreshRef.current?.(); }, []);
  useEffect(() => { setFeedback(finding.feedback || null); }, [finding.feedback]);
  const discard = useCallback(() => {
    opened.current = false;
    openSequence.current += 1;
    dirty.current = false;
    busy.current = null;
    setModalOpen(false);
    setCaseId(null);
  }, []);
  const requestLeave = useCallback((next = () => {}) => {
    if (busy.current === 'save') { messageApi.info('正在保存，请等待完成后再离开。'); return; }
    if (!dirty.current) { discard(); next(); return; }
    Modal.confirm({
      title: '放弃当前未保存修改？', content: '已保存的误报反馈继续保留，未保存的案例或说明将丢弃。',
      okText: '放弃并离开', cancelText: '继续编辑',
      onOk: () => { discard(); next(); }
    });
  }, [discard, messageApi]);
  useEffect(() => {
    if (!modalOpen && !caseId && !saving) return undefined;
    return registerSettingsNavigationGuard({
      isDirty: () => dirty.current || Boolean(busy.current),
      canNavigate: () => busy.current !== 'save',
      shouldConfirmNavigation: () => true,
      currentUrl: () => currentUrl.current, discard, requestNavigation: requestLeave
    });
  }, [modalOpen, caseId, saving, discard, requestLeave, location.key]);
  useEffect(() => {
    const handler = (event) => {
      if (!dirty.current && !busy.current) return;
      event.preventDefault(); event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => { window.removeEventListener('beforeunload', handler); openSequence.current += 1; };
  }, []);
  const open = async () => {
    const sequence = ++openSequence.current;
    opened.current = true;
    setError(null);
    setLoaded(false);
    setLoading(true);
    setModalOpen(true);
    try {
      const rows = await fetchApi(`/api/review-tasks/${taskId}/feedback`);
      if (!opened.current || sequence !== openSequence.current) return;
      const current = rows.find((row) => row.sourceType === 'AI_FINDING' && row.itemFingerprint === finding.fingerprint) || null;
      setFeedback(current);
      setLoaded(true);
      setDraft({ reasonType: current?.reasonType || 'OTHER', reasonText: current?.reasonText || '',
        missingContextTypes: current?.missingContextTypes || [], organize: false });
      dirty.current = false;
    } catch (err) {
      if (opened.current && sequence === openSequence.current) setError(feedbackError(err));
    } finally {
      if (sequence === openSequence.current) setLoading(false);
    }
  };
  const change = (patch) => { setDraft((value) => ({ ...value, ...patch })); dirty.current = true; };
  const submit = async () => {
    busy.current = 'save'; setSaving(true); setError(null);
    try {
      const saved = await saveFindingFeedback(taskId, {
        sourceType: 'AI_FINDING', itemFingerprint: finding.fingerprint,
        reviewKey: review.reviewKey, findingIndex, feedbackType: 'FALSE_POSITIVE',
        reasonType: draft.reasonType, reasonText: draft.reasonText.trim(),
        missingContextTypes: draft.reasonType === 'CONTEXT_MISSING' ? draft.missingContextTypes : [],
        suggestAsProjectRule: false
      });
      setFeedback(saved); dirty.current = false; setModalOpen(false);
      messageApi.success('反馈已保存，尚未进入审查记忆。');
      if (draft.organize) setCaseId(saved.id);
      else opened.current = false;
      onRefresh?.();
    } catch (err) { setError(feedbackError(err)); }
    finally { busy.current = null; setSaving(false); }
  };
  const withdraw = () => Modal.confirm({
    title: '撤回此误报标记？', content: '反馈将设为“已忽略”，已有同源案例会停用，等待中的回写会失效。历史记录继续保留。',
    okText: '确认撤回', cancelText: '取消', okButtonProps: { danger: true },
    onOk: async () => {
      busy.current = 'save'; setSaving(true);
      try {
        setFeedback(await withdrawFeedback(feedback.id));
        messageApi.success('已撤回，已有案例已失效。'); onRefresh?.();
      } catch (err) { messageApi.error(feedbackError(err)); throw err; }
      finally { busy.current = null; setSaving(false); }
    }
  });
  const isFalsePositive = feedback?.feedbackType === 'FALSE_POSITIVE';
  return (
    <>
      {contextHolder}
      <Button size="small" disabled={!projectId || !taskId || !finding.fingerprint || saving} onClick={open}>
        {isFalsePositive ? '修改误报标记' : '标记误报'}
      </Button>
      {isFalsePositive && <Tag>误报 · {labelFor(FEEDBACK_STATUS_OPTIONS, feedback.status)}</Tag>}
      {isFalsePositive && <Button size="small" disabled={saving} onClick={() => { opened.current = true; setCaseId(feedback.id); }}>整理 / 查看踩坑案例</Button>}
      {isFalsePositive && feedback.status !== 'IGNORED' && <Button size="small" danger loading={saving} onClick={withdraw}>撤回误报标记</Button>}
      <Modal title="标记误报" open={modalOpen} onCancel={() => requestLeave()} onOk={submit}
        confirmLoading={saving} okButtonProps={{ disabled: loading || !loaded }}
        cancelButtonProps={{ disabled: saving }} maskClosable={!saving} keyboard={!saving}
        okText="保存误报反馈" cancelText="取消">
        <Typography.Paragraph type="secondary">
          保存反馈不会自动发布案例；修改已有反馈会使原案例失效，需重新确认。
        </Typography.Paragraph>
        {loading ? <p role="status">正在读取已有反馈…</p> : <Form layout="vertical" disabled={saving} className="memory-top-space">
          <Form.Item label="误报原因"><Select aria-label="误报原因" value={draft.reasonType} options={REVIEW_FEEDBACK_REASON_OPTIONS}
            onChange={(reasonType) => change({ reasonType, missingContextTypes: reasonType === 'CONTEXT_MISSING' ? draft.missingContextTypes : [] })} /></Form.Item>
          {draft.reasonType === 'CONTEXT_MISSING' && <Form.Item label="缺失背景"><Select aria-label="缺失背景" mode="multiple"
            value={draft.missingContextTypes} options={MISSING_CONTEXT_TYPE_OPTIONS} onChange={(missingContextTypes) => change({ missingContextTypes })} /></Form.Item>}
          <Form.Item label="说明 / 参考证据" extra="填写判断依据、参考证据或缺失背景。"><Input.TextArea aria-label="说明 / 参考证据" rows={5} maxLength={4000}
            value={draft.reasonText} onChange={(event) => change({ reasonText: event.target.value })} /></Form.Item>
          <Checkbox checked={draft.organize} onChange={(event) => change({ organize: event.target.checked })}>提交后整理为踩坑案例</Checkbox>
        </Form>}
        {error && <Alert className="memory-top-space" type="error" title={error}
          action={!loaded && <Button disabled={saving || loading} onClick={open}>重新读取反馈</Button>} />}
      </Modal>
      {caseId && <MemoryFeedbackDrawer key={`${projectId}-${caseId}`} projectId={projectId} feedbackId={caseId}
        targetType={review.targetType} onClose={() => requestLeave()} onDirtyChange={handleDirty}
        onBusyChange={handleBusy} onSaved={handleSaved} />}
    </>
  );
}
