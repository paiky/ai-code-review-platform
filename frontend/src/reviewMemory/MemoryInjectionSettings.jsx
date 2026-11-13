import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Space, Switch, Tag, Typography } from 'antd';
import { getMemorySettings, saveMemorySettings } from './api.js';

export default function MemoryInjectionSettings({ projectId, onDirtyChange, onBusyChange, onSettingsChange }) {
  const [settings, setSettings] = useState(null);
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(false);
  const [retry, setRetry] = useState(0);
  const [saved, setSaved] = useState(false);
  const preserveChoice = useRef(false);
  const saveController = useRef(null);
  const dirty = Boolean(settings && settings.enabled !== enabled);

  useEffect(() => { onSettingsChange?.(settings); }, [settings, onSettingsChange]);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => {
    saveController.current?.abort();
    onDirtyChange(false);
    onBusyChange(false);
  }, [onDirtyChange, onBusyChange]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getMemorySettings(projectId, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setSettings(data);
        if (!preserveChoice.current) setEnabled(data.enabled);
        preserveChoice.current = false;
        setConflict(false);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, retry]);

  async function save() {
    if (saving || loading || conflict || !dirty || !settings?.schemaReady) return;
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    onBusyChange(true);
    setError(null);
    setSaved(false);
    try {
      const data = await saveMemorySettings(projectId, enabled, settings.version, controller.signal);
      if (controller.signal.aborted) return;
      setSettings(data);
      setEnabled(data.enabled);
      onDirtyChange(false);
      setSaved(true);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err.code === 'MEMORY_SCHEMA_PENDING' ? '记忆设置尚未就绪，请完成数据库迁移后重新读取。' : err.message);
      setConflict(err.status === 409 || err.code === 'MEMORY_SCHEMA_PENDING');
    } finally {
      if (!controller.signal.aborted) {
        setSaving(false);
        onBusyChange(false);
      }
    }
  }

  return (
    <Card size="small" className="memory-injection-settings memory-top-space" title="用于后续 Agent Review">
      <Space orientation="vertical" className="full-width">
        <Typography.Text type="secondary">
          只影响新入队的 Agent Review；已入队任务继续使用冻结背景。Skill 仅提供文字指引，不执行命令。
        </Typography.Text>
        <Space wrap>
          <Switch aria-label="用于后续 Agent Review" checked={enabled}
            disabled={loading || saving || conflict || !settings?.schemaReady}
            loading={loading || saving}
            checkedChildren="开启" unCheckedChildren="关闭"
            onChange={(value) => { setEnabled(value); onDirtyChange(value !== settings.enabled); setSaved(false); }} />
          <Button aria-label="保存记忆设置" type="primary" loading={saving} disabled={loading || conflict || !dirty || !settings?.schemaReady} onClick={save}>
            保存记忆设置
          </Button>
          {settings && <Tag>已保存：{settings.enabled ? '开启' : '关闭'} · 版本 {settings.version}</Tag>}
          {dirty && <Tag color="gold">未保存选择：{enabled ? '开启' : '关闭'}</Tag>}
        </Space>
        {settings && !settings.schemaReady && <Alert type="warning" showIcon title="记忆设置尚未就绪"
          description="请先完成数据库迁移；资料管理仍可使用。"
          action={<Button disabled={loading} onClick={() => setRetry((value) => value + 1)}>重新读取</Button>} />}
        {error && <Alert type="error" showIcon title={conflict ? '设置已变化，请先对比最新状态' : '记忆设置操作失败'}
          description={`${error}${settings ? ' 当前选择已保留。' : ''}`}
          action={<Button disabled={loading || saving} onClick={() => {
            preserveChoice.current = Boolean(settings);
            setRetry((value) => value + 1);
          }}>{settings ? '读取最新设置并保留选择' : '重试读取'}</Button>} />}
        {saved && <Typography.Text type="success" role="status">记忆设置已保存，仅对后续入队任务生效。</Typography.Text>}
      </Space>
    </Card>
  );
}
