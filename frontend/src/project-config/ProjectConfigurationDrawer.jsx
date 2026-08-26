import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

import {
  applyTargetDetection,
  fetchNotificationWebhooks,
  fetchProjectConfiguration,
  fetchProjectConfigurationDefaults,
  fetchReviewProfiles,
  fetchTargetDetectionPreview,
  saveProjectConfiguration
} from './projectConfigurationApi.js';
import {
  applyProjectEditorDefaults,
  configurationFingerprint,
  normalizeProjectConfiguration,
  TARGET_TYPE_OPTIONS,
  targetTypeMeta,
  webhookTestMeta
} from './projectConfigurationModel.js';
import WebhookEditorModal from './WebhookEditorModal.jsx';

const { Text, Title } = Typography;

function listItems(data) {
  return Array.isArray(data) ? data : (data?.items || []);
}

function SectionHeader({ icon, title, description }) {
  return (
    <div className="project-config-drawer-section-header">
      <span className="project-config-section-icon" aria-hidden="true">{icon}</span>
      <div>
        <Title level={5}>{title}</Title>
        {description && <Text type="secondary">{description}</Text>}
      </div>
    </div>
  );
}

function ChangeValue({ value }) {
  if (Array.isArray(value)) return <Text>{value.join('、') || '无'}</Text>;
  if (typeof value === 'boolean') return <Text>{value ? '开启' : '关闭'}</Text>;
  return <Text>{value ?? '无'}</Text>;
}

