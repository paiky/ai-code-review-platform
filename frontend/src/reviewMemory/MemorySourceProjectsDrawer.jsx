import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Drawer, Modal, Select, Table, Tag, Typography } from 'antd';
import { getSource, listSourceProjects } from './api.js';
import { labelFor, STATE_LABELS, TARGET_TYPE_OPTIONS, sourceUseProblem } from './model.js';
import MemoryAssociationDrawer from './MemoryAssociationDrawer.jsx';

const { Paragraph, Text, Title } = Typography;

export default function MemorySourceProjectsDrawer({
  initial, projectLabel, projectOptions, projectLoading, projectError, onProjectSearch,
  onClose, onDirtyChange, onBusyChange, onSaved
}) {
  const [source, setSource] = useState(initial.source);
  const [filters, setFilters] = useState({ state: 'ACTIVE', pageNo: 1, pageSize: 20 });
  const [page, setPage] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [selectedProject, setSelectedProject] = useState('');
  const [editor, setEditor] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(null);
  const handleDirty = useCallback((value) => { setDirty(value); onDirtyChange(value); }, [onDirtyChange]);
  const handleBusy = useCallback((value) => { setBusy(value); onBusyChange(value); }, [onBusyChange]);
  const saved = () => { setRefresh((v) => v + 1); onSaved(); };

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      getSource(initial.source.projectId, initial.source.id, controller.signal),
      listSourceProjects(initial.source.id, filters, controller.signal)
    ]).then(([current, relations]) => {
      if (controller.signal.aborted) return;
      setSource(current);
      setPage(relations);
    }).catch((err) => {
      if (!controller.signal.aborted) setError(err.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [initial.source.id, initial.source.projectId, filters, refresh]);

  function back() {
    if (busy) return;
    const leave = () => { setEditor(null); setRefresh((v) => v + 1); };
    if (!dirty) leave();
    else Modal.confirm({ title: '放弃未保存的使用范围？', okText: '放弃修改', cancelText: '继续编辑', onOk: leave });
  }

  const addProblem = !selectedProject ? '请选择使用项目'
    : sourceUseProblem(source, selectedProject, source.entries?.some((entry) => entry.state === 'ACTIVE'));

  if (editor) return (
    <MemoryAssociationDrawer
      key={editor.projectId}
      projectId={editor.projectId} projectName={projectLabel(editor.projectId)}
      initial={{ mode: 'binding', source: { ...source, binding: editor.binding } }}
      projectLabel={projectLabel} onClose={onClose} onBack={back}
      onDirtyChange={handleDirty} onBusyChange={handleBusy} onSaved={saved}
    />
  );

  return (
    <Drawer open title="管理使用项目" size="min(960px, 100vw)" styles={{ wrapper: { maxWidth: '100vw', minWidth: 0 } }} className="memory-source-drawer" onClose={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}>
      <Title level={4}>{source.title}</Title>
      <Paragraph>归属项目：{projectLabel(source.projectId)} · {STATE_LABELS[source.state]} · {source.visibility === 'SHARED' ? '共享资料' : '项目私有'}</Paragraph>
      <Alert type="info" showIcon title="每次保存一个项目的使用关系"
        description="添加不代表本次会加载，也不会自动共享、发布或开启项目记忆。已保存项目保留，下一项目保存失败不会撤销之前的结果。" />
      {error && <Alert type="error" className="memory-top-space" title="使用项目加载失败" description={error}
        action={<Button onClick={() => setRefresh((v) => v + 1)}>重试</Button>} />}
      <Title level={5}>添加使用项目</Title>
      <div className="memory-toolbar">
        <Select aria-label="添加使用项目" className="memory-owner-picker" value={selectedProject || undefined}
          placeholder="搜索并选择项目" loading={projectLoading}
          showSearch={{ filterOption: false, onSearch: onProjectSearch }}
          options={selectedProject && !projectOptions.some((item) => item.value === selectedProject)
            ? [{ value: selectedProject, label: projectLabel(selectedProject) }, ...projectOptions] : projectOptions}
          onChange={setSelectedProject} />
        <Button type="primary" disabled={loading || Boolean(error) || Boolean(addProblem)}
          onClick={() => setEditor({ projectId: selectedProject, binding: null })}>配置该项目范围</Button>
      </div>
      {projectError && <Alert type="error" title={`项目搜索失败：${projectError}`} />}
      {addProblem && <Paragraph type="secondary">{addProblem}</Paragraph>}
      <div className="memory-toolbar memory-top-space">
        <Select aria-label="项目关系状态" value={filters.state}
          options={[{ value: 'ACTIVE', label: '已添加' }, { value: 'DISABLED', label: '已移除' }]}
          onChange={(state) => setFilters((v) => ({ ...v, state, pageNo: 1 }))} />
        <Button loading={loading} onClick={() => setRefresh((v) => v + 1)}>刷新关系</Button>
        <Text type="secondary">来源 v{page.sourceVersion || source.version} · 每页最多 100 个关系</Text>
      </div>
      <Table rowKey="id" loading={loading} dataSource={error ? [] : page.items} scroll={{ x: 650 }}
        columns={[
          { title: '使用项目', dataIndex: 'projectId', render: projectLabel },
          { title: '关系', dataIndex: 'state', render: (state) => <Tag>{state === 'ACTIVE' ? '已添加' : '已移除'}</Tag> },
          { title: '该项目适用范围', render: (_, row) => <>{row.targetType ? labelFor(TARGET_TYPE_OPTIONS, row.targetType) : '所有端'}<div>{row.pathGlobs.join('、') || '所有路径'}</div></> },
          { title: '操作', render: (_, row) => <Button disabled={loading || Boolean(error)} onClick={() => setEditor({ projectId: String(row.projectId), binding: row })}>{row.state === 'ACTIVE' ? '修改范围 / 移除' : '查看 / 恢复'}</Button> }
        ]}
        locale={{ emptyText: error ? '加载失败，请重试' : '暂无该状态的使用项目' }}
        pagination={{ current: filters.pageNo, pageSize: filters.pageSize, total: page.total, showSizeChanger: true,
          pageSizeOptions: [20, 50, 100], onChange: (pageNo, pageSize) => setFilters((v) => ({ ...v, pageNo, pageSize })) }} />

    </Drawer>
  );
}
