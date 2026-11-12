import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography
} from 'antd';
import {
  downloadOriginal,
  getBinding,
  getSharedSource,
  listSharedSources,
  mutateSource
} from './api.js';
import { KIND_OPTIONS, labelFor, TARGET_TYPE_OPTIONS, validateEntry } from './model.js';

const { Paragraph, Text, Title } = Typography;
const draftFor = (binding) => ({
  targetType: binding?.targetType || null,
  pathGlobs: binding?.pathGlobs || []
});

export default function MemoryAssociationDrawer({
  projectId,
  projectName,
  initial,
  projectLabel,
  onClose,
  onDirtyChange,
  onBusyChange,
  onSaved
}) {
  const [filters, setFilters] = useState({
    kind: '',
    keyword: '',
    pageNo: 1,
    pageSize: 20
  });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState({ items: [], total: 0 });
  const [record, setRecord] = useState(initial.source || null);
  const [detail, setDetail] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [draft, setDraft] = useState(draftFor(initial.source?.binding));
  const [baseline, setBaseline] = useState(JSON.stringify(draftFor(initial.source?.binding)));
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [retry, setRetry] = useState(0);
  const mounted = useRef(true);
  const dirty = JSON.stringify(draft) !== baseline;
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    onBusyChange(busy ? 'save' : null);
  }, [busy, onBusyChange]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      onDirtyChange(false);
      onBusyChange(null);
    };
  }, [onDirtyChange, onBusyChange]);

  useEffect(() => {
    if (record) return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listSharedSources(filters, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setPage(next);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [record, filters, retry]);

  useEffect(() => {
    if (!record) return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setPreviewError(null);
    setDetail(null);
    setSnapshot(null);
    async function load() {
      try {
        // Only an explicit 404 means a first association. Network failures must not imply absence.
        let next;
        try {
          next = await getBinding(projectId, record.id, controller.signal);
        } catch (err) {
          if (err.status !== 404) throw err;
          const current = await getSharedSource(record.id, controller.signal);
          next = { sourceVersion: current.version, binding: null };
        }
        if (controller.signal.aborted) return;
        setSnapshot(next);
        if (!dirty) {
          const value = draftFor(next.binding);
          setDraft(value);
          setBaseline(JSON.stringify(value));
        }
        try {
          const current = await getSharedSource(record.id, controller.signal);
          if (!controller.signal.aborted) setDetail(current);
        } catch (err) {
          if (err.name !== 'AbortError') setPreviewError(err.message);
        }
      } catch (err) {
        if (err.name !== 'AbortError') setError(err);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
    // Retry explicitly retains local range input, and only refreshes server version tokens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record, projectId, retry]);

  function select(next) {
    const action = () => {
      const value = draftFor(next?.binding);
      setDraft(value);
      setBaseline(JSON.stringify(value));
      setRecord(next);
      setError(null);
    };
    if (dirty)
      Modal.confirm({
        title: '放弃未保存的关联范围？',
        okText: '放弃修改',
        cancelText: '继续编辑',
        onOk: action
      });
    else action();
  }

  async function save(state) {
    if (!snapshot || busy) return;
    const value = state === 'DISABLED' ? draftFor(snapshot.binding) : draft;
    const problem = validateEntry({
      ...value,
      heading: 'scope',
      content: 'scope',
      keywords: []
    });
    if (problem) {
      setError(new Error(problem));
      return;
    }
    setBusy(true);
    onBusyChange('save');
    setError(null);
    try {
      const next = await mutateSource(projectId, `sources/${record.id}/binding`, 'PUT', {
        ...value,
        state,
        expectedSourceVersion: snapshot.sourceVersion,
        expectedBindingVersion: snapshot.binding?.version || null
      });
      if (!mounted.current) return;
      setSnapshot(next);
      setDraft(value);
      setBaseline(JSON.stringify(value));
      onSaved();
    } catch (err) {
      if (mounted.current) setError(err);
    } finally {
      if (mounted.current) {
        setBusy(false);
        onBusyChange(null);
      }
    }
  }

  return (
    <Drawer
      open
      title={initial.mode === 'shared' ? '从共享库关联' : '本项目关联管理'}
      size={880}
      className="memory-source-drawer"
      onClose={onClose}
      mask={{ closable: !busy }}
      keyboard={!busy}
      footer={
        <Space wrap>
          <Button onClick={onClose}>关闭</Button>
          {record && initial.mode === 'shared' && (
            <Button disabled={busy || loading} onClick={() => select(null)}>
              返回共享目录
            </Button>
          )}
        </Space>
      }
    >
      <Paragraph>当前使用项目：{projectName}。本页只修改本项目的关联，不修改共享正文。</Paragraph>
      {error && (
        <Alert
          type="error"
          title={error.status === 409 ? '关联版本或预算冲突，输入已保留' : '操作未完成'}
          description={error.message}
          action={
            <Button
              disabled={busy || loading}
              onClick={() => {
                if (record)
                  Modal.confirm({
                    title: '保留输入并刷新关联版本？',
                    content: '请核对最新状态后再重试；不会自动重新提交。',
                    okText: '刷新版本',
                    cancelText: '取消',
                    onOk: () => setRetry((v) => v + 1)
                  });
                else setRetry((v) => v + 1);
              }}
            >
              重试 / 刷新版本
            </Button>
          }
        />
      )}
      <Spin spinning={loading}>
        {!record ? (
          <>
            <div className="memory-toolbar">
              <Select
                aria-label="共享资料类型"
                value={filters.kind || undefined}
                allowClear
                placeholder="全部共享类型"
                options={KIND_OPTIONS.filter((item) =>
                  ['STANDARD', 'ARCHITECTURE', 'SKILL'].includes(item.value)
                )}
                onChange={(kind) => setFilters((v) => ({ ...v, kind: kind || '', pageNo: 1 }))}
              />
              <Input.Search
                aria-label="搜索共享资料"
                value={search}
                maxLength={128}
                placeholder="搜索已发布标题或正文"
                onChange={(event) => setSearch(event.target.value)}
                onSearch={(keyword) =>
                  setFilters((v) => ({
                    ...v,
                    keyword: keyword.trim(),
                    pageNo: 1
                  }))
                }
              />
            </div>
            <Table
              rowKey="id"
              dataSource={page.items}
              loading={loading}
              scroll={{ x: 570 }}
              columns={[
                { title: '共享资料', dataIndex: 'title' },
                {
                  title: '类型',
                  dataIndex: 'kind',
                  render: (kind) => labelFor(KIND_OPTIONS, kind)
                },
                {
                  title: '维护项目',
                  dataIndex: 'projectId',
                  render: projectLabel
                },
                {
                  title: '操作',
                  render: (_, item) => <Button onClick={() => select(item)}>预览 / 关联</Button>
                }
              ]}
              locale={{
                emptyText: error ? '加载失败，请重试' : '暂无已发布共享资料'
              }}
              pagination={{
                current: filters.pageNo,
                pageSize: filters.pageSize,
                total: page.total,
                showSizeChanger: false,
                onChange: (pageNo) => setFilters((v) => ({ ...v, pageNo }))
              }}
            />
          </>
        ) : (
          <>
            <Title level={4}>{record.title}</Title>
            <Paragraph>
              维护项目：{projectLabel(record.projectId)} · 来源 v
              {snapshot?.sourceVersion || record.version}
            </Paragraph>
            <Tag color={snapshot?.binding?.state === 'ACTIVE' ? 'green' : 'default'}>
              {snapshot?.binding?.state === 'ACTIVE'
                ? '本项目已关联'
                : snapshot?.binding
                  ? '本项目已解除'
                  : '本项目尚未关联'}
            </Tag>
            {previewError && (
              <Alert
                className="memory-top-space"
                type="warning"
                title="共享正文不可预览"
                description={`${previewError}；已有关系仍可解除。私有自有资料请返回维护资料查看正文。`}
              />
            )}
            {snapshot && (
              <>
                <Alert
                  className="memory-top-space"
                  type="info"
                  title="关联范围与章节范围取交集；留空不限，“通用”是独立端。关联不会立即触发审查。"
                />
                <Form layout="vertical" disabled={busy || loading}>
                  <Form.Item label="本项目适用端">
                    <Select
                      aria-label="本项目适用端"
                      allowClear
                      value={draft.targetType || undefined}
                      placeholder="本项目所有端"
                      options={TARGET_TYPE_OPTIONS}
                      onChange={(targetType) =>
                        setDraft((v) => ({
                          ...v,
                          targetType: targetType || null
                        }))
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    label="本项目路径范围"
                    extra="每行一个相对 glob，最多 8 条；留空不限。"
                  >
                    <Input.TextArea
                      aria-label="本项目路径范围"
                      rows={3}
                      value={draft.pathGlobs.join('\n')}
                      onChange={(event) =>
                        setDraft((v) => ({
                          ...v,
                          pathGlobs: event.target.value ? event.target.value.split('\n') : []
                        }))
                      }
                    />
                  </Form.Item>
                  <Space wrap>
                    <Button
                      type="primary"
                      disabled={loading}
                      loading={busy}
                      onClick={() => save('ACTIVE')}
                    >
                      {snapshot.binding?.state === 'ACTIVE'
                        ? '保存本项目范围'
                        : snapshot.binding
                          ? '恢复本项目关联'
                          : '确认关联到本项目'}
                    </Button>
                    {snapshot.binding?.state === 'ACTIVE' && (
                      <Button
                        danger
                        disabled={busy || loading}
                        onClick={() =>
                          Modal.confirm({
                            title: '仅解除本项目关联？',
                            content:
                              '其他项目和共享资料保留；本地未保存范围将丢弃，恢复时使用已保存范围。',
                            okText: '解除本项目关联',
                            cancelText: '取消',
                            onOk: () => save('DISABLED')
                          })
                        }
                      >
                        解除本项目关联
                      </Button>
                    )}
                  </Space>
                </Form>
              </>
            )}
            {detail?.canDownloadOriginal && (
              <Button
                className="memory-top-space"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  onBusyChange('save');
                  try {
                    await downloadOriginal(null, detail);
                  } catch (err) {
                    if (mounted.current) setError(err);
                  } finally {
                    if (mounted.current) {
                      setBusy(false);
                      onBusyChange(null);
                    }
                  }
                }}
              >
                下载共享原件
              </Button>
            )}
            {detail?.hasOriginal && !detail.canDownloadOriginal && (
              <Paragraph type="secondary">原件包含未发布章节，当前不可下载。</Paragraph>
            )}
            {detail?.entries.map((entry) => (
              <div key={entry.id} className="memory-top-space">
                <Text strong>{entry.heading}</Text>
                <Paragraph type="secondary">
                  章节范围：
                  {entry.targetType
                    ? labelFor(TARGET_TYPE_OPTIONS, entry.targetType)
                    : '所有端'} · {entry.pathGlobs.join('、') || '所有路径'}
                </Paragraph>
                <pre className="memory-plain-text">{entry.content}</pre>
              </div>
            ))}
            {detail && !detail.entries.length && <Empty description="暂无已发布章节" />}
          </>
        )}
      </Spin>
    </Drawer>
  );
}
