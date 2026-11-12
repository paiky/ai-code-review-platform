import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Collapse,
  Empty,
  Input,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography
} from 'antd';
import { PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { fetchApi } from '../api.js';
import {
  AI_REVIEW_SETTINGS_TABS,
  registerSettingsNavigationGuard,
  requestSettingsNavigation
} from '../settingsNavigation.js';
import { listSources } from './api.js';
import {
  ISSUE_OPTIONS,
  KIND_OPTIONS,
  labelFor,
  ORIGIN_LABELS,
  STATE_LABELS,
  STATE_OPTIONS,
  stateColor,
  TARGET_TYPE_OPTIONS
} from './model.js';
import MemorySourceDrawer from './MemorySourceDrawer.jsx';
import MemoryAssociationDrawer from './MemoryAssociationDrawer.jsx';
import MemoryFeedbackDrawer from './MemoryFeedbackDrawer.jsx';
import MemoryFeedbackList from './MemoryFeedbackList.jsx';
import './reviewMemory.css';

const { Title, Paragraph, Text } = Typography;
const CATEGORIES = [
  { key: 'rules', label: '规范与约定' },
  { key: 'skills', label: '审查 Skill' },
  { key: 'cases', label: '踩坑案例' }
];
const CATEGORY_KINDS = {
  rules: ['STANDARD', 'ARCHITECTURE'],
  skills: ['SKILL'],
  cases: ['PITFALL', 'INCIDENT']
};

export default function ReviewMemoryPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [messageApi, contextHolder] = message.useMessage();
  const rawProjectId = new URLSearchParams(location.search).get('projectId') || '';
  const projectId = /^[1-9]\d*$/.test(rawProjectId) ? rawProjectId : '';
  const [projects, setProjects] = useState([]);
  const [projectSearch, setProjectSearch] = useState('');
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState(null);
  const [projectRetry, setProjectRetry] = useState(0);
  const [category, setCategory] = useState('rules');
  const [caseTab, setCaseTab] = useState('saved');
  const feedbackView = category === 'cases' && caseTab === 'feedbacks';
  const [view, setView] = useState('OWNED');
  const [filters, setFilters] = useState({
    kind: 'STANDARD',
    state: '',
    targetType: '',
    issueType: '',
    keyword: '',
    pageNo: 1,
    pageSize: 20
  });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [drawer, setDrawer] = useState(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacy, setLegacy] = useState(null);
  const [legacyError, setLegacyError] = useState(null);
  const [legacyRetry, setLegacyRetry] = useState(0);
  const dirtyRef = useRef(false);
  const busyRef = useRef(null);
  const currentUrl = useRef('');
  const drawerSequence = useRef(0);
  currentUrl.current = `${location.pathname}${location.search}${location.hash}`;
  const handleDirty = useCallback((dirty) => {
    dirtyRef.current = dirty;
  }, []);
  const handleBusy = useCallback((busy) => {
    busyRef.current = busy;
  }, []);
  const handleSaved = useCallback(() => setRefresh((value) => value + 1), []);

  const discard = useCallback(() => {
    dirtyRef.current = false;
    setDrawer(null);
  }, []);
  const requestLeave = useCallback(
    (next) => {
      if (busyRef.current === 'save') {
        messageApi.info('正在保存或发布，请等待完成后再离开。');
        return;
      }
      if (!dirtyRef.current && !busyRef.current) {
        discard();
        next();
        return;
      }
      Modal.confirm({
        title: busyRef.current === 'upload' ? '取消上传等待并离开？' : '放弃当前未保存修改？',
        content:
          busyRef.current === 'upload'
            ? '取消客户端等待不代表撤销服务端保存；请刷新列表检查是否已有草稿。'
            : '已保存的草稿继续保留，未保存的输入将丢弃。',
        okText: '放弃并离开',
        cancelText: '继续编辑',
        okButtonProps: { danger: true },
        onOk: () => {
          discard();
          next();
        }
      });
    },
    [discard, messageApi]
  );

  useEffect(
    () =>
      registerSettingsNavigationGuard({
        isDirty: () => dirtyRef.current || Boolean(busyRef.current),
        canNavigate: () => busyRef.current !== 'save',
        shouldConfirmNavigation: () => true,
        currentUrl: () => currentUrl.current,
        discard,
        requestNavigation: requestLeave
      }),
    [discard, requestLeave, location.key]
  );

  useEffect(() => {
    const onBeforeUnload = (event) => {
      if (!dirtyRef.current && !busyRef.current) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => {
        setProjectLoading(true);
        setProjectError(null);
        const query = new URLSearchParams({
          pageNo: '1',
          pageSize: '100',
          keyword: projectSearch
        });
        fetchApi(`/api/projects?${query}`, { signal: controller.signal })
          .then((data) => {
            if (!controller.signal.aborted)
              setProjects(Array.isArray(data) ? data : data?.items || []);
          })
          .catch((err) => {
            if (err.name !== 'AbortError') setProjectError(err.message);
          })
          .finally(() => {
            if (!controller.signal.aborted) setProjectLoading(false);
          });
      },
      projectSearch ? 250 : 0
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [projectSearch, projectRetry]);

  useEffect(() => {
    setPage({ items: [], total: 0 });
    setError(null);
    if (!projectId || feedbackView) {
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    listSources(projectId, { ...filters, view }, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setPage(data);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, filters, view, refresh, feedbackView]);

  useEffect(() => {
    setLegacy(null);
    setLegacyError(null);
    if (!projectId || !legacyOpen) return undefined;
    const controller = new AbortController();
    fetchApi(`/api/projects/${projectId}/review-policies`, {
      signal: controller.signal
    })
      .then((data) => {
        if (!controller.signal.aborted) setLegacy(Array.isArray(data) ? data : data?.items || []);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setLegacyError(err.message);
      });
    return () => controller.abort();
  }, [projectId, legacyOpen, legacyRetry]);

  const currentProject = projects.find((item) => String(item.id) === projectId);
  const projectName = currentProject?.name || `项目 #${projectId}`;
  const projectOptions = projects.map((item) => ({
    value: String(item.id),
    label: item.name
  }));
  if (projectId && !currentProject)
    projectOptions.unshift({ value: projectId, label: projectName });
  const openDrawer = (initial) => {
    drawerSequence.current += 1;
    setDrawer({ ...initial, key: drawerSequence.current });
  };
  const changeFilter = (patch) => setFilters((current) => ({ ...current, ...patch, pageNo: 1 }));
  const projectLabel = (id) =>
    `${projects.find((item) => String(item.id) === String(id))?.name || '项目'} #${id}`;

  const columns = [
    {
      title: '资料名称',
      dataIndex: 'title',
      width: 300,
      render: (value, record) => (
        <Button
          type="link"
          className="memory-title-link"
          onClick={() => openDrawer({ mode: 'view', sourceId: record.id })}
        >
          {value}
        </Button>
      )
    },
    {
      title: '类型',
      dataIndex: 'kind',
      width: 110,
      render: (value) => labelFor(KIND_OPTIONS, value)
    },
    {
      title: '来源',
      dataIndex: 'origin',
      width: 110,
      render: (value) => ORIGIN_LABELS[value] || value
    },
    {
      title: '状态',
      dataIndex: 'state',
      width: 110,
      render: (value) => <Tag color={stateColor(value)}>{STATE_LABELS[value]}</Tag>
    },
    {
      title: '共享 / 维护项目',
      width: 180,
      render: (_, record) => (
        <>
          <Tag>{record.visibility === 'SHARED' ? '共享' : '项目私有'}</Tag>
          <div>{projectLabel(record.projectId)}</div>
        </>
      )
    },
    {
      title: '本项目关联',
      width: 150,
      render: (_, record) => (
        <>
          <Tag color={record.binding?.state === 'ACTIVE' ? 'green' : 'default'}>
            {record.binding?.state === 'ACTIVE' ? '已关联' : '已解除 / 未关联'}
          </Tag>
          <div>{record.binding?.pathGlobs?.join('、') || '不限路径'}</div>
        </>
      )
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      width: 200,
      render: (value) => value?.replace('T', ' ').slice(0, 19) || '—'
    },
    {
      title: '操作',
      width: 200,
      render: (_, record) => (
        <Space wrap>
          <Button onClick={() => openDrawer({ mode: 'view', sourceId: record.id })}>查看</Button>
          <Button onClick={() => openDrawer({ mode: 'binding', source: record })}>
            本项目关联
          </Button>
        </Space>
      )
    }
  ];

  return (
    <section
      className="settings-route-panel memory-page"
      aria-label="项目记忆库"
      data-settings-section="ai-review-settings"
    >
      {contextHolder}
      <Tabs
        aria-label="AI Review 配置页签"
        activeKey="memory"
        items={AI_REVIEW_SETTINGS_TABS.map((tab) => ({
          key: tab.key,
          label: tab.label
        }))}
        onChange={(key) =>
          requestSettingsNavigation(() =>
            navigate(AI_REVIEW_SETTINGS_TABS.find((tab) => tab.key === key).route)
          )
        }
      />
      <div className="memory-page-heading">
        <div>
          <Title level={3}>项目记忆库</Title>
          <Paragraph type="secondary">管理项目规范、审查 Skill 与人工整理的案例。</Paragraph>
        </div>
        <Tag>资料管理</Tag>
      </div>
      <Alert
        type="info"
        showIcon
        title="资料可管理，尚未接入自动审查"
        description="“已发布”表示资料已确认；Agent Review 读取记忆和注入开关将在后续阶段接入。"
      />
      <div className="memory-toolbar memory-top-space">
        <label className="memory-project-select">
          <Text strong>当前项目</Text>
          <Select
            aria-label="当前项目"
            showSearch={{ filterOption: false, onSearch: setProjectSearch }}
            allowClear
            value={projectId || undefined}
            options={projectOptions}
            loading={projectLoading}
            placeholder="搜索并选择项目"
            onChange={(value) =>
              requestLeave(() => {
                const query = new URLSearchParams(location.search);
                if (value) query.set('projectId', value);
                else query.delete('projectId');
                navigate({
                  pathname: location.pathname,
                  search: query.toString()
                });
                changeFilter({ pageNo: 1 });
                setLegacyOpen(false);
              })
            }
          />
        </label>
        <Text type="secondary">每次搜索最多显示 100 个项目，可输入名称查找。</Text>
      </div>
      {projectError && (
        <Alert
          type="error"
          title={`项目加载失败：${projectError}`}
          action={<Button onClick={() => setProjectRetry((value) => value + 1)}>重试</Button>}
        />
      )}
      {rawProjectId && !projectId && (
        <Alert type="warning" title="项目参数无效，请重新选择项目。" />
      )}
      {!projectId ? (
        <Empty className="memory-empty" description="先选择项目，再查看或维护资料" />
      ) : (
        <>
          <Tabs
            aria-label="资料视图"
            style={feedbackView ? { display: 'none' } : undefined}
            activeKey={view}
            items={[
              { key: 'OWNED', label: '维护资料' },
              { key: 'USED', label: '本项目使用' }
            ]}
            onChange={(next) =>
              requestLeave(() => {
                setView(next);
                changeFilter({ state: '' });
              })
            }
          />
          <Tabs
            activeKey={category}
            items={CATEGORIES}
            onChange={(next) =>
              requestLeave(() => {
                setCategory(next);
                setCaseTab('saved');
                changeFilter({ kind: CATEGORY_KINDS[next][0], keyword: '' });
                setSearch('');
              })
            }
          />
          {category === 'cases' && <Tabs aria-label="踩坑案例视图" activeKey={caseTab}
            items={[{ key: 'saved', label: '已沉淀' }, { key: 'feedbacks', label: '待确认反馈' }]}
            onChange={(next) => requestLeave(() => setCaseTab(next))} />}
          {feedbackView ? <MemoryFeedbackList key={projectId} projectId={projectId} refresh={refresh}
            onOpen={(feedbackId) => openDrawer({ mode: 'feedback', feedbackId })} /> : <>
          <div className="memory-toolbar">
            <Select
              aria-label="资料子类型"
              value={filters.kind}
              options={KIND_OPTIONS.filter((item) => CATEGORY_KINDS[category].includes(item.value))}
              onChange={(kind) => changeFilter({ kind })}
            />
            <Select
              aria-label="资料状态筛选"
              disabled={view === 'USED'}
              allowClear
              value={filters.state || undefined}
              placeholder="全部状态"
              options={STATE_OPTIONS}
              onChange={(state) => changeFilter({ state: state || '' })}
            />
            <Select
              aria-label="适用端筛选"
              allowClear
              value={filters.targetType || undefined}
              placeholder="全部端"
              options={TARGET_TYPE_OPTIONS}
              onChange={(targetType) => changeFilter({ targetType: targetType || '' })}
            />
            <Select
              aria-label="问题类型筛选"
              allowClear
              value={filters.issueType || undefined}
              placeholder="全部问题"
              options={ISSUE_OPTIONS}
              onChange={(issueType) => changeFilter({ issueType: issueType || '' })}
            />
            <Input.Search
              aria-label="搜索资料"
              className="memory-search"
              value={search}
              maxLength={128}
              placeholder="搜索标题或正文"
              allowClear
              onChange={(event) => setSearch(event.target.value)}
              onSearch={(keyword) => changeFilter({ keyword: keyword.trim() })}
            />
            <Button
              aria-label="刷新"
              icon={<ReloadOutlined />}
              onClick={() => setRefresh((value) => value + 1)}
              loading={loading}
            >
              刷新
            </Button>
          </div>
          <div className="memory-toolbar memory-list-actions">
            <Text type="secondary">
              {view === 'OWNED'
                ? '维护本项目资料；解除自关联不删除资料。'
                : '仅显示有效资料的 ACTIVE 关联；已解除的共享资料可从共享库恢复。'}
            </Text>
            <Space wrap>
              <Button onClick={() => openDrawer({ mode: 'shared' })}>从共享库关联</Button>
              {view === 'OWNED' && (
                <>
                  <Button
                    aria-label="上传资料"
                    icon={<UploadOutlined />}
                    onClick={() => openDrawer({ mode: 'upload', kind: filters.kind })}
                  >
                    上传资料
                  </Button>
                  <Button
                    aria-label="新建条目"
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => openDrawer({ mode: 'manual', kind: filters.kind })}
                  >
                    新建条目
                  </Button>
                </>
              )}
            </Space>
          </div>
          {error && (
            <Alert
              type="error"
              showIcon
              title="资料加载失败"
              description={error}
              action={<Button onClick={() => setRefresh((value) => value + 1)}>重试</Button>}
            />
          )}
          <Table
            rowKey="id"
            dataSource={page.items}
            columns={columns}
            loading={loading}
            scroll={{ x: 1400 }}
            locale={{
              emptyText: error
                ? '加载失败，请重试'
                : filters.keyword || filters.state || filters.targetType || filters.issueType
                  ? '没有符合筛选条件的资料'
                  : view === 'USED'
                    ? '暂无有效关联，可从共享库关联'
                    : '暂无该类型资料，可以上传或新建'
            }}
            pagination={{
              current: filters.pageNo,
              pageSize: filters.pageSize,
              total: page.total,
              showSizeChanger: true,
              pageSizeOptions: [20, 50, 100],
              showTotal: (total) => `共 ${total} 份资料`,
              onChange: (pageNo, pageSize) =>
                setFilters((current) => ({ ...current, pageNo, pageSize }))
            }}
          />
          </>}
          <Collapse
            className="memory-top-space"
            activeKey={legacyOpen ? ['legacy'] : []}
            onChange={(keys) => setLegacyOpen(keys.includes('legacy'))}
            items={[
              {
                key: 'legacy',
                label: '旧项目策略 · 只读来源',
                children: (
                  <>
                    <Paragraph type="secondary">
                      旧策略继续按原机制加载，此处只读展示，不复制到新记忆库。
                    </Paragraph>
                    {legacyError ? (
                      <Alert
                        type="error"
                        title={legacyError}
                        action={
                          <Button onClick={() => setLegacyRetry((value) => value + 1)}>重试</Button>
                        }
                      />
                    ) : legacy == null ? (
                      <Text>正在加载…</Text>
                    ) : !legacy.length ? (
                      <Empty description="暂无旧项目策略" />
                    ) : (
                      legacy.map((item) => (
                        <div key={item.id} className="memory-legacy-item">
                          <Text strong>{item.title}</Text>
                          <Tag>{item.enabled ? '已启用' : '已停用'}</Tag>
                          <pre className="memory-plain-text">{item.content}</pre>
                        </div>
                      ))
                    )}
                  </>
                )
              }
            ]}
          />
        </>
      )}
      {drawer?.mode === 'feedback' ? (
        <MemoryFeedbackDrawer key={`${projectId}-${drawer.key}`} projectId={projectId}
          feedbackId={drawer.feedbackId} onClose={() => requestLeave(() => {})}
          onDirtyChange={handleDirty} onBusyChange={handleBusy} onSaved={handleSaved} />
      ) : drawer && ['shared', 'binding'].includes(drawer.mode) ? (
        <MemoryAssociationDrawer
          key={`${projectId}-${drawer.key}`}
          projectId={projectId}
          projectName={projectName}
          projectLabel={projectLabel}
          initial={drawer}
          onClose={() => requestLeave(() => {})}
          onDirtyChange={handleDirty}
          onBusyChange={handleBusy}
          onSaved={handleSaved}
        />
      ) : (
        drawer && (
          <MemorySourceDrawer
            key={`${projectId}-${drawer.key}`}
            projectId={projectId}
            projectName={projectName}
            initial={drawer}
            onClose={() => requestLeave(() => {})}
            onDirtyChange={handleDirty}
            onBusyChange={handleBusy}
            onSaved={handleSaved}
            projectLabel={projectLabel}
            onViewFeedback={(feedbackId) => requestLeave(() => openDrawer({ mode: 'feedback', feedbackId }))}
            onManageBinding={(source) =>
              requestLeave(() => openDrawer({ mode: 'binding', source }))
            }
          />
        )
      )}
    </section>
  );
}
