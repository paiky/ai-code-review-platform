import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Input,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  LinkOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

import {
  deleteNotificationWebhook,
  fetchNotificationWebhookProjects,
  fetchNotificationWebhooks,
  testNotificationWebhook,
  updateNotificationWebhook
} from './projectConfigurationApi.js';
import {
  EMPTY_WEBHOOK_FILTERS,
  formatDateTime,
  normalizePage,
  webhookTestMeta
} from './projectConfigurationModel.js';
import WebhookEditorModal from './WebhookEditorModal.jsx';

const { Text, Title } = Typography;

export default function WebhookLibrary({ onOpenProject, onDirtyChange }) {
  const [messageApi, contextHolder] = message.useMessage();
  const [filters, setFilters] = useState({ ...EMPTY_WEBHOOK_FILTERS });
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_WEBHOOK_FILTERS });
  const [page, setPage] = useState(() => normalizePage(null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [updatingId, setUpdatingId] = useState(null);
  const [editor, setEditor] = useState(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const [linkedProjects, setLinkedProjects] = useState(null);
  const [linkedProjectsLoading, setLinkedProjectsLoading] = useState(false);

  useEffect(() => onDirtyChange?.(editorDirty), [editorDirty, onDirtyChange]);

  const load = useCallback(async (nextPageNo = page.pageNo, nextPageSize = page.pageSize) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNotificationWebhooks(appliedFilters, {
        pageNo: nextPageNo,
        pageSize: nextPageSize
      });
      setPage(normalizePage(data, nextPageNo, nextPageSize));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, page.pageNo, page.pageSize]);

  useEffect(() => {
    load(1, page.pageSize);
  }, [appliedFilters]); // eslint-disable-line react-hooks/exhaustive-deps

  const search = () => setAppliedFilters({ ...filters });
  const reset = () => {
    const empty = { ...EMPTY_WEBHOOK_FILTERS };
    setFilters(empty);
    setAppliedFilters(empty);
  };

  const afterSaved = saved => {
    setEditor(null);
    setEditorDirty(false);
    messageApi.success(saved?.id ? '机器人已保存' : '机器人已新增');
    load();
  };

  const runTest = async webhook => {
    setTestingId(webhook.id);
    try {
      const result = await testNotificationWebhook(webhook.id);
      const status = result?.test?.status || result?.webhook?.lastTestStatus;
      if (status === 'SUCCESS') messageApi.success('机器人测试成功');
      else if (status === 'SKIPPED') messageApi.warning(result?.test?.message || '机器人测试已跳过');
      else messageApi.error(result?.test?.message || '机器人测试失败');
      await load();
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setTestingId(null);
    }
  };

  const toggleEnabled = async webhook => {
    setUpdatingId(webhook.id);
    try {
      await updateNotificationWebhook(webhook.id, { enabled: !webhook.enabled });
      messageApi.success(webhook.enabled ? '机器人已停用' : '机器人已启用');
      await load();
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setUpdatingId(null);
    }
  };

  const requestDelete = webhook => {
    Modal.confirm({
      title: '删除钉钉机器人？',
      content: `${webhook.name} 删除后无法恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      async onOk() {
        await deleteNotificationWebhook(webhook.id);
        messageApi.success('机器人已删除');
        await load();
      }
    });
  };

  const showLinkedProjects = async webhook => {
    setLinkedProjects({ webhook, items: [] });
    setLinkedProjectsLoading(true);
    try {
      const items = await fetchNotificationWebhookProjects(webhook.id);
      setLinkedProjects({ webhook, items: Array.isArray(items) ? items : [] });
    } catch (err) {
      messageApi.error(err.message);
      setLinkedProjects(null);
    } finally {
      setLinkedProjectsLoading(false);
    }
  };

  const columns = useMemo(() => [
    {
      title: '机器人名称',
      dataIndex: 'name',
      width: 220,
      fixed: 'left',
      render: (value, row) => (
        <div className="project-config-primary-cell">
          <Text strong>{value}</Text>
          <Text type="secondary" ellipsis={{ tooltip: row.description || '未填写描述' }}>
            {row.description || '未填写描述'}
          </Text>
        </div>
      )
    },
    { title: 'Webhook', dataIndex: 'webhookMasked', width: 250, render: value => <Text code>{value || '-'}</Text> },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: value => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    {
      title: '已关联项目',
      dataIndex: 'projectCount',
      width: 120,
      render: (value, row) => (
        <Button type="link" size="small" icon={<LinkOutlined />} onClick={() => showLinkedProjects(row)}>
          {value || 0} 个项目
        </Button>
      )
    },
    {
      title: '最近测试',
      dataIndex: 'lastTestStatus',
      width: 170,
      render: (value, row) => {
        const meta = webhookTestMeta(value);
        return (
          <div className="project-config-primary-cell">
            <Tag color={meta.color}>{meta.label}</Tag>
            <Text type="secondary">{formatDateTime(row.lastTestAt)}</Text>
          </div>
        );
      }
    },
    {
      title: '操作',
      key: 'actions',
      width: 190,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="编辑机器人">
            <Button type="text" icon={<EditOutlined />} onClick={() => setEditor(row)} aria-label={`编辑 ${row.name}`} />
          </Tooltip>
          <Tooltip title="测试已保存的 Webhook">
            <Button
              type="text"
              icon={<ThunderboltOutlined />}
              loading={testingId === row.id}
              onClick={() => runTest(row)}
              aria-label={`测试 ${row.name}`}
            />
          </Tooltip>
          <Tooltip title={row.enabled ? '停用机器人' : '启用机器人'}>
            <Button
              type="text"
              icon={<PoweroffOutlined />}
              loading={updatingId === row.id}
              onClick={() => toggleEnabled(row)}
              aria-label={`${row.enabled ? '停用' : '启用'} ${row.name}`}
            />
          </Tooltip>
          <Tooltip title={row.projectCount ? '请先解除所有项目关联' : '删除机器人'}>
            <Button
              type="text"
              danger
              disabled={Boolean(row.projectCount)}
              icon={<DeleteOutlined />}
              onClick={() => requestDelete(row)}
              aria-label={`删除 ${row.name}`}
            />
          </Tooltip>
        </Space>
      )
    }
  ], [load, testingId, updatingId]);

  return (
    <section className="project-config-tab-panel" aria-label="钉钉机器人库">
      {contextHolder}
      <div className="project-config-section-header">
        <div>
          <Title level={5}>钉钉机器人库</Title>
          <Text type="secondary">集中维护被多个项目复用的钉钉通知机器人</Text>
        </div>
        <Space>
          <Tooltip title="刷新机器人列表">
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => load()} aria-label="刷新机器人列表" />
          </Tooltip>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditor({})}>新增机器人</Button>
        </Space>
      </div>

      <div className="project-config-filter-bar webhook-filter-bar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={filters.keyword}
          placeholder="机器人名称 / Webhook 后四位"
          onChange={event => setFilters(current => ({ ...current, keyword: event.target.value }))}
          onPressEnter={search}
        />
        <Select
          allowClear
          value={filters.status}
          placeholder="全部状态"
          options={[
            { label: '启用', value: 'ENABLED' },
            { label: '停用', value: 'DISABLED' }
          ]}
          onChange={value => setFilters(current => ({ ...current, status: value }))}
        />
        <Select
          allowClear
          value={filters.lastTestStatus}
          placeholder="全部测试结果"
          options={[
            { label: '测试成功', value: 'SUCCESS' },
            { label: '测试失败', value: 'FAILED' },
            { label: '已跳过', value: 'SKIPPED' },
            { label: '未测试', value: 'UNTESTED' }
          ]}
          onChange={value => setFilters(current => ({ ...current, lastTestStatus: value }))}
        />
        <Space>
          <Button type="primary" icon={<SearchOutlined />} onClick={search}>查询</Button>
          <Button onClick={reset}>重置</Button>
        </Space>
      </div>

      {error && <Alert type="error" showIcon title="机器人列表加载失败" description={error} />}
      <div className="project-config-table-shell">
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={page.items}
          scroll={{ x: 1050 }}
          pagination={{
            current: page.pageNo,
            pageSize: page.pageSize,
            total: page.total,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50],
            showTotal: total => `共 ${total} 个机器人`,
            onChange: load
          }}
        />
      </div>

      <WebhookEditorModal
        open={editor !== null}
        webhook={editor?.id ? editor : null}
        onDirtyChange={setEditorDirty}
        onCancel={() => {
          if (editorDirty) {
            Modal.confirm({
              title: '放弃机器人修改？',
              okText: '放弃修改',
              cancelText: '继续编辑',
              onOk: () => {
                setEditor(null);
                setEditorDirty(false);
              }
            });
            return;
          }
          setEditor(null);
        }}
        onSaved={afterSaved}
      />

      <Modal
        open={Boolean(linkedProjects)}
        title={`${linkedProjects?.webhook?.name || ''} · 已关联项目`}
        footer={<Button onClick={() => setLinkedProjects(null)}>关闭</Button>}
        onCancel={() => setLinkedProjects(null)}
        width={620}
      >
        <Table
          rowKey="id"
          size="small"
          loading={linkedProjectsLoading}
          pagination={false}
          dataSource={linkedProjects?.items || []}
          columns={[
            { title: '项目', dataIndex: 'name' },
            { title: '状态', dataIndex: 'enabled', width: 90, render: value => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag> },
            {
              title: '操作',
              width: 90,
              render: (_, project) => (
                <Button type="link" onClick={() => {
                  setLinkedProjects(null);
                  onOpenProject?.(project);
                }}>
                  配置
                </Button>
              )
            }
          ]}
        />
      </Modal>
    </section>
  );
}