export default function ProjectConfigurationDrawer({
  open,
  project,
  onClose,
  onSaved,
  onDirtyChange
}) {
  const [messageApi, contextHolder] = message.useMessage();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [baseline, setBaseline] = useState('');
  const [profiles, setProfiles] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [targetChange, setTargetChange] = useState(null);
  const [defaultLoading, setDefaultLoading] = useState(false);
  const [webhookEditorOpen, setWebhookEditorOpen] = useState(false);
  const [webhookEditorDirty, setWebhookEditorDirty] = useState(false);
  const [detectionPreview, setDetectionPreview] = useState(null);
  const [detectionLoading, setDetectionLoading] = useState(false);
  const [detectionApplying, setDetectionApplying] = useState(false);

  const dirty = Boolean(draft) && configurationFingerprint(draft) !== baseline;

  useEffect(() => {
    onDirtyChange?.(open && (dirty || webhookEditorDirty));
  }, [dirty, onDirtyChange, open, webhookEditorDirty]);

  useEffect(() => {
    if (!open || !project?.id) return;
    let active = true;
    setLoading(true);
    setError(null);
    setTargetChange(null);
    setDetectionPreview(null);
    const configurationRequest = fetchProjectConfiguration(project.id);
    Promise.all([
      configurationRequest,
      configurationRequest.then(configuration => fetchProjectConfigurationDefaults(configuration.targetType)),
      fetchReviewProfiles(),
      fetchNotificationWebhooks({}, { pageNo: 1, pageSize: 100 })
    ])
      .then(([configuration, defaults, profileData, webhookData]) => {
        if (!active) return;
        const normalized = normalizeProjectConfiguration(configuration);
        const managed = applyProjectEditorDefaults(normalized, defaults);
        setDraft(managed);
        setBaseline(configurationFingerprint(normalized));
        setProfiles(listItems(profileData));
        setWebhooks(listItems(webhookData));
      })
      .catch(err => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [open, project?.id]);

  const profileOptions = useMemo(() => {
    const current = draft?.targetConfig?.codeQualityProfileCode;
    const rows = profiles.map(profile => ({
      value: profile.profileCode,
      label: profile.profileName || profile.displayName || profile.profileCode
    }));
    if (current && !rows.some(item => item.value === current)) {
      rows.unshift({ value: current, label: current });
    }
    return rows;
  }, [draft?.targetConfig?.codeQualityProfileCode, profiles]);

  const updateDraft = (field, value) => setDraft(current => ({ ...current, [field]: value }));
  const updateTargetConfig = (field, value) => setDraft(current => ({
    ...current,
    targetConfig: { ...current.targetConfig, [field]: value }
  }));
  const updateReviewSettings = (field, value) => setDraft(current => ({
    ...current,
    reviewSettings: { ...current.reviewSettings, [field]: value }
  }));

  const changeTargetType = async targetType => {
    if (targetType === draft?.targetType) return;
    setDefaultLoading(true);
    setError(null);
    try {
      const defaults = await fetchProjectConfigurationDefaults(targetType);
      const nextTargetConfig = {
        templateCode: defaults.targetConfig.templateCode,
        codeQualityProfileCode: defaults.targetConfig.codeQualityProfileCode || null,
        providerCode: defaults.targetConfig.providerCode || null,
        pathPatterns: defaults.targetConfig.pathPatterns || ['**/*'],
        reminderCardEnabled: Boolean(defaults.targetConfig.reminderCardEnabled)
      };
      setTargetChange({
        beforeType: draft.targetType,
        afterType: targetType,
        beforeConfig: draft.targetConfig,
        afterConfig: nextTargetConfig
      });
      setDraft(current => ({
        ...current,
        targetType,
        targetConfig: nextTargetConfig,
        aiReviewModels: []
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setDefaultLoading(false);
    }
  };

  const requestClose = () => {
    onDirtyChange?.(false);
    onClose?.();
  };

  const save = async () => {
    if (!draft?.targetConfig?.templateCode?.trim()) {
      setError('请选择规则模板');
      return;
    }
    if (!draft.targetConfig.pathPatterns?.length) {
      setError('至少保留一条项目路径规则');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveProjectConfiguration(project.id, draft);
      const normalized = normalizeProjectConfiguration(saved);
      setDraft(normalized);
      setBaseline(configurationFingerprint(normalized));
      setTargetChange(null);
      messageApi.success('项目配置已保存');
      onSaved?.(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const previewDetection = async () => {
    setDetectionLoading(true);
    setError(null);
    try {
      setDetectionPreview(await fetchTargetDetectionPreview(project.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setDetectionLoading(false);
    }
  };

  const applyDetection = async () => {
    if (!detectionPreview) return;
    setDetectionApplying(true);
    try {
      const result = await applyTargetDetection(project.id, {
        targetType: detectionPreview.detectedTargetType,
        evidenceVersion: detectionPreview.evidenceVersion
      });
      const normalized = normalizeProjectConfiguration(result.configuration);
      const managed = applyProjectEditorDefaults(normalized, {
        targetConfig: normalized.targetConfig
      });
      setDraft(managed);
      setBaseline(configurationFingerprint(normalized));
      setTargetChange(null);
      setDetectionPreview(null);
      messageApi.success('已恢复端类型自动识别结果');
      onSaved?.(result.configuration);
    } catch (err) {
      setError(err.message);
      setDetectionPreview(null);
    } finally {
      setDetectionApplying(false);
    }
  };

  return (
    <>
      {contextHolder}
      <Drawer
        open={open}
        size="min(560px, 100vw)"
        className="project-config-drawer"
        title={(
          <div className="project-config-drawer-title">
            <span>配置项目</span>
            <Text type="secondary">{project?.name || '-'} · GitLab ID {project?.gitProjectId || '-'}</Text>
          </div>
        )}
        onClose={requestClose}
        mask={{ closable: !saving }}
        footer={(
          <div className="project-config-drawer-footer">
            <Button onClick={requestClose} disabled={saving}>取消</Button>
            <Button type="primary" onClick={save} loading={saving} disabled={loading || !draft}>
              保存项目配置
            </Button>
          </div>
        )}
      >
        <Spin spinning={loading}>
          <div className="project-config-drawer-content">
            {error && <Alert type="error" showIcon title="项目配置操作失败" description={error} closable onClose={() => setError(null)} />}
            {draft && (
              <>
                <section className="project-config-drawer-section">
                  <div className="project-config-form-grid two-columns">
                    <label className="project-config-field">
                      <Text strong>端类型</Text>
                      <Select
                        value={draft.targetType}
                        loading={defaultLoading}
                        options={TARGET_TYPE_OPTIONS}
                        onChange={changeTargetType}
                      />
                    </label>
                    <label className="project-config-field">
                      <Text strong>规则模板</Text>
                      <Select
                        showSearch
                        value={draft.targetConfig.templateCode}
                        options={[{ value: draft.targetConfig.templateCode, label: draft.targetConfig.templateCode }]}
                        onChange={value => updateTargetConfig('templateCode', value)}
                      />
                    </label>
                  </div>
                  <label className="project-config-field">
                    <Text strong>AI Review Profile</Text>
                    <Select
                      allowClear
                      showSearch
                      value={draft.targetConfig.codeQualityProfileCode || undefined}
                      options={profileOptions}
                      placeholder="当前端类型未配置默认 Profile"
                      onChange={value => updateTargetConfig('codeQualityProfileCode', value || null)}
                    />
                  </label>
                  <label className="project-config-field">
                    <Text strong>项目路径规则</Text>
                    <Select
                      mode="tags"
                      value={draft.targetConfig.pathPatterns}
                      placeholder="输入路径规则后回车"
                      onChange={value => updateTargetConfig('pathPatterns', value)}
                    />
                  </label>
                  <div className="project-config-switch-field">
                    <div>
                      <Text strong>提醒卡片</Text>
                      <Text type="secondary">Review 完成后展示结构化提醒卡片</Text>
                    </div>
                    <Switch
                      checked={draft.targetConfig.reminderCardEnabled}
                      onChange={checked => updateTargetConfig('reminderCardEnabled', checked)}
                    />
                  </div>
                  {targetChange && (
                    <Alert
                      type="warning"
                      showIcon
                      title="端类型变化将同时调整以下 Review 配置"
                      description={(
                        <Descriptions size="small" column={1} className="project-config-change-list">
                          <Descriptions.Item label="端类型">
                            {targetTypeMeta(targetChange.beforeType).label} → {targetTypeMeta(targetChange.afterType).label}
                          </Descriptions.Item>
                          <Descriptions.Item label="规则模板">
                            <ChangeValue value={targetChange.beforeConfig.templateCode} /> → <ChangeValue value={targetChange.afterConfig.templateCode} />
                          </Descriptions.Item>
                          <Descriptions.Item label="Profile">
                            <ChangeValue value={targetChange.beforeConfig.codeQualityProfileCode} /> → <ChangeValue value={targetChange.afterConfig.codeQualityProfileCode} />
                          </Descriptions.Item>
                        </Descriptions>
                      )}
                    />
                  )}
                  <Button icon={<ReloadOutlined />} loading={detectionLoading} onClick={previewDetection}>
                    恢复自动识别
                  </Button>
                </section>

                <Divider />
                <section className="project-config-drawer-section">
                  <SectionHeader
                    icon={<ThunderboltOutlined />}
                    title="Review 触发"
                    description="Manual Review 始终可用，不受这里的自动触发开关影响"
                  />
                  <div className="project-config-switch-field">
                    <div><Text strong>MR 自动 Review</Text><Text type="secondary">Merge Request 创建或更新时触发</Text></div>
                    <Switch checked={draft.reviewSettings.triggerOnMr} onChange={checked => updateReviewSettings('triggerOnMr', checked)} />
                  </div>
                  <div className="project-config-switch-field">
                    <div><Text strong>PUSH 自动 Review</Text><Text type="secondary">代码推送满足条件后触发</Text></div>
                    <Switch checked={draft.reviewSettings.triggerOnPush} onChange={checked => updateReviewSettings('triggerOnPush', checked)} />
                  </div>
                  <div className="project-config-switch-field">
                    <div><Text strong>风险命中后才触发</Text><Text type="secondary">仅在规则识别到风险时调用 Review</Text></div>
                    <Switch checked={draft.reviewSettings.triggerOnlyWhenRiskMatched} onChange={checked => updateReviewSettings('triggerOnlyWhenRiskMatched', checked)} />
                  </div>
                  <div className="project-config-switch-field">
                    <div><Text strong>自动修复预览</Text><Text type="secondary">为指定严重级别生成修复预览</Text></div>
                    <Switch checked={draft.reviewSettings.autoFixPreviewEnabled} onChange={checked => updateReviewSettings('autoFixPreviewEnabled', checked)} />
                  </div>
                  {draft.reviewSettings.autoFixPreviewEnabled && (
                    <label className="project-config-field">
                      <Text strong>修复预览严重级别</Text>
                      <Select
                        mode="multiple"
                        value={draft.reviewSettings.autoFixPreviewSeverities}
                        options={[
                          { label: '严重', value: 'CRITICAL' },
                          { label: '主要', value: 'MAJOR' },
                          { label: '次要', value: 'MINOR' }
                        ]}
                        onChange={value => updateReviewSettings('autoFixPreviewSeverities', value)}
                      />
                    </label>
                  )}
                  {draft.reviewSettings.triggerOnPush && (
                    <Collapse
                      ghost
                      defaultActiveKey={['push-advanced']}
                      items={[{
                        key: 'push-advanced',
                        label: 'PUSH 高级条件',
                        children: (
                          <div className="project-config-form-stack">
                            <label className="project-config-field">
                              <Text strong>分支模式</Text>
                              <Select mode="tags" value={draft.reviewSettings.pushBranchPatterns} onChange={value => updateReviewSettings('pushBranchPatterns', value)} />
                            </label>
                            <div className="project-config-form-grid two-columns">
                              {[
                                ['pushMinChangedFiles', '最小文件数', 0],
                                ['pushMaxChangedFiles', '最大文件数', -1],
                                ['pushMinDiffBytes', '最小 diff 字节', 0],
                                ['pushMaxDiffBytes', '最大 diff 字节', -1],
                                ['pushMinCommitCount', '最小 commit 数', 0],
                                ['pushDebounceSeconds', '防抖秒数', 0]
                              ].map(([field, label, min]) => (
                                <label className="project-config-field" key={field}>
                                  <Text strong>{label}</Text>
                                  <InputNumber
                                    min={min}
                                    className="full-width"
                                    value={draft.reviewSettings[field]}
                                    onChange={value => updateReviewSettings(field, value ?? min)}
                                  />
                                </label>
                              ))}
                            </div>
                          </div>
                        )
                      }]}
                    />
                  )}
                </section>

                <Divider />
                <section className="project-config-drawer-section">
                  <SectionHeader
                    icon={<RobotOutlined />}
                    title="钉钉通知"
                    description="一个项目可关联多个机器人"
                  />
                  <label className="project-config-field">
                    <Text strong>通知机器人</Text>
                    <Select
                      mode="multiple"
                      allowClear
                      value={draft.webhookIds}
                      placeholder="选择钉钉机器人"
                      options={webhooks.map(webhook => {
                        const testMeta = webhookTestMeta(webhook.lastTestStatus);
                        const selected = draft.webhookIds.includes(webhook.id);
                        return {
                          value: webhook.id,
                          disabled: !webhook.enabled && !selected,
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
                      onChange={value => updateDraft('webhookIds', value)}
                    />
                  </label>
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => setWebhookEditorOpen(true)}>
                    新增机器人
                  </Button>
                  {draft.webhookIds.length > 0 && (
                    <Text type="secondary">Review 完成后将通知 {draft.webhookIds.length} 个群</Text>
                  )}
                </section>
              </>
            )}
          </div>
        </Spin>
      </Drawer>

      <WebhookEditorModal
        open={webhookEditorOpen}
        onDirtyChange={setWebhookEditorDirty}
        onCancel={() => {
          if (webhookEditorDirty) {
            Modal.confirm({
              title: '放弃新机器人草稿？',
              okText: '放弃修改',
              cancelText: '继续编辑',
              onOk: () => {
                setWebhookEditorOpen(false);
                setWebhookEditorDirty(false);
              }
            });
            return;
          }
          setWebhookEditorOpen(false);
        }}
        onSaved={saved => {
          setWebhooks(current => [saved, ...current.filter(item => item.id !== saved.id)]);
          updateDraft('webhookIds', [...new Set([...(draft?.webhookIds || []), saved.id])]);
          setWebhookEditorOpen(false);
          setWebhookEditorDirty(false);
          messageApi.success('机器人已新增并选中');
        }}
      />

      <Modal
        open={Boolean(detectionPreview)}
        title="恢复端类型自动识别"
        width={600}
        onCancel={() => setDetectionPreview(null)}
        footer={(
          <Space>
            <Button onClick={() => setDetectionPreview(null)}>取消</Button>
            <Button type="primary" loading={detectionApplying} onClick={applyDetection}>
              应用识别结果
            </Button>
          </Space>
        )}
      >
        {detectionPreview && (
          <div className="project-config-form-stack">
            <Alert
              type="warning"
              showIcon
              title={`将采用 ${targetTypeMeta(detectionPreview.detectedTargetType).label}`}
              description={`当前端类型为 ${targetTypeMeta(detectionPreview.currentTargetType).label}，识别证据变化后需要重新预览。`}
            />
            <div>
              <Text strong>全部候选：</Text>
              <Space wrap>{detectionPreview.detectedTargetTypes.map(item => <Tag key={item}>{targetTypeMeta(item).label}</Tag>)}</Space>
            </div>
            <Descriptions size="small" column={1} bordered>
              {(detectionPreview.changes || []).map(change => (
                <Descriptions.Item key={change.field} label={change.field}>
                  <ChangeValue value={change.before} /> → <ChangeValue value={change.after} />
                </Descriptions.Item>
              ))}
            </Descriptions>
            <Tooltip title={detectionPreview.evidenceVersion}>
              <Text type="secondary">证据版本：{detectionPreview.evidenceVersion.slice(0, 12)}...</Text>
            </Tooltip>
          </div>
        )}
      </Modal>
    </>
  );
}
