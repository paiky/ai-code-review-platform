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
import { registerSettingsNavigationGuard } from '../settingsNavigation.js';
import { listLibrarySources, listSources } from './api.js';
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
import MemoryInjectionSettings from './MemoryInjectionSettings.jsx';
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
  const params = new URLSearchParams(location.search);
  const isLibrary = params.get('tab') !== 'projects';
  const ownerProjectId = /^[1-9]\d*$/.test(params.get('ownerProjectId') || '') ? params.get('ownerProjectId') : '';
  const usingProjectId = /^[1-9]\d*$/.test(params.get('usingProjectId') || '') ? params.get('usingProjectId') : '';
  const rawProjectId = params.get('projectId') || '';
  const linkedSourceId = params.get('sourceId') || '';
  const projectId = /^[1-9]\d*$/.test(rawProjectId) ? rawProjectId : '';
  const [projects, setProjects] = useState([]);
  const [projectSearch, setProjectSearch] = useState('');
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState(null);
  const [projectRetry, setProjectRetry] = useState(0);
  const [category, setCategory] = useState('rules');
  const [caseTab, setCaseTab] = useState('saved');
  const feedbackView = !isLibrary && category === 'cases' && caseTab === 'feedbacks';
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
  const [drawer, setDrawer] = useState(() => {
    return projectId && /^[1-9]\d*$/.test(linkedSourceId)
      ? { mode: 'view', sourceId: linkedSourceId, projectId, key: 0 } : null;
  });
  const [settingsReset, setSettingsReset] = useState(0);
  const settingsDirtyRef = useRef(false);
  const settingsBusyRef = useRef(false);
  const handleSettingsDirty = useCallback((dirty) => { settingsDirtyRef.current = dirty; }, []);
  const handleSettingsBusy = useCallback((busy) => { settingsBusyRef.current = busy; }, []);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacy, setLegacy] = useState(null);
  const [legacyError, setLegacyError] = useState(null);
  const [legacyRetry, setLegacyRetry] = useState(0);
  const dirtyRef = useRef(false);
  const busyRef = useRef(null);
  const currentUrl = useRef('');
  const drawerSequence = useRef(0);
  const previousSourceLink = useRef(`${projectId}:${linkedSourceId}`);
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
    if (settingsDirtyRef.current) {
      settingsDirtyRef.current = false;
      setSettingsReset((value) => value + 1);
    }
  }, []);
  const requestLeave = useCallback(
    (next) => {
      if (busyRef.current === 'save' || settingsBusyRef.current) {
        messageApi.info('正在保存或发布，请等待完成后再离开。');
        return;
      }
      if (!dirtyRef.current && !busyRef.current && !settingsDirtyRef.current) {
        discard();
        next();
        return;
      }
      Modal.confirm({
        title: busyRef.current === 'upload' ? '取消上传等待并离开？' : '放弃当前未保存修改？',
        content:
          busyRef.current === 'upload'
            ? '取消客户端等待不代表撤销服务端保存；请刷新列表检查是否已有草稿。'
            : '已保存内容继续保留，未保存的资料输入及记忆开关选择将丢弃。',
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

  useEffect(() => {
    const link = `${projectId}:${linkedSourceId}`;
    if (previousSourceLink.current === link) return;
    previousSourceLink.current = link;
    drawerSequence.current += 1;
    setDrawer(projectId && /^[1-9]\d*$/.test(linkedSourceId)
      ? { mode: 'view', sourceId: linkedSourceId, projectId, key: drawerSequence.current } : null);
  }, [projectId, linkedSourceId]);

  useEffect(
    () =>
      registerSettingsNavigationGuard({
        isDirty: () => dirtyRef.current || Boolean(busyRef.current) || settingsDirtyRef.current || settingsBusyRef.current,
        canNavigate: () => busyRef.current !== 'save' && !settingsBusyRef.current,
        shouldConfirmNavigation: () => true,
        currentUrl: () => currentUrl.current,
        discard,
        requestNavigation: requestLeave
      }),
    [discard, requestLeave, location.key]
  );

  useEffect(() => {
    const onBeforeUnload = (event) => {
      if (!dirtyRef.current && !busyRef.current && !settingsDirtyRef.current && !settingsBusyRef.current) return;
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
    if ((!isLibrary && !projectId) || feedbackView) {
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    const request = isLibrary
      ? listLibrarySources({ ...filters, ownerProjectId, usingProjectId }, controller.signal)
      : listSources(projectId, { ...filters, view }, controller.signal);
    request
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
  }, [projectId, filters, view, refresh, feedbackView, isLibrary, ownerProjectId, usingProjectId]);

  useEffect(() => {
    setLegacy(null);
    setLegacyError(null);
    if (isLibrary || !projectId || !legacyOpen) return undefined;
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
  }, [projectId, legacyOpen, legacyRetry, isLibrary]);

  const currentProject = projects.find((item) => String(item.id) === projectId);
  const projectName = currentProject?.name || `项目 #${projectId}`;
  const projectOptions = projects.map((item) => ({
    value: String(item.id),
    label: item.name
  }));
  if (projectId && !currentProject)
    projectOptions.unshift({ value: projectId, label: projectName });
  const updateQuery = (patch) => requestLeave(() => {
    const query = new URLSearchParams(location.search);
    Object.entries(patch).forEach(([key, value]) => value ? query.set(key, value) : query.delete(key));
    query.delete('sourceId');
    navigate({ pathname: location.pathname, search: query.toString(), hash: location.hash });
    changeFilter(patch.tab === 'projects' && view === 'USED' ? { state: '' } : {});
  });
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
          onClick={() => openDrawer({ mode: 'view', sourceId: record.id, projectId: isLibrary ? String(record.projectId) : projectId })}
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
      title: '共享范围 / 归属项目',
      width: 180,
      render: (_, record) => (
        <>
          <Tag>{record.visibility === 'SHARED' ? '共享' : '项目私有'}</Tag>
          <div>{projectLabel(record.projectId)}</div>
        </>
      )
    },
    {
      title: isLibrary ? '已添加项目' : '本项目关联',
      width: 150,
      render: (_, record) => isLibrary ? (
        <div>
          <Text>{record.activeBindingCount} 个项目</Text>
          {record.usingProjectIds?.map((id) => <div key={id}>{projectLabel(id)}</div>)}
          {record.usingProjectsTruncated && <Text type="secondary">仅展示前 3 个项目</Text>}
        </div>
      ) : (
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
          <Button onClick={() => openDrawer({ mode: 'view', sourceId: record.id, projectId: isLibrary ? String(record.projectId) : projectId })}>查看</Button>
          {!isLibrary && <Button onClick={() => openDrawer({ mode: 'binding', source: record })}>
            本项目关联
          </Button>}
        </Space>
      )
    }
  ];

  return (
    <section
      className="settings-route-panel memory-page"
      aria-label="项目记忆库"
      data-settings-section="review-memory"
    >
      {contextHolder}
      <Tabs
        aria-label="项目记忆库页签"
        activeKey={isLibrary ? 'library' : 'projects'}
        items={[{ key: 'library', label: '记忆资料' }, { key: 'projects', label: '项目使用配置' }]}
        onChange={(tab) => updateQuery({ tab })}
      />
      <div className="memory-page-heading">
        <div>
          <Title level={3}>项目记忆库</Title>
          <Paragraph type="secondary">集中管理规范、审查 Skill 与案例，再为项目配置使用关系。</Paragraph>
        </div>
        <Tag>资料管理</Tag>
      </div>
      <Alert
        type="info"
        showIcon
        title="资料发布后，按项目设置参与后续 Agent Review"
        description="需在“项目使用配置”开启并保存记忆开关；系统按适用端、路径和问题线索选择背景。Standard Review 沿用原有策略。"
      />
      {!isLibrary && <div className="memory-toolbar memory-top-space">
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
                query.delete('sourceId');
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
      </div>}
      {projectError && (
        <Alert
          type="error"
          title={`项目加载失败：${projectError}`}
          action={<Button onClick={() => setProjectRetry((value) => value + 1)}>重试</Button>}
        />
      )}
      {!isLibrary && rawProjectId && !projectId && (
        <Alert type="warning" title="项目参数无效，请重新选择项目。" />
      )}
      {!isLibrary && !projectId ? (
        <Empty className="memory-empty" description="先选择项目，再查看或维护资料" />
      ) : (
        <>
          {!isLibrary && <MemoryInjectionSettings key={`${projectId}-${settingsReset}`} projectId={projectId}
            onDirtyChange={handleSettingsDirty} onBusyChange={handleSettingsBusy} />}
          {!isLibrary && <Tabs
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
          />}
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
          {!isLibrary && category === 'cases' && <Tabs aria-label="踩坑案例视图" activeKey={caseTab}
            items={[{ key: 'saved', label: '已沉淀' }, { key: 'feedbacks', label: '待确认反馈' }]}
            onChange={(next) => requestLeave(() => setCaseTab(next))} />}
          {feedbackView ? <MemoryFeedbackList key={projectId} projectId={projectId} refresh={refresh}
            onOpen={(feedbackId) => openDrawer({ mode: 'feedback', feedbackId })} /> : <>
          {isLibrary && <div className="memory-toolbar memory-top-space">
            {[['ownerProjectId', '归属项目筛选', ownerProjectId], ['usingProjectId', '使用项目筛选', usingProjectId]].map(([key, label, value]) => (
              <label className="memory-project-select" key={key}>
                <Text strong>{label}</Text>
                <Select aria-label={label} allowClear showSearch={{ filterOption: false, onSearch: setProjectSearch }}
                  value={value || undefined} loading={projectLoading}
                  options={value && !projectOptions.some((item) => item.value === value)
                    ? [{ value, label: projectLabel(value) }, ...projectOptions] : projectOptions}
                  placeholder="全部项目" onChange={(next) => updateQuery({ [key]: next })} />
              </label>
            ))}
            <Text type="secondary">可搜索项目名称；使用项目按已添加关系筛选，不代表本次审查加载。</Text>
          </div>}
          <div className="memory-toolbar">
            <Select
              aria-label="资料子类型"
              value={filters.kind}
              options={KIND_OPTIONS.filter((item) => CATEGORY_KINDS[category].includes(item.value))}
              onChange={(kind) => changeFilter({ kind })}
            />
            <Select
              aria-label="资料状态筛选"
              disabled={!isLibrary && view === 'USED'}
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
              {isLibrary ? '集中维护各项目资料；共享及添加项目不代表本次审查会加载。' : view === 'OWNED'
                ? '维护本项目资料；解除自关联不删除资料。'
                : '仅显示有效资料的 ACTIVE 关联；已解除的共享资料可从共享库恢复。'}
            </Text>
            <Space wrap>
              {!isLibrary && <Button onClick={() => openDrawer({ mode: 'shared' })}>从共享库关联</Button>}
              {(isLibrary || view === 'OWNED') && (
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
                  : !isLibrary && view === 'USED'
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
          {!isLibrary && <Collapse
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
          />}
        </>
      )}
      {drawer?.mode === 'feedback' ? (
        <MemoryFeedbackDrawer key={`${drawer.projectId || projectId}-${drawer.key}`} projectId={drawer.projectId || projectId}
          feedbackId={drawer.feedbackId} onClose={() => requestLeave(() => {})}
          onDirtyChange={handleDirty} onBusyChange={handleBusy} onSaved={handleSaved} />
      ) : drawer && ['shared', 'binding'].includes(drawer.mode) ? (
        <MemoryAssociationDrawer
          key={`${projectId}-${drawer.key}`}
          projectId={drawer.projectId || projectId}
          projectName={drawer.projectId ? projectLabel(drawer.projectId) : projectName}
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
            projectId={drawer.projectId || (isLibrary ? undefined : projectId)}
            projectName={drawer.projectId ? projectLabel(drawer.projectId) : projectName}
            ownerOptions={isLibrary ? projectOptions : undefined}
            ownerLoading={projectLoading}
            onOwnerSearch={setProjectSearch}
            initial={drawer}
            onClose={() => requestLeave(() => {})}
            onDirtyChange={handleDirty}
            onBusyChange={handleBusy}
            onSaved={handleSaved}
            projectLabel={projectLabel}
            onViewFeedback={(feedbackId) => requestLeave(() => openDrawer({ mode: 'feedback', feedbackId, projectId: drawer.projectId || projectId }))}
            onManageBinding={(source) =>
              requestLeave(() => openDrawer({ mode: 'binding', source, projectId: isLibrary ? String(source.projectId) : projectId }))
            }
          />
        )
      )}
    </section>
  );
}
