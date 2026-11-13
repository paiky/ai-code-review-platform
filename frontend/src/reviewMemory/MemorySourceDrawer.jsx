import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
  Upload
} from 'antd';
import { DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import MemoryEntryFields from './MemoryEntryFields.jsx';
import { downloadOriginal, getSource, getSourceImpact, mutateSource, uploadSource } from './api.js';
import {
  allowsCore,
  blankEntry,
  bytes,
  entryDraft,
  KIND_OPTIONS,
  labelFor,
  ORIGIN_LABELS,
  publicationError,
  STATE_LABELS,
  stateColor,
  TARGET_TYPE_OPTIONS,
  validateEntry,
  uploadProblem,
  DOCUMENT_ERRORS
} from './model.js';

const { Text, Title, Paragraph } = Typography;

export default function MemorySourceDrawer({
  projectId: initialProjectId,
  projectName,
  ownerOptions,
  ownerLoading,
  onOwnerSearch,
  initial,
  onClose,
  onDirtyChange,
  onBusyChange,
  onSaved,
  projectLabel,
  onManageBinding,
  onViewFeedback,
  onLoaded
}) {
  const [selectedOwner, setSelectedOwner] = useState(initialProjectId || '');
  const projectId = initial.library ? null : selectedOwner;
  const [source, setSource] = useState(null);
  const [creation, setCreation] = useState(initial.mode === 'view' ? null : initial.mode);
  const [metadata, setMetadata] = useState({
    kind: initial.kind,
    title: '',
    description: ''
  });
  const [creationEntry, setCreationEntry] = useState(() => blankEntry(initial.kind));
  const [file, setFile] = useState(null);
  const [touched, setTouched] = useState(false);
  const [editor, setEditor] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(initial.mode === 'view');
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [latest, setLatest] = useState(null);
  const [replacement, setReplacement] = useState(null);
  const [publishPreview, setPublishPreview] = useState(null);
  const [operatorName, setOperatorName] = useState('');
  const [impactView, setImpactView] = useState(null);
  const uploadController = useRef(null);
  const mounted = useRef(true);
  const active = source?.entries.find((item) => item.id === activeId);
  const dirty = creation
    ? touched
    : Boolean(editor && JSON.stringify(editor.value) !== editor.baseline);
  const readOnly = !source?.canManage || source?.projectId === null;

  useEffect(() => {
    if (source) onLoaded?.(source);
  }, [source, onLoaded]);

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    onBusyChange(busy);
  }, [busy, onBusyChange]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      uploadController.current?.abort();
      onDirtyChange(false);
      onBusyChange(null);
    };
  }, [onDirtyChange, onBusyChange]);

  function adopt(next) {
    setSource(next);
    setCreation(null);
    setTouched(false);
    setEditor(null);
    setActiveId((current) =>
      next.entries.some((item) => item.id === current) ? current : next.entries[0]?.id
    );
    setSelected(
      next.entries
        .filter((item) => item.state === 'DRAFT' && !publicationError(item))
        .map((item) => item.id)
    );
    setLatest(null);
    setError(null);
    setImpactView(null);
  }

  useEffect(() => {
    if (initial.mode !== 'view') return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getSource(projectId, initial.sourceId, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) adopt(next);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [initial.sourceId, initial.mode, projectId, retry]);

  function guardLocal(action) {
    if (busy) return;
    if (!dirty) {
      action();
      return;
    }
    Modal.confirm({
      title: '放弃当前未保存修改？',
      content: '已保存的草稿仍会保留。',
      okText: '放弃修改',
      cancelText: '继续编辑',
      onOk: () => {
        setEditor(null);
        action();
      }
    });
  }

  async function perform(action, { upload = false, adoptResult = true } = {}) {
    if (busy) return null;
    setBusy(upload ? 'upload' : 'save');
    onBusyChange(upload ? 'upload' : 'save');
    setError(null);
    try {
      const result = await action();
      if (!mounted.current) return null;
      if (result == null) return null;
      if (adoptResult) {
        adopt(result);
        onSaved();
      }
      return result;
    } catch (err) {
      if (mounted.current && err.name !== 'AbortError') setError(err);
      return null;
    } finally {
      if (mounted.current) {
        setBusy(null);
        onBusyChange(null);
      }
    }
  }

  function impactContent(impact) {
    return (
      <>
        <Paragraph>
          影响的 ACTIVE 关联项目（{impact.projectIds.length} 个）：
          {impact.projectIds.map(projectLabel).join('、') || '无'}。
        </Paragraph>
        <Paragraph>
          保存已发布章节会将其转为草稿，以上项目均暂时无法使用该章节。共享修改对所有使用项目生效，历史任务不变。
        </Paragraph>
      </>
    );
  }

  function assertImpactVersion(impact, version) {
    if (impact.sourceVersion !== version) {
      const conflict = new Error('资料或关联已变化，请查看最新版本并重新核对影响范围。');
      conflict.status = 409;
      throw conflict;
    }
  }

  async function changeSource(suffix, method, payload) {
    const impact = await getSourceImpact(projectId, source.id);
    assertImpactVersion(impact, source.version);
    const needsConfirmation =
      source.visibility === 'SHARED' ||
      payload?.visibility === 'SHARED' ||
      impact.projectIds.some((id) => String(id) !== String(projectId));
    const approved =
      !needsConfirmation ||
      (await new Promise((resolve) =>
        Modal.confirm({
          title: '确认修改资料及其项目影响',
          content: impactContent(impact),
          okText: '确认影响并继续',
          cancelText: '取消',
          onOk: () => {
            resolve(true);
          },
          onCancel: () => {
            resolve(false);
          }
        })
      ));
    if (!approved) return null;
    if (method === 'DELETE') {
      const query = new URLSearchParams({
        expectedVersion: String(source.version)
      });
      impact.projectIds.forEach((id) => query.append('acknowledgedProjectIds', String(id)));
      return mutateSource(projectId, `sources/${source.id}?${query}`, method);
    }
    return mutateSource(projectId, suffix, method, {
      ...payload,
      acknowledgedProjectIds: impact.projectIds
    });
  }

  async function saveCreation() {
    if (!projectId) {
      setError(new Error('请选择归属项目。'));
      return;
    }
    if (creation === 'manual' && !metadata.title.trim()) {
      setError(new Error('请填写资料标题。'));
      return;
    }
    if (creation === 'manual') {
      const problem = validateEntry(creationEntry);
      if (problem) {
        setError(new Error(problem));
        return;
      }
    } else if (!file) {
      setError(new Error('请选择一个 MD／TXT／DOCX／PDF 文件，Skill 仅支持 Markdown。'));
      return;
    }
    if (creation === 'upload') {
      const problem = uploadProblem(file, metadata.kind);
      if (problem) {
        setError(new Error(problem));
        return;
      }
      const { heading: _heading, content: _content, ...labels } = creationEntry;
      const payload = {
        ...metadata,
        ...labels,
        ...(metadata.title.trim() ? { title: metadata.title.trim() } : {})
      };
      if (!payload.title) delete payload.title;
      if (!payload.description) delete payload.description;
      if (replacement)
        Object.assign(payload, {
          replacementOfId: replacement.id,
          expectedReplacedVersion: replacement.version
        });
      uploadController.current = new AbortController();
      await perform(() => uploadSource(projectId, file, payload, uploadController.current.signal), {
        upload: true
      });
    } else {
      await perform(() =>
        mutateSource(projectId, 'sources', 'POST', {
          ...metadata,
          entries: [creationEntry]
        })
      );
    }
  }

  async function saveEditor() {
    if (!editor || !source) return;
    if (editor.type === 'meta') {
      if (!editor.value.title.trim()) {
        setError(new Error('资料标题不能为空。'));
        return;
      }
      await perform(() =>
        changeSource(`sources/${source.id}`, 'PUT', {
          ...editor.value,
          expectedVersion: source.version
        })
      );
      return;
    }
    const problem = validateEntry(editor.value);
    if (problem) {
      setError(new Error(problem));
      return;
    }
    if (editor.type === 'add') {
      const result = await perform(() =>
        changeSource(`sources/${source.id}/entries`, 'POST', {
          expectedSourceVersion: source.version,
          entry: editor.value
        })
      );
      if (result) setActiveId(result.entries.at(-1)?.id);
    } else {
      await perform(() =>
        changeSource(`sources/${source.id}/entries/${active.id}`, 'PUT', {
          expectedSourceVersion: source.version,
          expectedVersion: active.version,
          entry: editor.value
        })
      );
    }
  }

  function beginEdit(type) {
    guardLocal(() => {
      const value =
        type === 'meta'
          ? {
              title: source.title,
              description: source.description || '',
              visibility: source.visibility
            }
          : type === 'add'
            ? blankEntry(source.kind)
            : entryDraft(active);
      setEditor({
        type,
        value,
        baseline: type === 'add' ? '' : JSON.stringify(value)
      });
    });
  }

  function confirmAction(title, action, content) {
    guardLocal(() =>
      Modal.confirm({
        title,
        content,
        okText: '确认',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: () => perform(action)
      })
    );
  }

  async function preparePublish() {
    const entries = source.entries.filter((item) => selected.includes(item.id));
    if (!entries.length || entries.some(publicationError)) return;
    const preview = await perform(
      async () => {
        const old =
          source.replacementOfId && !source.confirmedAt
            ? await getSource(projectId, source.replacementOfId)
            : null;
        const impact = await getSourceImpact(projectId, old?.id || source.id);
        assertImpactVersion(impact, old?.version || source.version);
        return { entries, old, impact };
      },
      { adoptResult: false }
    );
    if (preview) setPublishPreview(preview);
  }

  async function publish() {
    const result = await perform(() =>
      mutateSource(projectId, `sources/${source.id}/publish`, 'POST', {
        expectedVersion: source.version,
        acknowledgedProjectIds: publishPreview.impact.projectIds,
        selectedEntries: publishPreview.entries.map((item) => ({
          id: item.id,
          expectedVersion: item.version
        })),
        ...(publishPreview.old
          ? { expectedReplacedVersion: publishPreview.impact.sourceVersion }
          : {}),
        ...(operatorName.trim() ? { operatorName: operatorName.trim() } : {})
      })
    );
    if (result) setPublishPreview(null);
  }

  async function compareLatest() {
    const result = await perform(() => getSource(projectId, source.id), {
      adoptResult: false
    });
    if (result) setLatest(result);
  }

  const footer = creation ? (
    <Space wrap>
      <Button onClick={onClose}>取消</Button>
      <Button
        aria-label={creation === 'upload' ? '上传并预览草稿' : '保存草稿并预览'}
        type="primary"
        loading={Boolean(busy)}
        onClick={saveCreation}
      >
        {creation === 'upload' ? '上传并预览草稿' : '保存草稿并预览'}
      </Button>
    </Space>
  ) : (
    <Space wrap>
      <Button onClick={onClose}>关闭</Button>
      {!readOnly && source && (
        <>
          <Text type="secondary">已选 {selected.length} 章</Text>
          <Button
            aria-label="发布所选章节"
            type="primary"
            disabled={dirty || !selected.length || Boolean(busy)}
            loading={Boolean(busy)}
            onClick={preparePublish}
          >
            发布所选章节
          </Button>
        </>
      )}
    </Space>
  );

  return (
    <Drawer
      open
      title={
        creation
          ? replacement
            ? '替换资料 · 先保存新草稿'
            : creation === 'upload'
              ? '上传项目资料'
              : '新建项目资料'
          : '资料详情'
      }
      size={960}
      className="memory-source-drawer"
      onClose={onClose}
      footer={footer}
      mask={{ closable: !busy }}
      keyboard={!busy}
    >
      <Steps
        size="small"
        current={creation ? 0 : 1}
        items={[{ title: '选择资料 / 录入' }, { title: '预览并确认发布' }]}
      />
      <Paragraph type="secondary" className="memory-top-space">
        {initial.library ? '公共资料，无归属项目' : ownerOptions ? `归属项目：${projectId ? projectLabel(projectId) : '待选择'}` : `查看项目：${projectName}`} · 保存草稿或发布资料均不会立即触发审查。
      </Paragraph>
      {error && (
        <Alert
          type="error"
          showIcon
          title={error.status === 409 ? '版本或发布条件冲突，本地输入已保留' : '操作未完成'}
          description={DOCUMENT_ERRORS[error.code] || error.message}
          action={
            source && error.status === 409 ? (
              <Button onClick={compareLatest} disabled={Boolean(busy)}>
                查看最新版本
              </Button>
            ) : !source && !creation ? (
              <Button onClick={() => setRetry((value) => value + 1)}>重试</Button>
            ) : undefined
          }
        />
      )}
      {latest && (
        <Alert
          className="memory-top-space"
          type="warning"
          title={`服务端最新资料：${latest.title} · v${latest.version}`}
          description={
            <>
              <Paragraph>
                当前编辑内容仍保留在下方。请对照后明确选择是否采用最新版本号重试。
              </Paragraph>
              <details>
                <summary>查看服务端完整章节</summary>
                {latest.entries.map((item) => (
                  <div key={item.id}>
                    <Text strong>
                      {item.heading} · v{item.version}
                    </Text>
                    <pre className="memory-plain-text">{item.content}</pre>
                  </div>
                ))}
              </details>
              <Button
                className="memory-top-space"
                disabled={
                  Boolean(busy) ||
                  (editor?.type === 'entry' && !latest.entries.some((item) => item.id === activeId))
                }
                onClick={() =>
                  Modal.confirm({
                    title: '确认对比后，采用最新版本号？',
                    content: '保留本地编辑；下一次保存将基于服务端最新版本。',
                    okText: '保留草稿并采用最新版本',
                    cancelText: '继续对比',
                    onOk: () => {
                      setSource(latest);
                      setLatest(null);
                      setError(null);
                    }
                  })
                }
              >
                保留编辑并采用最新版本号
              </Button>
            </>
          }
        />
      )}
      <Spin spinning={loading}>
        {creation ? (
          <div className="memory-top-space">
            {replacement && (
              <Alert
                type="info"
                showIcon
                title={`替换「${replacement.title}」v${replacement.version}`}
                description="新资料未发布前旧资料继续有效。首次发布会重新读取旧版本并由你确认。"
              />
            )}
            <Form layout="vertical" disabled={Boolean(busy)}>
              {ownerOptions && (
                <Form.Item label="归属项目" required>
                  <Select
                    aria-label="归属项目"
                    value={projectId || undefined}
                    disabled={Boolean(busy) || Boolean(replacement)}
                    showSearch={{ filterOption: false, onSearch: onOwnerSearch }}
                    loading={ownerLoading}
                    options={projectId && !ownerOptions.some((item) => item.value === projectId)
                      ? [{ value: projectId, label: projectLabel(projectId) }, ...ownerOptions] : ownerOptions}
                    placeholder="搜索并选择归属项目"
                    onChange={(value) => { setSelectedOwner(value); setTouched(true); }}
                  />
                  <Text type="secondary">创建后默认添加到归属项目；发布及开启记忆后，仍需按本次变更匹配。</Text>
                </Form.Item>
              )}
              <Form.Item label="资料类型">
                <Select
                  aria-label="资料类型"
                  disabled={Boolean(replacement) || Boolean(busy)}
                  options={KIND_OPTIONS}
                  value={metadata.kind}
                  onChange={(kind) => {
                    setMetadata((current) => ({ ...current, kind }));
                    const problem = file && uploadProblem(file, kind);
                    setError(problem ? new Error(problem) : null);
                    setCreationEntry((current) => ({
                      ...current,
                      content: current.content || blankEntry(kind).content,
                      loadMode: allowsCore(kind) ? current.loadMode : 'ON_DEMAND'
                    }));
                    setTouched(true);
                  }}
                />
              </Form.Item>
              <Form.Item label="资料标题" required={creation === 'manual'}>
                <Input
                  aria-label="资料标题"
                  maxLength={255}
                  value={metadata.title}
                  placeholder={
                    creation === 'upload' ? '留空采用 Skill 名称或文件名' : '例如：订单服务缓存约定'
                  }
                  onChange={(event) => {
                    setMetadata((current) => ({
                      ...current,
                      title: event.target.value
                    }));
                    setTouched(true);
                  }}
                />
              </Form.Item>
              <Form.Item label="简介">
                <Input.TextArea
                  aria-label="资料简介"
                  maxLength={4000}
                  value={metadata.description}
                  onChange={(event) => {
                    setMetadata((current) => ({
                      ...current,
                      description: event.target.value
                    }));
                    setTouched(true);
                  }}
                />
              </Form.Item>
              {creation === 'upload' && (
                <Form.Item
                  label="原文件"
                  required
                  extra={
                    metadata.kind === 'SKILL'
                      ? '仅支持 UTF-8 Markdown（.md），单文件不超过 1 MiB。'
                      : '每次选择一个文件：UTF-8 .md / .txt 不超过 1 MiB；.docx / 文本 .pdf 不超过 5 MiB。PDF 最多 100 页，不支持扫描件 OCR、旧 .doc、图片或压缩包。'
                  }
                >
                  <Upload
                    accept={metadata.kind === 'SKILL' ? '.md' : '.md,.txt,.docx,.pdf'}
                    maxCount={1}
                    fileList={
                      file
                        ? [
                            {
                              uid: 'memory-file',
                              name: file.name,
                              status: 'done',
                              originFileObj: file
                            }
                          ]
                        : []
                    }
                    beforeUpload={(next) => {
                      const problem = uploadProblem(next, metadata.kind);
                      if (problem) {
                        setError(new Error(problem));
                        return Upload.LIST_IGNORE;
                      }
                      setFile(next);
                      setError(null);
                      setTouched(true);
                      return false;
                    }}
                    onRemove={() => {
                      setFile(null);
                      setError(null);
                      setTouched(true);
                    }}
                    disabled={Boolean(busy)}
                  >
                    <Button aria-label="选择文件" icon={<UploadOutlined />}>
                      选择文件
                    </Button>
                  </Upload>
                  <Paragraph type="secondary" className="memory-top-space">
                    上传后请对照原件核对章节、适用条件和解析诊断，再选择章节发布；超长章节需人工拆分。多份规范、Skill 和案例可分别添加，按项目范围共同使用。
                  </Paragraph>
                </Form.Item>
              )}
            </Form>
            {metadata.kind === 'SKILL' && (
              <Alert
                type="info"
                showIcon
                title="Skill 仅导入审查文本；脚本、工具声明和权限均不执行。"
              />
            )}
            <MemoryEntryFields
              value={creationEntry}
              onChange={(next) => {
                setCreationEntry(next);
                setTouched(true);
              }}
              kind={metadata.kind}
              content={creation === 'manual'}
              disabled={Boolean(busy)}
            />
          </div>
        ) : source ? (
          <>
            <div className="memory-detail-header memory-top-space">
              <div>
                <Title level={4}>{source.title}</Title>
                <Space wrap>
                  <Tag color={stateColor(source.state)}>{STATE_LABELS[source.state]}</Tag>
                  <Tag>{labelFor(KIND_OPTIONS, source.kind)}</Tag>
                  <Tag>{source.visibility === 'SHARED' ? '共享资料' : '项目私有'}</Tag>
                  <Text type="secondary">
                    来源 v{source.version} · {ORIGIN_LABELS[source.origin]}
                  </Text>
                </Space>
              </div>
              <Space wrap>
                {source.canDownloadOriginal && (
                  <Button
                    aria-label="下载原件"
                    icon={<DownloadOutlined />}
                    disabled={Boolean(busy)}
                    onClick={() =>
                      perform(() => downloadOriginal(projectId, source, initial.library), {
                        adoptResult: false
                      })
                    }
                  >
                    下载原件
                  </Button>
                )}
                {!readOnly && (
                  <>
                    <Button disabled={Boolean(busy)} onClick={() => beginEdit('meta')}>
                      编辑资料信息
                    </Button>
                    <Button
                      disabled={Boolean(busy)}
                      onClick={() =>
                        guardLocal(() => {
                          setReplacement(source);
                          setMetadata({
                            kind: source.kind,
                            title: source.title,
                            description: source.description || ''
                          });
                          setCreationEntry(blankEntry(source.kind));
                          setFile(null);
                          setTouched(false);
                          setEditor(null);
                          setCreation('upload');
                        })
                      }
                    >
                      替换文件
                    </Button>
                    {source.state === 'PUBLISHED' && (
                      <Button
                        disabled={Boolean(busy)}
                        onClick={() =>
                          confirmAction(
                            '停用资料并影响全部使用项目？',
                            () =>
                              changeSource(`sources/${source.id}/state`, 'PUT', {
                                state: 'DISABLED',
                                expectedVersion: source.version
                              }),
                            '所有使用项目均无法在后续审查中检索这份资料；历史任务不变。'
                          )
                        }
                      >
                        停用资料
                      </Button>
                    )}
                    <Button
                      danger
                      disabled={Boolean(busy)}
                      onClick={() =>
                        confirmAction(
                          '删除资料并影响全部使用项目？',
                          () =>
                            changeSource(
                              `sources/${source.id}?expectedVersion=${source.version}`,
                              'DELETE'
                            ),
                          '影响全部使用项目，资料仅保留用于追溯，当前没有恢复入口。'
                        )
                      }
                    >
                      删除资料
                    </Button>
                  </>
                )}
              </Space>
            </div>
            <Paragraph>{source.description || '未填写简介'}</Paragraph>
            <Paragraph type="secondary">
              {source.projectId == null ? '公共资料，无默认项目关联' : `归属项目：${projectLabel(source.projectId)}`} · {ownerOptions ? '归属项目关联' : '本项目关联'}：
              {source.binding?.state === 'ACTIVE' ? '已关联' : '已解除 / 未关联'} · 范围：
              {source.binding?.targetType
                ? labelFor(TARGET_TYPE_OPTIONS, source.binding.targetType)
                : '所有端'}{' '}
              / {source.binding?.pathGlobs?.join('、') || '所有路径'}
            </Paragraph>
            <Space wrap className="memory-top-space">
              <Button disabled={Boolean(busy)} onClick={() => onManageBinding(source)}>
                {ownerOptions ? '管理使用项目' : '项目使用范围'}
              </Button>
              {!readOnly && (
                <Button
                  disabled={Boolean(busy)}
                  onClick={async () => {
                    const impact = await perform(() => getSourceImpact(projectId, source.id), {
                      adoptResult: false
                    });
                    if (impact) setImpactView(impact);
                  }}
                >
                  查看影响项目
                </Button>
              )}
            </Space>
            {impactView && (
              <Alert
                className="memory-top-space"
                type="info"
                title={`来源 v${impactView.sourceVersion} 的影响预览`}
                description={impactContent(impactView)}
              />
            )}
            {source.hasOriginal && !source.canDownloadOriginal && (
              <Paragraph type="secondary">原件包含未发布章节，当前不可下载。</Paragraph>
            )}
            {readOnly && (
              <Alert
                type="info"
                title={
                  source.origin === 'FEEDBACK'
                    ? '反馈来源只读，通过来源反馈的专用确认流程维护。'
                    : source.state === 'DELETED'
                      ? '资料已删除，只保留追溯信息。'
                      : source.projectId == null && initial.library
                        ? '公共资料暂为只读，独立维护入口将在后续阶段开放。'
                        : '引用资料只读，正文由维护项目统一管理。'
                }
              />
            )}
            {source.state === 'DISABLED' && (
              <Alert type="warning" title="当前资料已停用。重新发布只恢复本次明确勾选的章节。" />
            )}
            {Boolean(source.parseWarnings?.length) && (
              <details
                className="memory-parse-diagnostics memory-top-space"
                open={source.parserVersion === 'docx-pdf-v1'}
              >
                <summary>查看解析诊断（{source.parseWarnings.length} 条）</summary>
                <Paragraph type="secondary">请对照原件确认提取完整性，诊断不代表内容已经发布。</Paragraph>
                <div className="memory-parse-diagnostics-list">
                  {source.parseWarnings.map((warning, index) => (
                    <Alert key={index} type="warning" title={warning} />
                  ))}
                </div>
              </details>
            )}
            <Descriptions
              size="small"
              column={1}
              className="memory-top-space"
              items={[
                {
                  key: 'file',
                  label: '原件 / 解析版本',
                  children: `${source.originalFilename || '无原件'} / ${source.parserVersion || '手工录入'}`
                },
                {
                  key: 'confirmation',
                  label: '发布确认',
                  children: source.confirmedAt
                    ? `${source.confirmedBy || '未记录身份'} · ${source.confirmedAt}`
                    : '尚未发布确认'
                },
                ...(source.sourceFeedbackId
                  ? [
                      {
                        key: 'feedback',
                        label: '来源反馈',
                        children: <Button type="link" onClick={() => onViewFeedback?.(source.sourceFeedbackId)}>
                          查看来源反馈 #{source.sourceFeedbackId}
                        </Button>
                      }
                    ]
                  : []),
                ...(source.legacyPolicyIds?.length
                  ? [
                      {
                        key: 'legacy',
                        label: '同源旧策略',
                        children: source.legacyPolicyIds.map((id) => `#${id}`).join('、')
                      }
                    ]
                  : [])
              ]}
            />
            <Divider />
            {editor?.type === 'meta' ? (
              <Form layout="vertical">
                <Form.Item label="资料标题" required>
                  <Input
                    aria-label="编辑资料标题"
                    maxLength={255}
                    disabled={Boolean(busy)}
                    value={editor.value.title}
                    onChange={(event) =>
                      setEditor((current) => ({
                        ...current,
                        value: { ...current.value, title: event.target.value }
                      }))
                    }
                  />
                </Form.Item>
                <Form.Item label="简介">
                  <Input.TextArea
                    aria-label="编辑资料简介"
                    maxLength={4000}
                    disabled={Boolean(busy)}
                    value={editor.value.description}
                    onChange={(event) =>
                      setEditor((current) => ({
                        ...current,
                        value: {
                          ...current.value,
                          description: event.target.value
                        }
                      }))
                    }
                  />
                </Form.Item>
                {['STANDARD', 'ARCHITECTURE', 'SKILL'].includes(source.kind) && (
                  <Form.Item
                    label="共享范围"
                    extra="仅已发布共享资料进入共享目录；存在其他 ACTIVE 引用时不能改回私有。"
                  >
                    <Select
                      aria-label="共享范围"
                      value={editor.value.visibility}
                      disabled={Boolean(busy)}
                      options={[
                        { value: 'PROJECT', label: '项目私有' },
                        { value: 'SHARED', label: '共享给其他项目选用' }
                      ]}
                      onChange={(visibility) =>
                        setEditor((current) => ({
                          ...current,
                          value: { ...current.value, visibility }
                        }))
                      }
                    />
                  </Form.Item>
                )}
                <Button
                  aria-label="保存资料信息"
                  type="primary"
                  loading={Boolean(busy)}
                  onClick={saveEditor}
                >
                  保存资料信息
                </Button>
                <Button onClick={() => guardLocal(() => setEditor(null))}>取消编辑</Button>
              </Form>
            ) : (
              <div className="memory-chapter-layout">
                <div className="memory-chapters">
                  <Text strong>
                    章节 · {source.entries.filter((item) => item.state === 'ACTIVE').length}/
                    {source.entries.length} 已发布
                  </Text>
                  {source.entries.map((item) => (
                    <div
                      className={`memory-chapter ${activeId === item.id ? 'is-active' : ''}`}
                      key={item.id}
                    >
                      {!readOnly && (
                        <Checkbox
                          aria-label={`发布章节：${item.heading}`}
                          checked={selected.includes(item.id)}
                          disabled={Boolean(busy) || Boolean(publicationError(item))}
                          onChange={(event) =>
                            setSelected((current) =>
                              event.target.checked
                                ? [...current, item.id]
                                : current.filter((id) => id !== item.id)
                            )
                          }
                        />
                      )}
                      <button
                        type="button"
                        disabled={Boolean(busy)}
                        onClick={() =>
                          guardLocal(() => {
                            setEditor(null);
                            setActiveId(item.id);
                          })
                        }
                      >
                        <strong>{item.heading}</strong>
                        <span>
                          <Tag color={stateColor(item.state)}>{STATE_LABELS[item.state]}</Tag>
                          {bytes(item.content)} 字节
                        </span>
                        {publicationError(item) && (
                          <Text type="danger">{publicationError(item)}</Text>
                        )}
                      </button>
                    </div>
                  ))}
                  {!readOnly && (
                    <Button
                      aria-label="新增 / 拆分章节"
                      className="memory-top-space"
                      icon={<PlusOutlined />}
                      disabled={Boolean(busy) || source.entries.length >= 200}
                      onClick={() => beginEdit('add')}
                    >
                      新增 / 拆分章节
                    </Button>
                  )}
                </div>
                <div className="memory-chapter-body">
                  {editor && ['entry', 'add'].includes(editor.type) ? (
                    <>
                      <Title level={5}>{editor.type === 'add' ? '新增草稿章节' : '编辑章节'}</Title>
                      {active?.state === 'ACTIVE' && editor.type === 'entry' && (
                        <Alert
                          type="warning"
                          title="保存后本章节转回草稿，重新发布后才参与新检索。"
                        />
                      )}
                      <MemoryEntryFields
                        value={editor.value}
                        kind={source.kind}
                        disabled={Boolean(busy)}
                        onChange={(value) => setEditor((current) => ({ ...current, value }))}
                      />
                      <Space wrap>
                        <Button
                          aria-label="保存章节草稿"
                          type="primary"
                          loading={Boolean(busy)}
                          onClick={saveEditor}
                        >
                          保存章节草稿
                        </Button>
                        <Button
                          disabled={Boolean(busy)}
                          onClick={() => guardLocal(() => setEditor(null))}
                        >
                          取消编辑
                        </Button>
                      </Space>
                    </>
                  ) : active ? (
                    <>
                      <Title level={5}>{active.heading}</Title>
                      <Space wrap>
                        <Tag>
                          {active.targetType
                            ? labelFor(TARGET_TYPE_OPTIONS, active.targetType)
                            : '本项目所有端'}
                        </Tag>
                        <Tag>{active.issueType || '不限问题'}</Tag>
                        <Tag>{active.loadMode === 'CORE' ? '核心约定' : '按需背景'}</Tag>
                        <Text type="secondary">章节 v{active.version}</Text>
                      </Space>
                      <Paragraph type="secondary" className="memory-top-space">
                        路径：{active.pathGlobs.join('、') || '整个项目'}
                        <br />
                        关键词：{active.keywords.join('、') || '无'}
                      </Paragraph>
                      {publicationError(active) && (
                        <Alert type="error" title={publicationError(active)} />
                      )}
                      <pre className="memory-plain-text">{active.content}</pre>
                      {!readOnly && (
                        <Space wrap>
                          <Button disabled={Boolean(busy)} onClick={() => beginEdit('entry')}>
                            编辑章节
                          </Button>
                          {active.state !== 'DISABLED' && (
                            <Button
                              disabled={Boolean(busy)}
                              onClick={() =>
                                confirmAction('停用本章节？', () =>
                                  changeSource(`sources/${source.id}/entries/${active.id}`, 'PUT', {
                                    state: 'DISABLED',
                                    expectedSourceVersion: source.version,
                                    expectedVersion: active.version
                                  })
                                )
                              }
                            >
                              停用章节
                            </Button>
                          )}
                        </Space>
                      )}
                    </>
                  ) : (
                    <Empty description="暂无章节，可新增草稿" />
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          !loading && <Empty description="资料暂不可用" />
        )}
      </Spin>
      <Modal
        open={Boolean(publishPreview)}
        title="确认发布所选章节"
        okText="确认发布资料"
        okButtonProps={{ 'aria-label': '确认发布资料' }}
        cancelText="返回预览"
        confirmLoading={Boolean(busy)}
        onOk={publish}
        onCancel={() => {
          if (!busy) setPublishPreview(null);
        }}
        mask={{ closable: !busy }}
        keyboard={!busy}
      >
        {publishPreview && (
          <>
            <Paragraph>
              项目：{projectName} · {publishPreview.entries.length} 章 · 选中正文{' '}
              {publishPreview.entries.reduce((total, item) => total + bytes(item.content), 0)} UTF-8
              字节
            </Paragraph>
            <Alert
              type="info"
              title="正文大小不等于项目 CORE 总占用，最终预算由服务端校验。仅项目开启记忆且范围、预算匹配时，才会用于后续 Agent Review。"
            />
            {impactContent(publishPreview.impact)}
            {publishPreview.entries.map((item) => (
              <Paragraph key={item.id}>
                {item.heading} ·{' '}
                {item.targetType ? labelFor(TARGET_TYPE_OPTIONS, item.targetType) : '本项目所有端'}{' '}
                · {item.pathGlobs.join('、') || '整个项目'} ·{' '}
                {item.loadMode === 'CORE' ? '核心约定' : '按需背景'}
              </Paragraph>
            ))}
            {publishPreview.old && (
              <Alert
                type="warning"
                title={`发布后停用旧资料「${publishPreview.old.title}」v${publishPreview.old.version}`}
                description={
                  <>
                    <Paragraph>
                      {replacement && replacement.version !== publishPreview.old.version
                        ? '旧资料自上传后已变化，请核对当前版本后再确认替换。'
                        : '请确认替换当前旧版本；期间再次变化会返回版本冲突。'}
                    </Paragraph>
                    新资料继承旧资料的共享标识、全部项目关联、端/路径范围及解除状态，不恢复已解除项目。
                  </>
                }
              />
            )}
            <Form layout="vertical">
              <Form.Item label="操作人（选填，填报身份未经验证）">
                <Input
                  aria-label="操作人"
                  maxLength={96}
                  value={operatorName}
                  onChange={(event) => setOperatorName(event.target.value)}
                  disabled={Boolean(busy)}
                />
              </Form.Item>
            </Form>
            {error && <Alert type="error" title={error.message} />}
          </>
        )}
      </Modal>
    </Drawer>
  );
}
