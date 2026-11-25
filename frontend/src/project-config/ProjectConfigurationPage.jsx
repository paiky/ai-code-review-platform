import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Input,
  message,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography
} from 'antd';
import {
  CloseOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined
} from '@ant-design/icons';

import {
  fetchProjects,
  fetchTargetPathMappings,
  saveTargetPathMappings
} from './projectConfigurationApi.js';
import {
  DEFAULT_TARGET_PATHS,
  EMPTY_PROJECT_FILTERS,
  normalizePage,
  TARGET_TYPE_OPTIONS,
  targetTypeMeta
} from './projectConfigurationModel.js';
import BatchWebhookDrawer from './BatchWebhookDrawer.jsx';
import ProjectConfigurationDrawer from './ProjectConfigurationDrawer.jsx';
import ProjectConfigurationTable from './ProjectConfigurationTable.jsx';
import WebhookLibrary from './WebhookLibrary.jsx';
import './projectConfiguration.css';

const { Text, Title } = Typography;
const PATH_MAPPING_TARGET_TYPES = TARGET_TYPE_OPTIONS.filter(
  item => !['APP_CROSS_PLATFORM', 'GENERAL'].includes(item.value)
);

function normalizeMappings(items) {
  const source = Array.isArray(items) ? items : [];
  return PATH_MAPPING_TARGET_TYPES.map((option, index) => {
    const existing = source.find(item => item.targetType === option.value);
    return existing || {
      targetType: option.value,
      pathPatterns: DEFAULT_TARGET_PATHS[option.value],
      enabled: true,
      sortOrder: (index + 1) * 10,
      description: '系统默认端类型路径映射'
    };
  });
}

