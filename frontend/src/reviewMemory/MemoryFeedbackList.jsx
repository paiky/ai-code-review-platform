import { useEffect, useState } from 'react';
import { Alert, Button, Select, Space, Table, Tag, Typography } from 'antd';
import { listMemoryFeedbacks } from './api.js';
import { FEEDBACK_STATUS_OPTIONS, memoryFeedbackState } from './feedbackModel.js';
import { labelFor } from './model.js';

export default function MemoryFeedbackList({ projectId, refresh, onOpen }) {
  const [filters, setFilters] = useState({ status: '', pageNo: 1, pageSize: 20 });
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setPage({ items: [], total: 0 }); setLoading(true); setError(null);
    listMemoryFeedbacks(projectId, filters, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setPage(data); })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, filters, refresh, retry]);
  return (
    <>
      <Alert type="info" showIcon title="本项目人工误报反馈"
        description="只收集 AI finding 反馈。保存标记不会直接生效；已沉淀、已撤回及失败记录也保留在列表中，便于追溯。" />
      <div className="memory-toolbar memory-top-space">
        <Select aria-label="反馈状态筛选" allowClear placeholder="全部反馈状态" options={FEEDBACK_STATUS_OPTIONS}
          value={filters.status || undefined} onChange={(status) => setFilters((current) => ({ ...current, status: status || '', pageNo: 1 }))} />
        <Button onClick={() => setRetry((value) => value + 1)} loading={loading}>刷新反馈</Button>
      </div>
      {error && <Alert type="error" title={`反馈加载失败：${error}`} action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} />}
      <Table rowKey="id" dataSource={page.items} loading={loading} scroll={{ x: 1000 }}
        locale={{ emptyText: error ? '加载失败，请重试' : filters.status ? '没有符合筛选条件的反馈' : '暂无误报反馈，可从任务详情的具体 finding 标记' }}
        columns={[
          { title: '原结论', dataIndex: 'riskTitle', width: 260, render: (value, row) => <><Typography.Text>{value || '未命名问题'}</Typography.Text><div>反馈 #{row.id}</div></> },
          { title: '人工说明 / 证据', dataIndex: 'reasonText', width: 260, render: (value) => <div className="memory-feedback-summary">{value || '尚未填写，整理案例时需补充证据'}</div> },
          { title: '反馈状态', dataIndex: 'status', width: 150, render: (value) => <Tag>{labelFor(FEEDBACK_STATUS_OPTIONS, value)}</Tag> },
          { title: '记忆状态', width: 170, render: (_, row) => <Tag>{memoryFeedbackState(row)}</Tag> },
          { title: '操作', width: 220, render: (_, row) => <Space wrap>
            <Button onClick={() => onOpen(row.id)}>{row.memorySourceId ? '查看案例 / 反馈' : '整理 / 查看反馈'}</Button>
            <a href={`/tasks/${row.taskId}`} target="_blank" rel="noreferrer">任务 #{row.taskId}</a>
          </Space> }
        ]}
        pagination={{ current: filters.pageNo, pageSize: filters.pageSize, total: page.total, showSizeChanger: true,
          pageSizeOptions: [20, 50, 100], showTotal: (total) => `共 ${total} 条反馈`,
          onChange: (pageNo, pageSize) => setFilters((current) => ({ ...current, pageNo, pageSize })) }} />
    </>
  );
}
