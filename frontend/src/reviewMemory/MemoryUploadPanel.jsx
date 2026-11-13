import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Collapse, Form, Input, Select, Space, Table, Tag, Typography, Upload } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import { uploadSource } from './api.js';
import { allowsCore, blankEntry, DOCUMENT_ERRORS, KIND_OPTIONS, labelFor, TARGET_TYPE_OPTIONS, uploadProblem } from './model.js';
import MemoryEntryFields from './MemoryEntryFields.jsx';

const { Paragraph, Text, Title } = Typography;
const kinds = KIND_OPTIONS.filter((item) => ['STANDARD', 'SKILL', 'ARCHITECTURE'].includes(item.value));
const targets = [{ value: '', label: '不限' }, ...TARGET_TYPE_OPTIONS];
const states = { pending: '待上传', uploading: '上传与解析中', succeeded: '已上传（生成草稿）', failed: '上传失败', unknown: '结果待确认' };

export default function MemoryUploadPanel({
  libraryReady, onDirtyChange, onBusyChange, onSaved, onPreview
}) {
  const [metadata, setMetadata] = useState({ kind: 'STANDARD', title: '', description: '' });
  const [labels, setLabels] = useState(() => blankEntry('STANDARD'));
  const [rows, setRows] = useState([]);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState(null);
  const controller = useRef(null);
  const mounted = useRef(true);
  const running = useRef(false);
  const stop = useRef(false);
  const dirty = touched || rows.some((row) => row.status !== 'succeeded');

  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => {
    mounted.current = false;
    stop.current = true;
    controller.current?.abort();
    onDirtyChange(false);
    onBusyChange(null);
  }, [onDirtyChange, onBusyChange]);
  useEffect(() => { mounted.current = true; }, []);

  function changeMetadata(patch) {
    setMetadata((current) => ({ ...current, ...patch }));
    setTouched(true);
  }

  function changeRow(id, patch) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row));
  }

  function addFiles(files) {
    setRows((current) => {
      if (current.length + files.length > 20 || [...current.map((row) => row.file), ...files].reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) {
        setError(new Error('队列最多 20 个文件、合计 50 MiB；本次选择未添加，请减少文件后重选。'));
        return current;
      }
      setError(null);
      return [...current, ...files.map((file) => ({ id: crypto.randomUUID(), file, kind: null, targetType: null, status: 'pending' }))];
    });
  }

  async function submit(onlyId) {
    if (running.current) return;
    const selected = rows.filter((row) => onlyId ? row.id === onlyId && row.status === 'failed' : row.status === 'pending');
    if (!libraryReady || !selected.length) {
      setError(new Error(!libraryReady ? '公共资料创建尚未就绪，请完成迁移并重新读取。' : '没有待上传文件；失败项请逐项检查后重试。'));
      return;
    }
    const { heading: _heading, content: _content, ...scope } = labels;
    const batch = selected.map((row) => {
      const kind = row.kind || metadata.kind;
      return { ...row, metadata: { ...metadata, ...scope, kind,
        targetType: row.targetType === null ? labels.targetType : row.targetType || null,
        loadMode: allowsCore(kind) ? scope.loadMode : 'ON_DEMAND',
        title: metadata.title.trim() || row.file.name } };
    });
    running.current = true;
    stop.current = false;
    setBusy(true); setStopping(false); setTouched(false);
    onBusyChange('upload');
    setError(null);
    try {
      for (const row of batch) {
        if (stop.current || !mounted.current) break;
        const problem = uploadProblem(row.file, row.metadata.kind);
        if (problem) { changeRow(row.id, { status: 'failed', error: problem }); continue; }
        changeRow(row.id, { status: 'uploading', error: null, submitted: row.metadata });
        controller.current = new AbortController();
        try {
          const source = await uploadSource(null, row.file, row.metadata, controller.current.signal);
          if (!source?.id || source.projectId !== null || source.assetScope !== 'LIBRARY') throw new Error('响应缺少有效公共草稿信息');
          if (!mounted.current) break;
          changeRow(row.id, { status: 'succeeded', source });
          onSaved();
        } catch (err) {
          if (!mounted.current) break;
          const definite = err.status >= 400 && err.status < 500;
          changeRow(row.id, { status: definite ? 'failed' : 'unknown', error: DOCUMENT_ERRORS[err.code] || err.message });
        }
      }
    } finally {
      running.current = false;
      if (mounted.current) { setBusy(false); setStopping(false); onBusyChange(null); }
    }
  }

  return <div className="memory-upload-panel">
    {error && <Alert type="error" showIcon title="上传未完成，文件与设置已保留"
      description={DOCUMENT_ERRORS[error.code] || error.message} />}
    <div className="memory-upload-layout">
      <Card className="memory-upload-drop-card">
        <Upload.Dragger name="file" multiple showUploadList={false} disabled={busy}
          accept=".md,.txt,.docx,.pdf"
          beforeUpload={(file, files) => {
            if (file === files[0]) addFiles(files);
            return false;
          }}>
          <CloudUploadOutlined className="memory-upload-icon" />
          <Title level={3}>上传记忆资料</Title>
          <Paragraph>拖拽文件到此处，或点击选择多个文件</Paragraph>
          <Text type="secondary">最多 20 个文件、合计 50 MiB，逐份上传并生成草稿</Text>
        </Upload.Dragger>
        <div className="memory-upload-footer">
          <Text type="secondary">MD / TXT ≤ 1 MiB · DOCX / PDF ≤ 5 MiB<br />Skill 仅支持 Markdown；PDF 最多 100 页，不支持扫描件 OCR。</Text>
          <Space wrap>
            <Button aria-label="开始上传" type="primary" disabled={busy || !libraryReady} onClick={() => submit()}>开始上传</Button>
            {busy && <Button aria-label="停止后续上传" disabled={stopping} onClick={() => { stop.current = true; setStopping(true); }}>停止后续上传</Button>}
          </Space>
        </div>
        <Paragraph type="secondary">停止后当前文件继续处理。刷新或离开不会保留本地文件队列；上传成功后请逐份核对发布。</Paragraph>
      </Card>
      <Card title="批次默认设置" className="memory-upload-settings">
        <Form layout="vertical" disabled={busy}>
          <Form.Item label="资料类型">
            <Select aria-label="资料类型" value={metadata.kind}
              options={kinds}
              onChange={(kind) => {
                changeMetadata({ kind });
                setLabels((current) => ({ ...current, loadMode: allowsCore(kind) ? current.loadMode : 'ON_DEMAND' }));
              }} />
          </Form.Item>
          <Form.Item label="适用端" extra="“不限”包含所有端；“通用”是独立端。">
            <Select aria-label="适用端" value={labels.targetType || ''}
              options={[{ value: '', label: '不限' }, ...TARGET_TYPE_OPTIONS]}
              onChange={(targetType) => { setLabels((current) => ({ ...current, targetType: targetType || null })); setTouched(true); }} />
          </Form.Item>
        </Form>
        <Collapse items={[{ key: 'advanced', label: '高级设置', children: <>
          <Form layout="vertical" disabled={busy}>
            <Form.Item label="自定义标题"><Input aria-label="资料标题" maxLength={255} value={metadata.title}
              placeholder="默认采用各自文件名" onChange={(event) => changeMetadata({ title: event.target.value })} /></Form.Item>
            <Form.Item label="简介"><Input.TextArea aria-label="资料简介" maxLength={4000} value={metadata.description}
              onChange={(event) => changeMetadata({ description: event.target.value })} /></Form.Item>
          </Form>
          <MemoryEntryFields kind={metadata.kind} content={false} showTargetType={false} value={labels}
            disabled={busy} onChange={(value) => { setLabels(value); setTouched(true); }} />
        </> }]} />
        <Paragraph type="secondary" className="memory-top-space">上传无需选择项目。核对并发布后，到“项目关联”选择使用项目；不会自动关联或开启记忆。</Paragraph>
      </Card>
    </div>
    <Card title={`文件队列（${rows.length} / 20）`} className="memory-top-space"
      extra={<Button disabled={busy || !rows.length} onClick={() => { setRows([]); setTouched(false); setError(null); }}>清空队列</Button>}>
      <Table rowKey="id" pagination={false} scroll={{ x: 1200 }} dataSource={rows}
        locale={{ emptyText: '尚未选择文件，点击或拖拽到上方上传区' }}
        columns={[
          { title: '文件名', width: 220, render: (_, row) => row.file.name },
          { title: '大小', width: 100, render: (_, row) => `${(row.file.size / 1024).toFixed(1)} KiB` },
          { title: '资料类型', width: 150, render: (_, row) => ['pending', 'failed'].includes(row.status)
            ? <Select aria-label={`${row.file.name} 资料类型`} disabled={busy} value={row.kind || ''} style={{ width: '100%' }}
              options={[{ value: '', label: '跟随批次' }, ...kinds]} onChange={(kind) => changeRow(row.id, { kind: kind || null })} />
            : labelFor(kinds, row.submitted?.kind || row.kind || metadata.kind) },
          { title: '适用端', width: 150, render: (_, row) => ['pending', 'failed'].includes(row.status)
            ? <Select aria-label={`${row.file.name} 适用端`} disabled={busy} value={row.targetType === null ? 'DEFAULT' : row.targetType} style={{ width: '100%' }}
              options={[{ value: 'DEFAULT', label: '跟随批次' }, ...targets]} onChange={(targetType) => changeRow(row.id, { targetType: targetType === 'DEFAULT' ? null : targetType })} />
            : labelFor(targets, row.submitted?.targetType || '') },
          { title: '状态 / 错误', width: 300, render: (_, row) => <>
            <Tag color={row.status === 'succeeded' ? 'green' : ['unknown', 'failed'].includes(row.status) ? 'orange' : 'default'}>{states[row.status]}</Tag>
            {row.error && <div className="memory-feedback-summary">{row.error}</div>}
            {row.status === 'pending' && <Text type="danger">{uploadProblem(row.file, row.kind || metadata.kind)}</Text>}
            {row.status === 'unknown' && <div>请先到记忆资料核对是否已生成草稿，不能仅凭同名认定结果。本项不直接重试。</div>}
            {row.source && <div>草稿 #{row.source.id}</div>}
          </> },
          { title: '操作', width: 210, render: (_, row) => <Space wrap>
            {row.source && <Button disabled={busy} onClick={() => onPreview(row.source)}>核对草稿</Button>}
            {row.status === 'failed' && <Button disabled={busy || !libraryReady} onClick={() => submit(row.id)}>重试此文件</Button>}
            <Button disabled={busy} onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}>移除</Button>
          </Space> }
        ]} />
    </Card>
  </div>;
}