export default function ProjectConfigurationPage({ onDirtyChange }) {
  const [messageApi, contextHolder] = message.useMessage();
  const [activeTab, setActiveTab] = useState('projects');
  const [filters, setFilters] = useState({ ...EMPTY_PROJECT_FILTERS });
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_PROJECT_FILTERS });
  const [page, setPage] = useState(() => normalizePage(null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [projectDrawer, setProjectDrawer] = useState(null);
  const [projectDrawerDirty, setProjectDrawerDirty] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchDirty, setBatchDirty] = useState(false);
  const [webhookLibraryDirty, setWebhookLibraryDirty] = useState(false);
  const [mappings, setMappings] = useState([]);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [savingTargetType, setSavingTargetType] = useState(null);
  const hasDirtyDraft = projectDrawerDirty || batchDirty || webhookLibraryDirty;

  useEffect(() => onDirtyChange?.(hasDirtyDraft), [hasDirtyDraft, onDirtyChange]);

  const loadProjects = useCallback(async (pageNo = 1, pageSize = 20) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProjects(appliedFilters, { pageNo, pageSize });
      setPage(normalizePage(data, pageNo, pageSize));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    loadProjects(1, page.pageSize);
  }, [appliedFilters]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setMappingsLoading(true);
    fetchTargetPathMappings()
      .then(data => setMappings(normalizeMappings(data)))
      .catch(err => messageApi.error(err.message))
      .finally(() => setMappingsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedProjects = useMemo(
    () => page.items.filter(project => selectedRowKeys.includes(project.id)),
    [page.items, selectedRowKeys]
  );

  const applyFilters = () => {
    setSelectedRowKeys([]);
    setAppliedFilters({ ...filters });
  };

  const resetFilters = () => {
    const empty = { ...EMPTY_PROJECT_FILTERS };
    setSelectedRowKeys([]);
    setFilters(empty);
    setAppliedFilters(empty);
  };

  const changePage = (pageNo, pageSize) => {
    setSelectedRowKeys([]);
    loadProjects(pageNo, pageSize);
  };

  const discardTransientDrafts = () => {
    setProjectDrawer(null);
    setProjectDrawerDirty(false);
    setBatchOpen(false);
    setBatchDirty(false);
    setWebhookLibraryDirty(false);
  };

  const changeTab = nextTab => {
    if (nextTab === activeTab) return;
    const switchTab = () => {
      discardTransientDrafts();
      setSelectedRowKeys([]);
      setActiveTab(nextTab);
    };
    if (!hasDirtyDraft) {
      switchTab();
      return;
    }
    Modal.confirm({
      title: '放弃当前未保存修改？',
      content: '切换页签会放弃当前未保存的修改。',
      okText: '放弃并切换',
      cancelText: '继续编辑',
      onOk: switchTab
    });
  };

  const saveMapping = async (row, changes) => {
    if (savingTargetType) return;
    const mapping = { ...row, ...changes };
    setSavingTargetType(row.targetType);
    try {
      const saved = await saveTargetPathMappings([{
        targetType: mapping.targetType,
        pathPatterns: mapping.pathPatterns || [],
        enabled: mapping.enabled !== false,
        sortOrder: mapping.sortOrder,
        description: mapping.description || null
      }]);
      setMappings(normalizeMappings(saved));
      messageApi.success('端类型自动识别规则已保存');
    } catch (err) {
      messageApi.error(err.message);
    } finally {
      setSavingTargetType(null);
    }
  };

  const openProjectFromLibrary = project => {
    setActiveTab('projects');
    setSelectedRowKeys([]);
    setProjectDrawer(project);
  };

  const projectsPanel = (
    <section className="project-config-tab-panel" aria-label="项目配置">
      <div className="project-config-filter-bar">
        <Select
          allowClear
          value={filters.targetType}
          placeholder="全部端类型"
          options={TARGET_TYPE_OPTIONS}
          onChange={value => setFilters(current => ({ ...current, targetType: value }))}
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={filters.keyword}
          placeholder="项目名 / GitLab 路径 / ID"
          onChange={event => setFilters(current => ({ ...current, keyword: event.target.value }))}
          onPressEnter={applyFilters}
        />
        <Select
          allowClear
          value={filters.notificationStatus}
          placeholder="全部通知状态"
          options={[
            { label: '已配置', value: 'CONFIGURED' },
            { label: '未配置', value: 'UNCONFIGURED' },
            { label: '配置异常', value: 'ABNORMAL' },
            { label: '健康告警', value: 'HEALTH_WARNING' }
          ]}
          onChange={value => setFilters(current => ({ ...current, notificationStatus: value }))}
        />
        <Select
          allowClear
          value={filters.reviewStatus}
          placeholder="全部 Review 状态"
          options={[
            { label: '已配置', value: 'CONFIGURED' },
            { label: '未配置', value: 'UNCONFIGURED' }
          ]}
          onChange={value => setFilters(current => ({ ...current, reviewStatus: value }))}
        />
        <Space>
          <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>查询</Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </div>

      {selectedRowKeys.length > 0 && (
        <div className="project-config-selection-toolbar">
          <Text strong>已选择 {selectedRowKeys.length} 个项目</Text>
          <Button type="primary" ghost icon={<RobotOutlined />} onClick={() => setBatchOpen(true)}>
            批量配置机器人
          </Button>
          <Button type="text" icon={<CloseOutlined />} onClick={() => setSelectedRowKeys([])}>取消选择</Button>
        </div>
      )}

      {error && <Alert type="error" showIcon title="项目列表加载失败" description={error} />}
      <ProjectConfigurationTable
        page={page}
        loading={loading}
        selectedRowKeys={selectedRowKeys}
        onSelectionChange={setSelectedRowKeys}
        onPageChange={changePage}
        onConfigure={setProjectDrawer}
      />

    </section>
  );

  const rulesPanel = (
    <section className="project-config-tab-panel" aria-label="端类型自动识别规则">
      <div className="project-config-table-shell">
        <Table
          rowKey="targetType"
          size="small"
          loading={mappingsLoading}
          pagination={false}
          dataSource={mappings}
          scroll={{ x: 820 }}
          columns={[
            { title: '端类型', dataIndex: 'targetType', width: 140, render: value => {
              const meta = targetTypeMeta(value);
              return <Tag color={meta.color}>{meta.label}</Tag>;
            } },
            { title: '路径匹配', dataIndex: 'pathPatterns', render: (_, row) => (
              <Select
                mode="tags"
                className="full-width"
                value={row.pathPatterns}
                disabled={Boolean(savingTargetType)}
                onChange={pathPatterns => saveMapping(row, { pathPatterns })}
              />
            ) },
            { title: '启用', dataIndex: 'enabled', width: 90, render: (_, row) => (
              <Switch
                aria-label={`${targetTypeMeta(row.targetType).label}自动识别`}
                checked={row.enabled !== false}
                disabled={Boolean(savingTargetType)}
                loading={savingTargetType === row.targetType}
                onChange={enabled => saveMapping(row, { enabled })}
              />
            ) },
            { title: '操作', width: 90, render: (_, row) => (
              <Button
                type="link"
                icon={<ReloadOutlined />}
                disabled={Boolean(savingTargetType)}
                onClick={() => saveMapping(row, { pathPatterns: DEFAULT_TARGET_PATHS[row.targetType] })}
              >
                重置
              </Button>
            ) }
          ]}
        />
      </div>
    </section>
  );

  return (
    <div className="project-config-page">
      {contextHolder}
      <header className="settings-page-heading">
        <span className="settings-card-icon" aria-hidden="true"><FolderOpenOutlined /></span>
        <Title level={4}>项目通知与 Review 配置</Title>
      </header>

      <Tabs
        activeKey={activeTab}
        onChange={changeTab}
        items={[
          { key: 'projects', label: '项目配置', children: projectsPanel },
          {
            key: 'webhooks',
            label: '钉钉机器人库',
            children: <WebhookLibrary onOpenProject={openProjectFromLibrary} onDirtyChange={setWebhookLibraryDirty} />
          },
          { key: 'rules', label: '端类型自动识别规则', children: rulesPanel }
        ]}
      />

      <ProjectConfigurationDrawer
        open={Boolean(projectDrawer)}
        project={projectDrawer}
        onDirtyChange={setProjectDrawerDirty}
        onClose={() => {
          setProjectDrawer(null);
          setProjectDrawerDirty(false);
        }}
        onSaved={() => loadProjects(page.pageNo, page.pageSize)}
      />

      <BatchWebhookDrawer
        open={batchOpen}
        projects={selectedProjects}
        onDirtyChange={setBatchDirty}
        onClose={() => {
          setBatchOpen(false);
          setBatchDirty(false);
        }}
        onSaved={() => {
          setBatchOpen(false);
          setBatchDirty(false);
          setSelectedRowKeys([]);
          loadProjects(page.pageNo, page.pageSize);
        }}
      />
    </div>
  );
}
