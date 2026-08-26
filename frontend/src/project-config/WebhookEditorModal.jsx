import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Input, Modal, Space, Switch, Typography } from 'antd';

import {
  createNotificationWebhook,
  updateNotificationWebhook
} from './projectConfigurationApi.js';

const { Text } = Typography;

function initialDraft(webhook) {
  return {
    name: webhook?.name || '',
    description: webhook?.description || '',
    enabled: webhook?.enabled !== false,
    webhookUrl: '',
    replaceWebhook: false
  };
}

export default function WebhookEditorModal({
  open,
  webhook,
  onCancel,
  onSaved,
  onDirtyChange
}) {
  const [draft, setDraft] = useState(() => initialDraft(webhook));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const editing = Boolean(webhook?.id);
  const baseline = useMemo(() => JSON.stringify(initialDraft(webhook)), [webhook]);
  const dirty = JSON.stringify(draft) !== baseline;

  useEffect(() => {
    if (!open) return;
    setDraft(initialDraft(webhook));
    setError(null);
  }, [open, webhook]);

  useEffect(() => {
    onDirtyChange?.(open && dirty);
  }, [dirty, onDirtyChange, open]);

  const update = (field, value) => setDraft(current => ({ ...current, [field]: value }));

  const submit = async () => {
    const name = draft.name.trim();
    const webhookUrl = draft.webhookUrl.trim();
    if (!name) {
      setError('请输入机器人名称');
      return;
    }
    if ((!editing || draft.replaceWebhook) && !webhookUrl) {
      setError('请输入钉钉 Webhook');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name,
        description: draft.description.trim() || null,
        enabled: draft.enabled
      };
      if (!editing || draft.replaceWebhook) payload.webhookUrl = webhookUrl;
      const saved = editing
        ? await updateNotificationWebhook(webhook.id, payload)
        : await createNotificationWebhook(payload);
      onDirtyChange?.(false);
      onSaved?.(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={editing ? '编辑钉钉机器人' : '新增钉钉机器人'}
      width={520}
      onCancel={onCancel}
      mask={{ closable: !saving }}
      footer={(
        <Space>
          <Button onClick={onCancel} disabled={saving}>取消</Button>
          <Button type="primary" onClick={submit} loading={saving}>
            {editing ? '保存机器人' : '新增机器人'}
          </Button>
        </Space>
      )}
    >
      <div className="project-config-form-stack">
        {error && <Alert type="error" showIcon title={error} />}
        <label className="project-config-field">
          <Text strong>机器人名称</Text>
          <Input
            value={draft.name}
            maxLength={128}
            placeholder="例如 前端研发群"
            onChange={event => update('name', event.target.value)}
          />
        </label>
        {editing && (
          <div className="project-config-field">
            <Text strong>当前 Webhook</Text>
            <Text code>{webhook.webhookMasked || '-'}</Text>
            <Space>
              <Switch
                checked={draft.replaceWebhook}
                onChange={checked => update('replaceWebhook', checked)}
              />
              <Text>更换 Webhook</Text>
            </Space>
          </div>
        )}
        {(!editing || draft.replaceWebhook) && (
          <label className="project-config-field">
            <Text strong>Webhook</Text>
            <Input.Password
              value={draft.webhookUrl}
              maxLength={1024}
              placeholder="https://oapi.dingtalk.com/robot/send?..."
              onChange={event => update('webhookUrl', event.target.value)}
            />
          </label>
        )}
        <label className="project-config-field">
          <Text strong>描述</Text>
          <Input.TextArea
            value={draft.description}
            maxLength={512}
            autoSize={{ minRows: 2, maxRows: 4 }}
            placeholder="说明机器人用途"
            onChange={event => update('description', event.target.value)}
          />
        </label>
        <div className="project-config-field project-config-switch-field project-config-webhook-status-field">
          <div>
            <Text strong>启用状态</Text>
            <Text type="secondary">停用后保留项目关联，但项目通知状态将显示配置异常。</Text>
          </div>
          <Switch
            checked={draft.enabled}
            checkedChildren="启用"
            unCheckedChildren="停用"
            onChange={checked => update('enabled', checked)}
          />
        </div>
      </div>
    </Modal>
  );
}
