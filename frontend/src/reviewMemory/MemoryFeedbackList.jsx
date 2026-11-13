import { useEffect, useState } from 'react';
import { Alert, Button, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { listGlobalMemoryFeedbacks, listMemoryFeedbacks, withdrawFeedback } from './api.js';
import { FEEDBACK_STATUS_OPTIONS, memoryFeedbackState } from './feedbackModel.js';
import { labelFor, TARGET_TYPE_OPTIONS } from './model.js';

export default function MemoryFeedbackList({ projectId, refresh, onOpen, globalView = false,
  projectOptions = [], projectLoading, onProjectSearch, projectLabel = (id) => `项目 #${id}` }) {
  const [filters, setFilters] = useState({ projectId: projectId || '', targetType: '', keyword: '', status: '', pageNo: 1, pageSize: 20 });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [withdrawing, setWithdrawing] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    setPage({ items: [], total: 0 }); setLoading(true); setError(null);
    const request = globalView ? listGlobalMemoryFeedbacks(filters, controller.signal)
      : listMemoryFeedbacks(projectId, { status: filters.status, pageNo: filters.pageNo, pageSize: filters.pageSize }, controller.signal);
    request
      .then((data) => { if (!controller.signal.aborted) setPage(data); })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, globalView, filters, refresh, retry]);
  const filter = (patch) => setFilters((current) => ({ ...current, ...patch, pageNo: 1 }));
  const withdraw = (row) => Modal.confirm({
    title: '撤回此误报标记？',
    content: `反馈 #${row.id} 将变为已撤回 / 忽略，同源案例会停用，在途旧回写会取消；不修改原 AI 结论或历史审查背景。`,
    okText: '确认撤回', cancelText: '取消', okButtonProps: { danger: true },
    onOk: async () => {
      setWithdrawing(row.id); setError(null);
      try { await withdrawFeedback(row.id); setRetry((value) => value + 1); }
      catch (err) { setError(err.message); }
      finally { setWithdrawing(null); }
    }
  });
  return (
    <>
      <Alert type="info" showIcon title={globalView ? '人工误报打标池' : '本项目人工误报反馈'}
        description={globalView
          ? '汇总各项目 AI finding 的误报标记。有效反馈不等于已沉淀案例；任务主端来自历史任务，未记录时不推断，多端任务不代表具体问题归属。完整说明与证据请打开详情核对。'
          : '只收集 AI finding 反馈。保存标记不会直接生效；已沉淀、已撤回及失败记录也保留在列表中，便于追溯。'} />
      {globalView && <div className="memory-simple-filters memory-top-space">
        <label><Typography.Text>项目</Typography.Text><Select aria-label="反馈项目筛选" allowClear placeholder="全部项目" value={filters.projectId || undefined}
          showSearch={{ filterOption: false, onSearch: onProjectSearch }} loading={projectLoading}
          options={filters.projectId && !projectOptions.some((item) => item.value === filters.projectId)
            ? [{ value: filters.projectId, label: projectLabel(filters.projectId) }, ...projectOptions] : projectOptions}
          onChange={(project) => filter({ projectId: project || '' })} /></label>
        <label><Typography.Text>任务主端</Typography.Text><Select aria-label="反馈任务主端筛选" allowClear placeholder="全部任务主端" value={filters.targetType || undefined}
          options={TARGET_TYPE_OPTIONS} onChange={(targetType) => filter({ targetType: targetType || '' })} /></label>
        <label><Typography.Text>反馈状态</Typography.Text><Select aria-label="反馈状态筛选" allowClear placeholder="全部反馈状态" options={FEEDBACK_STATUS_OPTIONS}
          value={filters.status || undefined} onChange={(status) => filter({ status: status || '' })} /></label>
        <label><Typography.Text>关键词</Typography.Text><Input.Search aria-label="反馈关键词" placeholder="原问题 / 人工原因" value={search} maxLength={128} allowClear
          onChange={(event) => { setSearch(event.target.value); if (!event.target.value) filter({ keyword: '' }); }}
          onSearch={(keyword) => filter({ keyword: keyword.trim() })} /></label>
      </div>}
      <div className="memory-toolbar memory-top-space">
        {!globalView && <Select aria-label="反馈状态筛选" allowClear placeholder="全部反馈状态" options={FEEDBACK_STATUS_OPTIONS}
          value={filters.status || undefined} onChange={(status) => filter({ status: status || '' })} />}
        <Button aria-label="刷新反馈" onClick={() => setRetry((value) => value + 1)} loading={loading}>刷新反馈</Button>
      </div>
      {error && <Alert type="error" title={`反馈加载失败：${error}`} action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} />}
      <Table rowKey="id" dataSource={page.items} loading={loading} scroll={{ x: 1000 }}
        locale={{ emptyText: error ? '加载失败，请重试' : filters.status || filters.keyword || filters.targetType || (globalView && filters.projectId) ? '没有符合筛选条件的反馈' : '暂无误报反馈，可从任务详情的具体 finding 标记' }}
        columns={[
          ...(globalView ? [{ title: '来源项目 / 任务主端', width: 200, render: (_, row) => <>
            <div>{projectLabel(String(row.projectId))}</div>
            <Tag>{row.targetType ? labelFor(TARGET_TYPE_OPTIONS, row.targetType) : '未记录'}</Tag>
          </> }] : []),
          { title: '原结论', dataIndex: 'riskTitle', width: 260, render: (value, row) => <><Typography.Text>{value || '未命名问题'}</Typography.Text><div>反馈 #{row.id}</div></> },
          { title: '人工说明 / 证据', dataIndex: 'reasonText', width: 260, render: (value) => <div className="memory-feedback-summary">{value || '尚未填写，整理案例时需补充证据'}</div> },
          { title: '反馈状态', dataIndex: 'status', width: 150, render: (value) => <Tag>{labelFor(FEEDBACK_STATUS_OPTIONS, value)}</Tag> },
          { title: '记忆状态', width: 170, render: (_, row) => <Tag>{memoryFeedbackState(row)}</Tag> },
          ...(globalView ? [{ title: '打标时间', dataIndex: 'createdAt', width: 180,
            render: (value) => value ? value.replace('T', ' ') : '未记录' }] : []),
          { title: '操作', width: 220, render: (_, row) => <Space wrap>
            <Button onClick={() => onOpen(row.id, row.projectId)}>{row.memorySourceId ? '查看案例 / 反馈' : '整理 / 查看反馈'}</Button>
            <a href={`/tasks/${row.taskId}`} target="_blank" rel="noreferrer">任务 #{row.taskId}</a>
            {globalView && !['IGNORED', 'CONVERTED'].includes(row.status) && <Button danger disabled={withdrawing !== null}
              onClick={() => withdraw(row)}>撤回误报</Button>}
          </Space> }
        ]}
        pagination={{ current: filters.pageNo, pageSize: filters.pageSize, total: page.total, showSizeChanger: true,
          pageSizeOptions: [20, 50, 100], showTotal: (total) => `共 ${total} 条反馈`,
          onChange: (pageNo, pageSize) => setFilters((current) => ({ ...current, pageNo, pageSize })) }} />
    </>
  );
}
