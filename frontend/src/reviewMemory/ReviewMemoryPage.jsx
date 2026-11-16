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
import { getMemoryCapabilities, getMemorySettings, listLibrarySources } from './api.js';
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
import MemoryUploadPanel from './MemoryUploadPanel.jsx';
import MemoryAssociationDrawer from './MemoryAssociationDrawer.jsx';
import MemoryFeedbackDrawer from './MemoryFeedbackDrawer.jsx';
import MemoryFeedbackList from './MemoryFeedbackList.jsx';
import MemoryProjectBindings from './MemoryProjectBindings.jsx';
import MemorySourceProjectsDrawer from './MemorySourceProjectsDrawer.jsx';
import './reviewMemory.css';

const { Title, Paragraph, Text } = Typography;
const DOCUMENT_KINDS = ['STANDARD', 'SKILL', 'ARCHITECTURE'];
const CASE_KINDS = ['PITFALL', 'INCIDENT'];

export default function ReviewMemoryPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [messageApi, contextHolder] = message.useMessage();
  const params = new URLSearchParams(location.search);
  const activeTab = ['upload', 'cases', 'projects'].includes(params.get('tab')) ? params.get('tab') : 'library';
  const isProjects = activeTab === 'projects';
  const isLibrary = activeTab === 'library' || activeTab === 'cases';
  const kindOptions = activeTab === 'cases' ? CASE_KINDS : DOCUMENT_KINDS;
  const ownerProjectId = /^[1-9]\d*$/.test(params.get('ownerProjectId') || '') ? params.get('ownerProjectId') : '';
  const usingProjectId = /^[1-9]\d*$/.test(params.get('usingProjectId') || '') ? params.get('usingProjectId') : '';
  const rawProjectId = params.get('projectId') || '';
  const linkedSourceId = params.get('sourceId') || '';
  const projectId = /^[1-9]\d*$/.test(rawProjectId) ? rawProjectId : '';
  const [projects, setProjects] = useState([]);
  const [projectNames, setProjectNames] = useState({});
  const [projectSearch, setProjectSearch] = useState('');
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState(null);
  const [projectRetry, setProjectRetry] = useState(0);
  const [caseTab, setCaseTab] = useState('feedbacks');
  const [projectFeedbackOpen, setProjectFeedbackOpen] = useState(false);
  const feedbackView = activeTab === 'cases' && caseTab === 'feedbacks';
  const showList = isLibrary && !feedbackView;
  const [uploadReset, setUploadReset] = useState(0);
  const uploadDirtyRef = useRef(false);
  const uploadBusyRef = useRef(null);
  const handleUploadDirty = useCallback((dirty) => { uploadDirtyRef.current = dirty; }, []);
  const handleUploadBusy = useCallback((busy) => { uploadBusyRef.current = busy; }, []);
  const [projectSettings, setProjectSettings] = useState(null);
  const [filters, setFilters] = useState({
    kind: '',
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
  const [capabilities, setCapabilities] = useState(null);
  const [capabilityError, setCapabilityError] = useState(null);
  const [capabilityRetry, setCapabilityRetry] = useState(0);
  const [drawer, setDrawer] = useState(() => {
    return /^[1-9]\d*$/.test(linkedSourceId)
      ? { mode: 'view', sourceId: linkedSourceId, projectId, library: !projectId, key: 0 } : null;
  });
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

  useEffect(() => {
    if (!isProjects || !projectId) return;
    const controller = new AbortController();
    setProjectSettings(null);
    getMemorySettings(projectId, controller.signal).then((settings) => {
      if (!controller.signal.aborted) setProjectSettings({ projectId, settings });
    }).catch(() => {
      if (!controller.signal.aborted) setProjectSettings(null);
    });
    return () => controller.abort();
  }, [isProjects, projectId, location.key]);

  useEffect(() => {
    const controller = new AbortController();
    setCapabilities(null);
    setCapabilityError(null);
    getMemoryCapabilities(controller.signal).then((data) => {
      if (!controller.signal.aborted) setCapabilities(data);
    }).catch((err) => {
      if (!controller.signal.aborted) setCapabilityError(err.message);
    });
    return () => controller.abort();
  }, [capabilityRetry]);

  const discard = useCallback(() => {
    dirtyRef.current = false;
    setDrawer(null);
    if (uploadDirtyRef.current || uploadBusyRef.current) {
      uploadDirtyRef.current = false; uploadBusyRef.current = null;
      setUploadReset((value) => value + 1);
    }
  }, []);
  const requestLeave = useCallback(
    (next) => {
      if (busyRef.current === 'save') {
        messageApi.info('正在保存或发布，请等待完成后再离开。');
        return;
      }
      if (!dirtyRef.current && !busyRef.current && !uploadDirtyRef.current && !uploadBusyRef.current) {
        discard();
        next();
        return;
      }
      Modal.confirm({
        title: (busyRef.current === 'upload' || uploadBusyRef.current) ? '取消上传等待并离开？' : '放弃当前未保存修改？',
        content:
          (busyRef.current === 'upload' || uploadBusyRef.current)
            ? '取消客户端等待不代表撤销服务端保存；请刷新列表检查是否已有草稿。'
            : '已保存内容继续保留，未保存的资料输入将丢弃。',
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

  function closeUploadPreview() {
    if (busyRef.current) {
      messageApi.info('正在保存或发布，请等待完成后再离开。');
      return;
    }
    const close = () => { dirtyRef.current = false; setDrawer(null); };
    if (!dirtyRef.current) { close(); return; }
    Modal.confirm({ title: '放弃当前未保存修改？', content: '未保存的详情修改将丢弃，文件队列继续保留。',
      okText: '放弃并离开', cancelText: '继续编辑', onOk: close });
  }

  useEffect(() => {
    const link = `${projectId}:${linkedSourceId}`;
    if (previousSourceLink.current === link) return;
    previousSourceLink.current = link;
    drawerSequence.current += 1;
    setDrawer(/^[1-9]\d*$/.test(linkedSourceId)
      ? { mode: 'view', sourceId: linkedSourceId, projectId, library: !projectId, key: drawerSequence.current } : null);
  }, [projectId, linkedSourceId]);

  useEffect(
    () =>
      registerSettingsNavigationGuard({
        isDirty: () => dirtyRef.current || Boolean(busyRef.current) || uploadDirtyRef.current || Boolean(uploadBusyRef.current),
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
      if (!dirtyRef.current && !busyRef.current && !uploadDirtyRef.current && !uploadBusyRef.current) return;
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
            if (!controller.signal.aborted) {
              const items = Array.isArray(data) ? data : data?.items || [];
              setProjects(items);
              setProjectNames((current) => ({
                ...current,
                ...Object.fromEntries(items.map((item) => [String(item.id), item.name]))
              }));
            }
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
    if (!showList) {
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    const request = listLibrarySources({ ...filters, kind: kindOptions.includes(filters.kind) ? filters.kind : '',
      category: activeTab === 'cases' ? 'CASE' : 'DOCUMENT', ownerProjectId, usingProjectId }, controller.signal);
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
  }, [filters, refresh, showList, activeTab, ownerProjectId, usingProjectId]);

  useEffect(() => {
    setLegacy(null);
    setLegacyError(null);
    if (!isProjects || !projectId || !legacyOpen) return undefined;
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
  }, [projectId, legacyOpen, legacyRetry, isProjects]);

  const currentProject = projects.find((item) => String(item.id) === projectId);
  const projectName = projectNames[projectId] || `项目 #${projectId}`;
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
    changeFilter(patch.tab ? { kind: '', keyword: '' } : {});
    if (patch.tab) setSearch('');
  });
  const openDrawer = (initial) => {
    drawerSequence.current += 1;
    setDrawer({ ...initial, key: drawerSequence.current });
  };
  const changeFilter = (patch) => setFilters((current) => ({ ...current, ...patch, pageNo: 1 }));
  const projectLabel = (id) =>
    `${projectNames[String(id)] || '项目'} #${id}`;

  const columns = [
    {
      title: '资料名称',
      dataIndex: 'title',
      width: 250,
      render: (value, record) => (
        <div><Button
          type="link"
          className="memory-title-link"
          onClick={() => openDrawer({ mode: 'view', sourceId: record.id, library: record.projectId == null, projectId: isLibrary ? record.projectId == null ? null : String(record.projectId) : projectId })}
        >
          {value}
        </Button>
          <div><Text type="secondary">{record.projectId == null ? '公共资料' : `归属：${projectLabel(record.projectId)}`}</Text></div>
          <div><Text type="secondary">{record.visibility === 'SHARED' ? '共享' : '项目私有'} · {ORIGIN_LABELS[record.origin] || record.origin}</Text></div>
        </div>
      )
    },
    {
      title: '类型',
      dataIndex: 'kind',
      width: 100,
      render: (value) => labelFor(KIND_OPTIONS, value)
    },
    {
      title: '适用端',
      width: 135,
      render: (_, record) => <>
        {!record.hasEntries ? '未设置' : <>
          {record.hasUnrestrictedTarget && <Tag>不限</Tag>}
          {record.targetTypes?.map((target) => <Tag key={target}>{labelFor(TARGET_TYPE_OPTIONS, target)}</Tag>)}
        </>}
      </>
    },
    {
      title: '状态',
      dataIndex: 'state',
      width: 90,
      render: (value) => <Tag color={stateColor(value)}>{STATE_LABELS[value]}</Tag>
    },
    {
      title: '已添加项目',
      width: 140,
      render: (_, record) => (
        <div>
          <Text>{record.activeBindingCount} 个项目</Text>
          {record.usingProjectIds?.map((id) => <div key={id}>{projectLabel(id)}</div>)}
          {record.usingProjectsTruncated && <Text type="secondary">仅展示前 3 个项目</Text>}
        </div>
      )
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      width: 155,
      render: (value) => value?.replace('T', ' ').slice(0, 16) || '—'
    },
    {
      title: '操作',
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button onClick={() => openDrawer({ mode: 'view', sourceId: record.id, library: record.projectId == null, projectId: isLibrary ? record.projectId == null ? null : String(record.projectId) : projectId })}>查看</Button>
          <Button onClick={() => openDrawer({ mode: 'projects', source: record })}>管理使用项目</Button>
          {record.origin === 'FEEDBACK' && record.sourceFeedbackId && <Button onClick={() => openDrawer({ mode: 'feedback', projectId: String(record.projectId), feedbackId: record.sourceFeedbackId })}>查看来源反馈</Button>}
        </Space>
      )
    }
  ];

  const onSourceLoaded = useCallback((source) => {
    if (isProjects || !linkedSourceId || String(source.id) !== linkedSourceId) return;
    const tab = CASE_KINDS.includes(source.kind) ? 'cases' : 'library';
    if (tab === 'cases') setCaseTab('saved');
    if (activeTab !== tab) {
      const query = new URLSearchParams(location.search);
      query.set('tab', tab);
      navigate({ pathname: location.pathname, search: query.toString(), hash: location.hash }, { replace: true });
    }
  }, [isProjects, linkedSourceId, activeTab, location.pathname, location.search, location.hash, navigate]);
  const projectPicker = <div className="memory-toolbar memory-top-space">
    <label className="memory-project-select">
      <Text strong>{isProjects ? '当前项目' : '反馈项目'}</Text>
      <Select aria-label={isProjects ? '当前项目' : '反馈项目'} allowClear
        showSearch={{ filterOption: false, onSearch: setProjectSearch }} value={projectId || undefined}
        options={projectOptions} loading={projectLoading} placeholder="搜索并选择项目"
        onChange={(value) => { updateQuery({ projectId: value }); setLegacyOpen(false); }} />
    </label>
    <Text type="secondary">每次搜索最多显示 100 个项目，可输入名称查找。</Text>
  </div>;
  const sourceList = <>
    <div className="memory-simple-filters">
      <label><Text strong>关键词</Text><Input.Search aria-label="搜索资料" value={search} maxLength={128}
        placeholder="搜索标题或正文" allowClear onChange={(event) => setSearch(event.target.value)}
        onSearch={(keyword) => changeFilter({ keyword: keyword.trim() })} /></label>
      <label><Text strong>适用端</Text><Select aria-label="适用端筛选" allowClear
        value={filters.targetType || undefined} placeholder="全部端" options={TARGET_TYPE_OPTIONS}
        onChange={(targetType) => changeFilter({ targetType: targetType || '' })} /></label>
      <label><Text strong>资料类型</Text><Select aria-label="资料类型筛选" allowClear
        value={kindOptions.includes(filters.kind) ? filters.kind : undefined} placeholder="全部类型"
        options={KIND_OPTIONS.filter((item) => kindOptions.includes(item.value))}
        onChange={(kind) => changeFilter({ kind: kind || '' })} /></label>
      <label><Text strong>发布状态</Text><Select aria-label="资料状态筛选" allowClear value={filters.state || undefined}
        placeholder="全部状态" options={STATE_OPTIONS} onChange={(state) => changeFilter({ state: state || '' })} /></label>
    </div>
    <Collapse className="memory-more-filters" items={[{ key: 'more', label: '更多筛选（项目 / 问题类型）', children:
      <div className="memory-toolbar">
        {[['ownerProjectId', '归属项目筛选', ownerProjectId], ['usingProjectId', '使用项目筛选', usingProjectId]].map(([key, label, value]) => (
          <label className="memory-project-select" key={key}><Text strong>{label}</Text>
            <Select aria-label={label} allowClear showSearch={{ filterOption: false, onSearch: setProjectSearch }}
              value={value || undefined} loading={projectLoading}
              options={value && !projectOptions.some((item) => item.value === value) ? [{ value, label: projectLabel(value) }, ...projectOptions] : projectOptions}
              placeholder="全部项目" onChange={(next) => updateQuery({ [key]: next })} />
          </label>
        ))}
        <Select aria-label="问题类型筛选" allowClear value={filters.issueType || undefined} placeholder="全部问题"
          options={ISSUE_OPTIONS} onChange={(issueType) => changeFilter({ issueType: issueType || '' })} />
        <Text type="secondary">使用项目按已添加关系筛选，不代表本次审查加载。</Text>
      </div>
    }]} />
    {(ownerProjectId || usingProjectId || filters.issueType) && <Paragraph type="secondary">
      当前额外筛选：{ownerProjectId && `归属 ${projectLabel(ownerProjectId)}；`}{usingProjectId && `使用 ${projectLabel(usingProjectId)}；`}{filters.issueType && labelFor(ISSUE_OPTIONS, filters.issueType)}
    </Paragraph>}
    <div className="memory-toolbar memory-list-actions memory-top-space">
      <Title level={4}>{activeTab === 'cases' ? '已沉淀案例' : '记忆资料列表'}</Title>
      <Space wrap>
        <Button icon={<ReloadOutlined />} aria-label="刷新" loading={loading} onClick={() => setRefresh((value) => value + 1)}>刷新</Button>
        {activeTab === 'library' && <Button aria-label="上传资料" icon={<UploadOutlined />} onClick={() => updateQuery({ tab: 'upload' })}>上传资料</Button>}
        <Button aria-label="新建条目" icon={<PlusOutlined />} onClick={() => openDrawer({ mode: 'manual', kind: filters.kind || (activeTab === 'cases' ? 'PITFALL' : 'STANDARD'), library: activeTab !== 'cases' })}>新建条目</Button>
      </Space>
    </div>
    <Paragraph type="secondary">适用端汇总所有管理章节（含草稿和停用）；资料发布、项目开启且匹配本次变更后才可能采用。</Paragraph>
    {error && <Alert type="error" showIcon title="资料加载失败" description={error}
      action={<Button onClick={() => setRefresh((value) => value + 1)}>重试</Button>} />}
    <Table rowKey="id" dataSource={page.items} columns={columns} loading={loading} scroll={{ x: 1100 }}
      locale={{ emptyText: error ? '加载失败，请重试' : '暂无符合条件的资料，可以上传或新建' }}
      pagination={{ current: filters.pageNo, pageSize: filters.pageSize, total: page.total,
        showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: (total) => `共 ${total} 份资料`,
        onChange: (pageNo, pageSize) => setFilters((current) => ({ ...current, pageNo, pageSize })) }} />
  </>;

  return (
    <section className="settings-route-panel memory-page" aria-label="项目记忆库" data-settings-section="review-memory">
      {contextHolder}
      <div className="memory-page-heading">
        <div><Title level={3}>项目记忆库</Title>
          <Paragraph type="secondary">上传资料、维护规范与 Skill，将人工误报整理为可追溯的案例。</Paragraph></div>
      </div>
      <Tabs aria-label="项目记忆库页签" activeKey={activeTab}
        items={[{ key: 'upload', label: '上传资料' }, { key: 'library', label: '记忆资料' }, { key: 'cases', label: '案例与打标' }, { key: 'projects', label: '项目关联' }]}
        onChange={(tab) => updateQuery({ tab })} />
      {(capabilityError || capabilities?.schemaReady === false) && <Alert type="warning" showIcon
        title="公共资料创建尚未就绪"
        description={capabilityError ? `无法确认数据库状态：${capabilityError}。请更新后端后重新读取；旧资料和案例仍可维护。` : '请完成 V60 数据库迁移后重新读取；旧资料和案例仍可维护。'}
        action={<Button onClick={() => setCapabilityRetry((value) => value + 1)}>重新检查资料库</Button>} />}
      {projectError && <Alert type="error" title={`项目加载失败：${projectError}`}
        action={<Button onClick={() => setProjectRetry((value) => value + 1)}>重试</Button>} />}
      {isProjects && projectPicker}
      {(isProjects || feedbackView) && rawProjectId && !projectId && <Alert type="warning" title="项目参数无效，请重新选择项目。" />}
      {activeTab === 'upload' ? <MemoryUploadPanel key={uploadReset}
        libraryReady={capabilities?.schemaReady === true}
        onDirtyChange={handleUploadDirty} onBusyChange={handleUploadBusy} onSaved={handleSaved}
        onPreview={(source) => openDrawer({ mode: 'view', sourceId: source.id, library: true })} /> : isProjects ? (
        !projectId ? <Empty className="memory-empty" description="先选择项目，再配置使用资料" /> : <>
          <Title level={4} className="memory-top-space">已关联资料</Title>
          <MemoryProjectBindings key={projectId} projectId={projectId} refresh={refresh}
              onBusyChange={handleBusy}
              memoryEnabled={projectSettings?.projectId === projectId ? projectSettings.settings?.enabled : null}
              projectLabel={projectLabel} onOpen={openDrawer} onAdd={() => openDrawer({ mode: 'candidates' })} />
          <Collapse className="memory-top-space" activeKey={projectFeedbackOpen ? ['feedbacks'] : []}
            onChange={(keys) => setProjectFeedbackOpen(keys.includes('feedbacks'))}
            items={[{ key: 'feedbacks', label: '更多信息 · 本项目待确认反馈', children: projectFeedbackOpen &&
              <MemoryFeedbackList key={projectId} projectId={projectId} refresh={refresh}
                onOpen={(feedbackId) => openDrawer({ mode: 'feedback', feedbackId })} /> }]} />
          {isProjects && <Collapse
            className="memory-top-space"
            activeKey={legacyOpen ? ['legacy'] : []}
            onChange={(keys) => setLegacyOpen(keys.includes('legacy'))}
            items={[
              {
                key: 'legacy',
                label: '更多信息 · 旧项目策略（只读）',
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
      ) : activeTab === 'cases' ? <>
        <Paragraph type="secondary">人工确认的误报案例会自动关联原项目，无需再手动添加；不会跨项目共享，也不会自动开启项目记忆。</Paragraph>
        <Tabs aria-label="案例与打标视图" activeKey={caseTab}
          items={[{ key: 'feedbacks', label: '待整理打标' }, { key: 'saved', label: '已沉淀案例' }]}
          onChange={(next) => requestLeave(() => setCaseTab(next))} />
        {feedbackView ? <MemoryFeedbackList key={`global-${projectId}`} globalView projectId={projectId} refresh={refresh}
          projectOptions={projectOptions} projectLoading={projectLoading} onProjectSearch={setProjectSearch} projectLabel={projectLabel}
          onOpen={(feedbackId, actualProjectId) => openDrawer({ mode: 'feedback', feedbackId, projectId: String(actualProjectId) })} /> : sourceList}
      </> : sourceList}
      {drawer?.mode === 'feedback' ? (
        <MemoryFeedbackDrawer key={`${drawer.projectId || projectId}-${drawer.key}`} projectId={drawer.projectId || projectId}
          feedbackId={drawer.feedbackId} onClose={() => requestLeave(() => {})}
          onDirtyChange={handleDirty} onBusyChange={handleBusy} onSaved={handleSaved} />
      ) : drawer?.mode === 'projects' ? (
        <MemorySourceProjectsDrawer key={drawer.key} initial={drawer}
          projectLabel={projectLabel} projectOptions={projectOptions} projectLoading={projectLoading}
          projectError={projectError} onProjectSearch={setProjectSearch}
          onClose={() => requestLeave(() => {})} onDirtyChange={handleDirty} onBusyChange={handleBusy} onSaved={handleSaved} />
      ) : drawer && ['candidates', 'binding'].includes(drawer.mode) ? (
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
            projectId={drawer.projectId || (isProjects ? projectId : undefined)}
            projectName={drawer.projectId ? projectLabel(drawer.projectId) : projectName}
            ownerOptions={isProjects ? undefined : projectOptions}
            ownerLoading={projectLoading}
            onOwnerSearch={setProjectSearch}
            initial={drawer}
            libraryReady={capabilities?.schemaReady === true}
            onClose={() => activeTab === 'upload' ? closeUploadPreview() : requestLeave(() => {})}
            onDirtyChange={handleDirty}
            onBusyChange={handleBusy}
            onSaved={handleSaved}
            onLoaded={onSourceLoaded}
            projectLabel={projectLabel}
            onViewFeedback={(feedbackId) => requestLeave(() => openDrawer({ mode: 'feedback', feedbackId, projectId: drawer.projectId || projectId }))}
            onManageBinding={(source) =>
              requestLeave(() => openDrawer({ mode: isProjects ? 'binding' : 'projects', source, projectId: isProjects ? projectId : source.projectId == null ? null : String(source.projectId) }))
            }
          />
        )
      )}
    </section>
  );
}
