import { Button, Space, Table, Tag, Tooltip, Typography } from 'antd';
import {
  ExclamationCircleOutlined,
  SettingOutlined
} from '@ant-design/icons';

import {
  projectDisplayName,
  projectRepositoryUrl,
  targetTypeMeta
} from './projectConfigurationModel.js';

const { Text } = Typography;
const PROJECT_COLUMN_WIDTH = 190;
const TABLE_SCROLL_WIDTH = 1090;

function NotificationSummary({ project }) {
  const status = project.notificationStatus || 'UNCONFIGURED';
  const meta = {
    CONFIGURED: { label: '已配置', color: 'success' },
    UNCONFIGURED: { label: '未配置', color: 'warning' },
    ABNORMAL: { label: '配置异常', color: 'error' }
  }[status] || { label: status, color: 'default' };
  return (
    <Space size={4}>
      <Tag color={meta.color}>{meta.label}</Tag>
      {project.healthWarning && (
        <Tooltip title="存在最近测试失败的启用机器人">
          <ExclamationCircleOutlined className="project-config-health-warning" aria-label="健康告警" />
        </Tooltip>
      )}
    </Space>
  );
}

function WebhookSummary({ webhooks = [] }) {
  if (!webhooks.length) return <Text type="secondary">未关联</Text>;
  const visible = webhooks.slice(0, 2);
  const all = (
    <div className="project-config-webhook-tooltip">
      {webhooks.map(item => (
        <div key={item.id}>{item.name} · {item.enabled ? '启用' : '停用'}</div>
      ))}
    </div>
  );
  return (
    <Tooltip title={all}>
      <Space size={[4, 4]} wrap>
        {visible.map(item => (
          <Tag key={item.id} color={item.enabled ? 'blue' : 'default'}>{item.name}</Tag>
        ))}
        {webhooks.length > 2 && <Tag>+{webhooks.length - 2}</Tag>}
      </Space>
    </Tooltip>
  );
}

export default function ProjectConfigurationTable({
  page,
  loading,
  selectedRowKeys,
  onSelectionChange,
  onPageChange,
  onConfigure
}) {
  const columns = [
    {
      title: '项目',
      dataIndex: 'name',
      width: PROJECT_COLUMN_WIDTH,
      fixed: 'left',
      render: (_, project) => {
        const repositoryUrl = projectRepositoryUrl(project);
        const displayName = projectDisplayName(project);
        return (
          <div className="project-config-project-cell">
            {repositoryUrl ? (
              <a
                className="project-config-project-link"
                href={repositoryUrl}
                target="_blank"
                rel="noopener noreferrer"
                title={`在 GitLab 中打开 ${displayName}`}
              >
                {displayName}
              </a>
            ) : <Text strong>{displayName}</Text>}
          </div>
        );
      }
    },
    {
      title: '端类型',
      dataIndex: 'targetType',
      width: 105,
      render: value => {
        const meta = targetTypeMeta(value);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      }
    },
    {
      title: 'Review 配置',
      key: 'review',
      width: 210,
      render: (_, project) => project.reviewStatus === 'CONFIGURED' ? (
        <div className="project-config-primary-cell">
          <Text>{project.reviewProfileCode || '默认 Profile'}</Text>
          <Text type="secondary" ellipsis={{ tooltip: (project.reviewModelNames || []).join('、') }}>
            {(project.reviewModelNames || []).join('、') || 'Provider 回退'}
          </Text>
        </div>
      ) : <Tag color="warning">未配置</Tag>
    },
    {
      title: '触发方式',
      key: 'triggers',
      width: 145,
      render: (_, project) => (
        <Space size={4}>
          <Tag color={project.triggerOnMr ? 'blue' : 'default'}>MR</Tag>
          <Tag color={project.triggerOnPush ? 'cyan' : 'default'}>PUSH</Tag>
        </Space>
      )
    },
    {
      title: '钉钉机器人',
      dataIndex: 'webhooks',
      width: 220,
      render: value => <WebhookSummary webhooks={value} />
    },
    {
      title: '通知状态',
      key: 'notification',
      width: 130,
      render: (_, project) => <NotificationSummary project={project} />
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      fixed: 'right',
      render: (_, project) => (
        <Button
          type="link"
          icon={<SettingOutlined />}
          onClick={() => onConfigure(project)}
        >
          配置
        </Button>
      )
    }
  ];

  return (
    <div className="project-config-table-shell">
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={page.items}
        scroll={{ x: TABLE_SCROLL_WIDTH }}
        rowSelection={{
          selectedRowKeys,
          preserveSelectedRowKeys: false,
          onChange: onSelectionChange,
          getCheckboxProps: row => ({ disabled: row.status !== 'ENABLED' })
        }}
        pagination={{
          current: page.pageNo,
          pageSize: page.pageSize,
          total: page.total,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50],
          showTotal: total => `共 ${total} 个项目`,
          onChange: onPageChange
        }}
      />
    </div>
  );
}
