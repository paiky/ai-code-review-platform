import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  message,
  Modal,
  Radio,
  Select,
  Space,
  Spin,
  Tag,
  Typography
} from 'antd';
import { RobotOutlined } from '@ant-design/icons';

import {
  fetchNotificationWebhooks,
  previewBatchNotificationWebhooks,
  saveBatchNotificationWebhooks
} from './projectConfigurationApi.js';
import { projectDisplayName, webhookTestMeta } from './projectConfigurationModel.js';

const { Text, Title } = Typography;

const MODE_OPTIONS = [
  { value: 'REPLACE', label: '覆盖现有配置', description: '用本次选择完全替换项目原有机器人', tag: '推荐' },
  { value: 'ADD', label: '追加机器人', description: '保留原配置并新增所选机器人' },
  { value: 'REMOVE', label: '移除指定机器人', description: '仅移除所选机器人，其他配置不变' }
];

export default function BatchWebhookDrawer({
  open,
  projects,
  onClose,
  onSaved,
  onDirtyChange
}) {
  const [messageApi, contextHolder] = message.useMessage();
  const [mode, setMode] = useState('REPLACE');
  const [webhookIds, setWebhookIds] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);
  const dirty = mode !== 'REPLACE' || webhookIds.length > 0;

  useEffect(() => onDirtyChange?.(open && dirty), [dirty, onDirtyChange, open]);

  useEffect(() => {
    if (!open) return;
    setMode('REPLACE');
    setWebhookIds([]);
    setPreview(null);
    setError(null);
    setLoading(true);
    fetchNotificationWebhooks({}, { pageNo: 1, pageSize: 100 })
      .then(data => setWebhooks(Array.isArray(data) ? data : (data?.items || [])))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [open]);

  const payload = useMemo(() => ({
    projectIds: projects.map(project => project.id),
    webhookIds,
    mode
  }), [mode, projects, webhookIds]);

  const changeMode = value => {
    setMode(value);
    setWebhookIds([]);
    setPreview(null);
  };

  const changeWebhooks = value => {
    setWebhookIds(value);
    setPreview(null);
  };

  const requestClose = () => {
    if (!dirty) {
      onClose?.();
      return;
    }
    Modal.confirm({
      title: '放弃批量配置草稿？',
      content: '已选择的项目会保留，可重新打开批量配置。',
      okText: '放弃草稿',
      cancelText: '继续编辑',
      onOk: () => {
        onDirtyChange?.(false);
        onClose?.();
      }
    });
  };

  const runPreview = async () => {
    setPreviewing(true);
    setError(null);
    try {
      setPreview(await previewBatchNotificationWebhooks(payload));
    } catch (err) {
      setError(err.message);
    } finally {
      setPreviewing(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await saveBatchNotificationWebhooks(payload);
      if (JSON.stringify(result) !== JSON.stringify(preview)) {
        messageApi.warning('保存时数据已变化，列表已按最新结果刷新');
      } else {
        messageApi.success(`已配置 ${projects.length} 个项目`);
      }
      onDirtyChange?.(false);
      onSaved?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const webhookById = new Map(webhooks.map(item => [item.id, item]));

  return (
    <>
      {contextHolder}
      <Drawer
        open={open}
        size="min(560px, 100vw)"
        className="project-config-drawer"
        title={(
          <div className="project-config-drawer-title">
            <span>批量配置机器人</span>
            <Text type="secondary">已选择 {projects.length} 个项目</Text>
          </div>
        )}
        onClose={requestClose}
        mask={{ closable: !saving }}
        footer={(
          <div className="project-config-drawer-footer">
            <Button onClick={requestClose} disabled={saving}>取消</Button>
            {preview ? (
              <Button type="primary" loading={saving} onClick={save}>
                确认配置 {projects.length} 个项目
              </Button>
            ) : (
              <Button type="primary" loading={previewing} onClick={runPreview} disabled={loading}>
                预览变更
              </Button>
            )}
          </div>
        )}
      >
        <Spin spinning={loading}>
          <div className="project-config-drawer-content">
            {error && <Alert type="error" showIcon title="批量配置失败" description={error} />}
            <section className="project-config-drawer-section">
              <div className="project-config-drawer-section-header">
                <span className="project-config-section-icon"><RobotOutlined /></span>
                <div><Title level={5}>操作模式</Title><Text type="secondary">批量操作只修改机器人关联</Text></div>
              </div>
              <Radio.Group className="project-config-mode-group" value={mode} onChange={event => changeMode(event.target.value)}>
                {MODE_OPTIONS.map(option => (
                  <Radio key={option.value} value={option.value} className="project-config-mode-option">
                    <span className="project-config-mode-copy">
                      <span><Text strong>{option.label}</Text>{option.tag && <Tag color="blue">{option.tag}</Tag>}</span>
                      <Text type="secondary">{option.description}</Text>
                    </span>
                  </Radio>
                ))}
              </Radio.Group>
            </section>

            <section className="project-config-drawer-section">
              <Title level={5}>选择机器人</Title>
              <Select
                mode="multiple"
                allowClear
                className="full-width"
                value={webhookIds}
                placeholder={mode === 'REMOVE' ? '选择需要移除的机器人' : '选择启用机器人'}
                options={webhooks.map(webhook => {
                  const testMeta = webhookTestMeta(webhook.lastTestStatus);
                  return {
                    value: webhook.id,
                    disabled: mode !== 'REMOVE' && !webhook.enabled,
                    label: (
                      <Space size={6}>
                        <span>{webhook.name}</span>
                        <Text type="secondary">{webhook.webhookMasked}</Text>
                        <Tag color={webhook.enabled ? 'success' : 'default'}>{webhook.enabled ? '启用' : '停用'}</Tag>
                        <Tag color={testMeta.color}>{testMeta.label}</Tag>
                      </Space>
                    )
                  };
                })}
                onChange={changeWebhooks}
              />
            </section>

            {preview && (
              <section className="project-config-drawer-section project-config-preview-section">
                <Alert
                  type="info"
                  showIcon
                  title={`${preview.changedProjectCount} 个项目将调整，${preview.unchangedProjectCount} 个无需调整`}
                />
                <div className="project-config-preview-list">
                  {preview.items.map(item => {
                    const project = projects.find(row => row.id === item.projectId);
                    return (
                      <div className="project-config-preview-item" key={item.projectId}>
                        <div className="project-config-preview-title">
                          <Text strong>{projectDisplayName(project || { id: item.projectId })}</Text>
                          <Text type="secondary">GitLab ID {project?.gitProjectId || '-'}</Text>
                        </div>
                        <Descriptions size="small" column={1}>
                          <Descriptions.Item label="变更前">
                            <Space wrap>{item.beforeWebhookIds.map(id => <Tag key={id}>{webhookById.get(id)?.name || id}</Tag>)}{!item.beforeWebhookIds.length && <Text type="secondary">无</Text>}</Space>
                          </Descriptions.Item>
                          <Descriptions.Item label="变更后">
                            <Space wrap>{item.afterWebhookIds.map(id => <Tag color="blue" key={id}>{webhookById.get(id)?.name || id}</Tag>)}{!item.afterWebhookIds.length && <Text type="secondary">无</Text>}</Space>
                          </Descriptions.Item>
                        </Descriptions>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            <Alert
              type="info"
              showIcon
              title="仅修改钉钉机器人绑定，不影响端类型、Review 配置或 MR/PUSH 触发"
            />
          </div>
        </Spin>
      </Drawer>
    </>
  );
}
