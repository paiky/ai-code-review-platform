import { useEffect, useState } from 'react';
import { Alert, Button, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { listProjectBindings, mutateSource } from './api.js';
import { KIND_OPTIONS, labelFor, STATE_LABELS, TARGET_TYPE_OPTIONS, sourceUseProblem } from './model.js';

const { Text } = Typography;

export default function MemoryProjectBindings({ projectId, memoryEnabled, refresh, projectLabel, onOpen, onAdd, onBusyChange }) {
  const [filters, setFilters] = useState({ state: 'ACTIVE', pageNo: 1, pageSize: 20 });
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [removing, setRemoving] = useState(false);
  useEffect(() => {
    onBusyChange(removing ? 'save' : null);
    return () => onBusyChange(null);
  }, [removing, onBusyChange]);

  function remove(row) {
    Modal.confirm({
      title: '仅从该项目移除？',
      content: '资料正文和其他项目关联保留，只影响该项目后续审查；历史任务不变。',
      okText: '确认移除', cancelText: '取消', okButtonProps: { danger: true },
      onOk: async () => {
        setRemoving(true);
        setError(null);
        try {
          await mutateSource(projectId, `sources/${row.sourceId}/binding`, 'PUT', {
            expectedSourceVersion: row.source.version,
            expectedBindingVersion: row.binding.version,
            state: 'DISABLED', targetType: row.binding.targetType, pathGlobs: row.binding.pathGlobs
          });
          setRetry((value) => value + 1);
        } catch (err) {
          setError(err.status === 409 ? `关联或资料已变化，请刷新后核对再操作：${err.message}` : err.message);
        } finally {
          setRemoving(false);
        }
      }
    });
  }
  useEffect(() => {
    const controller = new AbortController();
    setPage({ items: [], total: 0 });
    setLoading(true);
    setError(null);
    listProjectBindings(projectId, filters, controller.signal).then((data) => {
      if (!controller.signal.aborted) setPage(data);
    }).catch((err) => {
      if (!controller.signal.aborted) setError(err.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [projectId, filters, refresh, retry]);

  return <>
    <div className="memory-toolbar memory-top-space">
      <Select aria-label="资料关系状态" value={filters.state}
        options={[{ value: 'ACTIVE', label: '已添加资料' }, { value: 'DISABLED', label: '已移除资料' }]}
        onChange={(state) => setFilters((v) => ({ ...v, state, pageNo: 1 }))} />
      <Button loading={loading} disabled={removing} onClick={() => setRetry((v) => v + 1)}>刷新关联</Button>
      <Button type="primary" disabled={removing} onClick={onAdd}>添加记忆资料</Button>
    </div>
    {error && <Alert type="error" title="项目关联操作未完成" description={error}
      action={<Button onClick={() => setRetry((v) => v + 1)}>重试</Button>} />}
    <Table rowKey="sourceId" loading={loading} dataSource={page.items} scroll={{ x: 1100 }}
      columns={[
        { title: '资料 / 来源', width: 250, render: (_, row) => <>
          <Text strong>{row.source?.title || `缺失资料 #${row.sourceId}`}</Text>
          {row.source && <div>{row.source.projectId == null ? '公共资料' : projectLabel(row.source.projectId)} · {labelFor(KIND_OPTIONS, row.source.kind)}</div>}
          {row.source?.origin === 'FEEDBACK' && <div>本项目案例 · 人工确认后自动关联</div>}
        </> },
        { title: '资料状态 / 关系', width: 170, render: (_, row) => <>
          <Tag>{row.source ? STATE_LABELS[row.source.state] : '资料缺失'}</Tag>
          <Tag>{row.binding.state === 'ACTIVE' ? '已添加' : '已移除'}</Tag>
        </> },
        { title: '该项目适用范围', width: 200, render: (_, row) => <>
          {row.binding.targetType ? labelFor(TARGET_TYPE_OPTIONS, row.binding.targetType) : '所有端'}
          <div>{row.binding.pathGlobs.join('、') || '所有路径'}</div>
        </> },
        { title: '审查背景状态', width: 250, render: (_, row) => {
          const problem = sourceUseProblem(row.source, projectId, row.hasActiveEntries);
          return <>
            {problem && <div>{problem}</div>}
            {memoryEnabled !== true && <div>{memoryEnabled === false ? '项目记忆关闭' : '项目记忆状态待确认'}</div>}
            {!problem && memoryEnabled === true && row.binding.state === 'ACTIVE' && <Text>按本次变更匹配</Text>}
            {row.binding.state !== 'ACTIVE' && <div>已移除，不参与后续检索</div>}
          </>;
        } },
        { title: '操作', width: 230, render: (_, row) => <Space wrap>
          <Button disabled={removing || !row.canReadSource || row.sourceMissing} onClick={() => onOpen({ mode: 'view', sourceId: row.sourceId })}>查看资料</Button>
          {row.binding.state === 'ACTIVE' && <Button danger disabled={removing || row.sourceMissing} onClick={() => remove(row)}>移除</Button>}
          <Button type="link" disabled={removing || row.sourceMissing} onClick={() => onOpen({ mode: 'binding', source: row.source })}>
            {row.binding.state === 'ACTIVE' ? '调整范围' : '查看 / 恢复'}
          </Button>
        </Space> }
      ]}
      locale={{ emptyText: error ? '加载失败，请重试' : '暂无该状态的资料，可添加记忆资料' }}
      pagination={{ current: filters.pageNo, pageSize: filters.pageSize, total: page.total, showSizeChanger: true,
        pageSizeOptions: [20, 50, 100], showTotal: (total) => `共 ${total} 份资料`,
        onChange: (pageNo, pageSize) => setFilters((v) => ({ ...v, pageNo, pageSize })) }} />
  </>;
}
