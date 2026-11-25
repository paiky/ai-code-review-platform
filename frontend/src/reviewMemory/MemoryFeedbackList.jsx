import { useEffect, useState } from 'react';
import { Alert, Button, Dropdown, Empty, Input, Modal, Pagination, Select, Space, Spin, Table, Tag, Typography } from 'antd';
import { EllipsisOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons';
import { listGlobalMemoryFeedbacks, listMemoryFeedbacks, withdrawFeedback } from './api.js';
import { FEEDBACK_STATUS_OPTIONS, isWritebackPending, memoryFeedbackState } from './feedbackModel.js';
import { labelFor, TARGET_TYPE_OPTIONS } from './model.js';

export default function MemoryFeedbackList({ projectId, refresh, onOpen, globalView = false,
  projectOptions = [], projectLoading, onProjectSearch, projectLabel = (id) => `项目 #${id}` }) {
  const [filters, setFilters] = useState({ projectId: projectId || '', targetType: '', keyword: '', status: '', pageNo: 1, pageSize: 20 });
  const [search, setSearch] = useState('');
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(globalView);
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
  const reload = () => setRetry((value) => value + 1);
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
  const statusFilter = <Select aria-label="反馈状态筛选" allowClear placeholder="全部反馈状态" options={FEEDBACK_STATUS_OPTIONS}
    value={filters.status || undefined} onChange={(status) => filter({ status: status || '' })} />;
  const filterCount = Number(Boolean(filters.projectId)) + Number(Boolean(filters.targetType));
  const emptyText = error ? '加载失败，请重试' : filters.status || filters.keyword || (globalView && filterCount)
    ? '没有符合筛选条件的反馈' : '暂无误报反馈，可在任务详情标记误报';
  const pagination = { current: filters.pageNo, pageSize: filters.pageSize, total: page.total,
    pageSizeOptions: [20, 50, 100],
    onChange: (pageNo, pageSize) => setFilters((current) => ({ ...current, pageNo, pageSize })) };
  const loadError = error && <Alert type="error" title={`反馈加载失败：${error}`} action={<Button onClick={reload}>重试</Button>} />;

  if (globalView) return (
    <>
      <div className="memory-case-toolbar memory-feedback-toolbar">
        <div className="memory-case-controls">
          <Input.Search aria-label="反馈关键词" placeholder="搜索原结论或误判原因" value={search} maxLength={128} allowClear
            onChange={(event) => { setSearch(event.target.value); if (!event.target.value && filters.keyword) filter({ keyword: '' }); }}
            onSearch={(keyword) => filter({ keyword: keyword.trim() })} />
          {statusFilter}
          <Button icon={<FilterOutlined />} aria-expanded={moreFiltersOpen} aria-controls="memory-feedback-filters"
            onClick={() => setMoreFiltersOpen((open) => !open)}>筛选{filterCount ? `（${filterCount}）` : ''}</Button>
          <Button aria-label="刷新反馈" title="刷新反馈" icon={<ReloadOutlined />} onClick={reload} loading={loading} />
        </div>
      </div>
      <div id="memory-feedback-filters" className="memory-case-filter-panel" hidden={!moreFiltersOpen}>
        <label><Typography.Text>项目</Typography.Text><Select aria-label="反馈项目筛选" allowClear placeholder="全部项目" value={filters.projectId || undefined}
          showSearch={{ filterOption: false, onSearch: onProjectSearch }} loading={projectLoading}
          options={filters.projectId && !projectOptions.some((item) => item.value === filters.projectId)
            ? [{ value: filters.projectId, label: projectLabel(filters.projectId) }, ...projectOptions] : projectOptions}
          onChange={(project) => filter({ projectId: project || '' })} /></label>
        <label><Typography.Text>任务主端</Typography.Text><Select aria-label="反馈任务主端筛选" allowClear placeholder="全部任务主端" value={filters.targetType || undefined}
          options={TARGET_TYPE_OPTIONS} onChange={(targetType) => filter({ targetType: targetType || '' })} /></label>
        <Typography.Text type="secondary">任务主端来自原任务。多端任务以详情中的证据为准。</Typography.Text>
      </div>
      {loadError}
      <Spin spinning={loading}>
        <div className="memory-case-results" aria-busy={loading}>
          {page.items.length > 0 ? <ul className="memory-feedback-rows" role="list" aria-label="误报反馈">
            {page.items.map((row) => {
              const inactive = ['IGNORED', 'CONVERTED'].includes(row.status);
              const feedbackState = labelFor(FEEDBACK_STATUS_OPTIONS, row.status);
              const memoryState = memoryFeedbackState(row);
              const canOrganize = ['PENDING', 'VALID'].includes(row.status) && !row.memorySourceId && !isWritebackPending(row.writebackState);
              return <li className="memory-feedback-row" key={row.id} role="listitem">
                <div className="memory-feedback-content">
                  <Typography.Text strong>{row.riskTitle || '未命名问题'}</Typography.Text>
                  {row.reasonText ? <div className="memory-feedback-preview">{row.reasonText}</div> : canOrganize &&
                    <Typography.Text type="secondary">尚未填写误判原因</Typography.Text>}
                </div>
                <div className="memory-feedback-source">
                  <div className="memory-feedback-meta">
                    <Typography.Text>{projectLabel(String(row.projectId))}</Typography.Text>
                    <Typography.Text type="secondary">{row.targetType ? labelFor(TARGET_TYPE_OPTIONS, row.targetType) : '主端未记录'}</Typography.Text>
                  </div>
                  <div className="memory-feedback-meta">
                    <a href={`/tasks/${row.taskId}`} target="_blank" rel="noreferrer">任务 #{row.taskId}</a>
                    <Typography.Text type="secondary">反馈 #{row.id}</Typography.Text>
                    {row.createdAt && <Typography.Text type="secondary">{row.createdAt.replace('T', ' ')}</Typography.Text>}
                  </div>
                </div>
                <div className="memory-feedback-processing">
                  <div className="memory-feedback-states">
                    <Tag color={row.status === 'PENDING' ? 'gold' : undefined}>{feedbackState}</Tag>
                    {memoryState !== '尚未沉淀' && memoryState !== feedbackState && <Tag>{memoryState}</Tag>}
                  </div>
                  <div className="memory-feedback-actions">
                    <Button type={canOrganize ? 'primary' : 'default'} onClick={() => onOpen(row.id, row.projectId)}>
                      {canOrganize ? '整理案例' : row.memorySourceId ? '查看案例' : '查看反馈'}
                    </Button>
                    {!inactive && <Dropdown trigger={['click']} menu={{ items: [{ key: 'withdraw', label: '撤回误报', danger: true, disabled: withdrawing !== null }],
                      onClick: () => withdraw(row) }}>
                      <Button aria-label={`反馈 #${row.id} 的更多操作`} icon={<EllipsisOutlined />} />
                    </Dropdown>}
                  </div>
                </div>
              </li>;
            })}
          </ul> : !loading && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />}
        </div>
      </Spin>
      {page.total > 0 && <div className="memory-feedback-footer">
        <Typography.Text type="secondary">共 {page.total} 条反馈</Typography.Text>
        {page.total > 20 && <Pagination {...pagination} size="small" showSizeChanger />}
      </div>}
    </>
  );

  return (
    <>
      <Typography.Text strong>本项目人工误报反馈</Typography.Text>
      <Typography.Paragraph type="secondary">保存误报标记不会自动加入记忆库；已沉淀、已撤回及失败记录均保留。</Typography.Paragraph>
      <div className="memory-toolbar memory-top-space">
        {statusFilter}
        <Button aria-label="刷新反馈" onClick={reload} loading={loading}>刷新反馈</Button>
      </div>
      {loadError}
      <Table rowKey="id" dataSource={page.items} loading={loading} scroll={{ x: 1000 }}
        locale={{ emptyText }}
        columns={[
          { title: '原结论', dataIndex: 'riskTitle', width: 260, render: (value, row) => <><Typography.Text>{value || '未命名问题'}</Typography.Text><div>反馈 #{row.id}</div></> },
          { title: '人工说明 / 证据', dataIndex: 'reasonText', width: 260, render: (value) => <div className="memory-feedback-summary">{value || '尚未填写，整理案例时需补充证据'}</div> },
          { title: '反馈状态', dataIndex: 'status', width: 150, render: (value) => <Tag>{labelFor(FEEDBACK_STATUS_OPTIONS, value)}</Tag> },
          { title: '记忆状态', width: 170, render: (_, row) => <Tag>{memoryFeedbackState(row)}</Tag> },
          { title: '操作', width: 220, render: (_, row) => <Space wrap>
            <Button onClick={() => onOpen(row.id, row.projectId)}>{row.memorySourceId ? '查看案例 / 反馈' : '整理 / 查看反馈'}</Button>
            <a href={`/tasks/${row.taskId}`} target="_blank" rel="noreferrer">任务 #{row.taskId}</a>
          </Space> }
        ]}
        pagination={{ ...pagination, showSizeChanger: true, showTotal: (total) => `共 ${total} 条反馈` }} />
    </>
  );
}
