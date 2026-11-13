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
  getSource,
  listSources,
  getSharedSource,
  listSharedSources,
  mutateSource
} from './api.js';
import { KIND_OPTIONS, labelFor, TARGET_TYPE_OPTIONS, STATE_LABELS, sourceUseProblem, validateEntry } from './model.js';

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
  onSaved,
  onBack
}) {
  const [filters, setFilters] = useState({
    kind: '',
    keyword: '',
    pageNo: 1,
    pageSize: 20
  });
  const [catalog, setCatalog] = useState('shared');
  const [conflict, setConflict] = useState(false);
  const [saved, setSaved] = useState(false);
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
    const request = catalog === 'owned'
      ? listSources(projectId, { ...filters, view: 'OWNED', state: 'PUBLISHED' }, controller.signal)
      : listSharedSources(filters, controller.signal);
    request
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
  }, [record, filters, retry, catalog, projectId]);

  useEffect(() => {
    if (!record) return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setPreviewError(null);
    setDetail(null);
    setSnapshot(null);
    setConflict(false);
    async function load() {
      try {
        // Only an explicit 404 means a first association. Network failures must not imply absence.
        let next;
        try {
          next = await getBinding(projectId, record.id, controller.signal);
        } catch (err) {
          if (err.status !== 404) throw err;
          const current = String(record.projectId) === String(projectId)
            ? await getSource(projectId, record.id, controller.signal)
            : await getSharedSource(record.id, controller.signal);
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
          const current = String(record.projectId) === String(projectId)
            ? await getSource(projectId, record.id, controller.signal)
            : await getSharedSource(record.id, controller.signal);
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
      setSaved(false);
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

  function requestRefresh() {
    if (busy || loading) return;
    if (!record) { setRetry((v) => v + 1); return; }
    Modal.confirm({
      title: '保留输入并刷新关联版本？',
      content: '请核对最新状态后再重试；不会自动重新提交。',
      okText: '刷新版本', cancelText: '取消', onOk: () => setRetry((v) => v + 1)
    });
  }

  async function save(state) {
    if (!snapshot || busy || loading || conflict) return;
    if (state === 'ACTIVE' && useProblem) return;
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
    setSaved(false);
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
      setDetail((current) => current ? { ...current, version: next.sourceVersion } : current);
      setSaved(true);
      setDraft(value);
      setBaseline(JSON.stringify(value));
      onSaved();
    } catch (err) {
      if (mounted.current) { setError(err); setConflict(err.status === 409); }
    } finally {
      if (mounted.current) {
        setBusy(false);
        onBusyChange(null);
      }
    }
  }

  const saveLabel = snapshot?.binding?.state === 'ACTIVE' ? '保存使用范围'
    : snapshot?.binding ? '恢复到该项目' : '添加到该项目';
  const useProblem = !detail || detail.id !== record?.id ? '资料当前不可引用，不能添加或恢复'
    : detail.version !== snapshot?.sourceVersion ? '资料版本已变化，请刷新版本后核对'
      : sourceUseProblem(detail, projectId, detail.entries.some((entry) => entry.state === 'ACTIVE'));

  return (
    <Drawer
      open
      title={initial.mode === 'candidates' ? '添加记忆资料' : '项目使用范围'}
      size="min(880px, 100vw)" styles={{ wrapper: { maxWidth: '100vw', minWidth: 0 } }}
      className="memory-source-drawer"
      onClose={onClose}
      mask={{ closable: !busy }}
      keyboard={!busy}
      footer={
        <Space wrap>
          <Button onClick={onClose}>关闭</Button>
          {onBack && <Button disabled={busy || loading} onClick={onBack}>返回使用项目</Button>}
          {record && initial.mode === 'candidates' && (
            <Button disabled={busy || loading} onClick={() => select(null)}>
              返回资料目录
            </Button>
          )}
        </Space>
      }
    >
      <Paragraph>使用项目：{projectName}。只修改该项目的使用范围，资料正文由归属项目维护。</Paragraph>
      {error && (
        <Alert
          type="error"
          title={error.status === 409 ? '关联版本或预算冲突，输入已保留' : '操作未完成'}
          description={error.message}
          action={
            <Button
              disabled={busy || loading}
              onClick={requestRefresh}
            >
              重试 / 刷新版本
            </Button>
          }
        />
      )}
      {dirty && <Tag color="gold">使用范围有未保存修改</Tag>}
      {saved && !dirty && <Alert type="success" title="本项目关系已保存；其他项目的已保存关系保留" />}
      <Spin spinning={loading}>
        {!record ? (
          <>
            <Select aria-label="资料目录" value={catalog} className="memory-top-space"
              options={[{ value: 'shared', label: '已发布共享资料' }, { value: 'owned', label: '本项目已发布资料' }]}
              onChange={(value) => { setCatalog(value); setFilters((v) => ({ ...v, kind: '', pageNo: 1 })); }} />
            <div className="memory-toolbar memory-top-space">
              <Select
                aria-label="共享资料类型"
                value={filters.kind || undefined}
                allowClear
                placeholder="全部共享类型"
                options={KIND_OPTIONS.filter((item) =>
                  catalog === 'owned' || ['STANDARD', 'ARCHITECTURE', 'SKILL'].includes(item.value)
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
                { title: '资料名称', dataIndex: 'title' },
                {
                  title: '类型',
                  dataIndex: 'kind',
                  render: (kind) => labelFor(KIND_OPTIONS, kind)
                },
                {
                  title: '归属项目',
                  dataIndex: 'projectId',
                  render: projectLabel
                },
                {
                  title: '操作',
                  render: (_, item) => <Button onClick={() => select(item)}>预览 / 添加</Button>
                }
              ]}
              locale={{
                emptyText: error ? '加载失败，请重试' : '暂无该目录的已发布资料'
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
            <Title level={4}>{detail?.title || record.title}</Title>
            <Tag>{STATE_LABELS[detail?.state || record.state]}</Tag>
            <Paragraph>
              归属项目：{projectLabel(record.projectId)} · 来源 v
              {snapshot?.sourceVersion || record.version}
            </Paragraph>
            <Tag color={snapshot?.binding?.state === 'ACTIVE' ? 'green' : 'default'}>
              {snapshot?.binding?.state === 'ACTIVE'
                ? '已添加'
                : snapshot?.binding
                  ? '已移除'
                  : '尚未添加'}
            </Tag>
            {previewError && (
              <Alert
                className="memory-top-space"
                type="warning"
                title="资料正文不可预览"
                description={`${previewError}；已有关系仍可移除，添加或恢复需先满足资料条件。`}
              />
            )}
            {snapshot && (
              <>
                {useProblem && <Alert type="warning" className="memory-top-space" title={useProblem} />}
                <Alert
                  className="memory-top-space"
                  type="info"
                  title="项目范围与章节范围取交集；实际按本次变更匹配。添加资料不会开启记忆或立即触发审查。"
                />
                <Button className="memory-top-space" disabled={busy || loading} onClick={requestRefresh}>刷新关联状态</Button>
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
                      aria-label={saveLabel}
                      disabled={loading || conflict || Boolean(useProblem)}
                      loading={busy}
                      onClick={() => save('ACTIVE')}
                    >
                      {saveLabel}
                    </Button>
                    {snapshot.binding?.state === 'ACTIVE' && (
                      <Button
                        danger
                        disabled={busy || loading || conflict}
                        onClick={() =>
                          Modal.confirm({
                            title: '仅从该项目移除？',
                            content:
                              '其他项目的关系和资料正文保留；本地未保存范围将丢弃，恢复时使用已保存范围。',
                            okText: '从该项目移除',
                            cancelText: '取消',
                            onOk: () => save('DISABLED')
                          })
                        }
                      >
                        从该项目移除
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
                    await downloadOriginal(String(record.projectId) === String(projectId) ? projectId : null, detail);
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
