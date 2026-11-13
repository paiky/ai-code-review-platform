import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Collapse, Form, Input, Select, Table, Tag, Typography, Upload } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import { uploadSource } from './api.js';
import { allowsCore, blankEntry, DOCUMENT_ERRORS, KIND_OPTIONS, labelFor, TARGET_TYPE_OPTIONS, uploadProblem } from './model.js';
import MemoryEntryFields from './MemoryEntryFields.jsx';

const { Paragraph, Text, Title } = Typography;

export default function MemoryUploadPanel({
  projectOptions, projectLoading, onProjectSearch, projectLabel, onDirtyChange, onBusyChange, onSaved, onPreview
}) {
  const [projectId, setProjectId] = useState('');
  const [metadata, setMetadata] = useState({ kind: 'STANDARD', title: '', description: '' });
  const [labels, setLabels] = useState(() => blankEntry('STANDARD'));
  const [file, setFile] = useState(null);
  const [saved, setSaved] = useState(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const controller = useRef(null);
  const mounted = useRef(true);
  const problem = file && uploadProblem(file, metadata.kind);

  useEffect(() => { onDirtyChange(touched); }, [touched, onDirtyChange]);
  useEffect(() => () => {
    mounted.current = false;
    controller.current?.abort();
    onDirtyChange(false);
    onBusyChange(null);
  }, [onDirtyChange, onBusyChange]);
  useEffect(() => { mounted.current = true; }, []);

  function changeMetadata(patch) {
    setMetadata((current) => ({ ...current, ...patch }));
    setTouched(true);
  }

  async function submit() {
    if (busy) return;
    if (!projectId || !file || problem) {
      setError(new Error(!projectId ? '请选择归属项目。' : problem || '请先选择一个文件。'));
      return;
    }
    setBusy(true);
    onBusyChange('upload');
    setError(null);
    controller.current = new AbortController();
    const { heading: _heading, content: _content, ...scope } = labels;
    try {
      const source = await uploadSource(projectId, file, {
        ...metadata, ...scope, title: metadata.title.trim() || file.name
      }, controller.current.signal);
      if (!mounted.current) return;
      setSaved({ source, filename: file.name, size: file.size });
      setFile(null);
      setTouched(false);
      onDirtyChange(false);
      onSaved();
      onPreview(source);
    } catch (err) {
      if (mounted.current && err.name !== 'AbortError') setError(err);
    } finally {
      if (mounted.current) { setBusy(false); onBusyChange(null); }
    }
  }

  return <div className="memory-upload-panel">
    {error && <Alert type="error" showIcon title="上传未完成，文件与设置已保留"
      description={DOCUMENT_ERRORS[error.code] || error.message} />}
    <div className="memory-upload-layout">
      <Card className="memory-upload-drop-card">
        <Upload.Dragger name="file" multiple={false} maxCount={1} showUploadList={false} disabled={busy}
          accept={metadata.kind === 'SKILL' ? '.md' : '.md,.txt,.docx,.pdf'}
          beforeUpload={(next) => {
            const nextProblem = uploadProblem(next, metadata.kind);
            if (nextProblem) { setError(new Error(nextProblem)); return Upload.LIST_IGNORE; }
            setFile(next); setError(null); setTouched(true);
            return false;
          }}>
          <CloudUploadOutlined className="memory-upload-icon" />
          <Title level={3}>上传记忆资料</Title>
          <Paragraph>拖拽文件到此处，或点击选择文件</Paragraph>
          <Text type="secondary">每次上传一个文件，支持 MD、TXT、DOCX、文本 PDF</Text>
        </Upload.Dragger>
        <div className="memory-upload-footer">
          <Text type="secondary">MD / TXT ≤ 1 MiB · DOCX / PDF ≤ 5 MiB<br />Skill 仅支持 Markdown；PDF 最多 100 页，不支持扫描件 OCR。</Text>
          <Button aria-label="开始上传" type="primary" loading={busy} onClick={submit}>开始上传</Button>
        </div>
      </Card>
      <Card title="上传设置" className="memory-upload-settings">
        <Form layout="vertical" disabled={busy}>
          <Form.Item label="归属项目" required>
            <Select aria-label="归属项目" placeholder="搜索并选择归属项目" value={projectId || undefined}
              showSearch={{ filterOption: false, onSearch: onProjectSearch }} loading={projectLoading}
              options={projectId && !projectOptions.some((item) => item.value === projectId)
                ? [{ value: projectId, label: projectLabel(projectId) }, ...projectOptions] : projectOptions}
              onChange={(value) => { setProjectId(value); setTouched(true); }} />
          </Form.Item>
          <Form.Item label="资料类型">
            <Select aria-label="资料类型" value={metadata.kind}
              options={KIND_OPTIONS.filter((item) => ['STANDARD', 'SKILL', 'ARCHITECTURE'].includes(item.value))}
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
              placeholder="默认采用文件名" onChange={(event) => changeMetadata({ title: event.target.value })} /></Form.Item>
            <Form.Item label="简介"><Input.TextArea aria-label="资料简介" maxLength={4000} value={metadata.description}
              onChange={(event) => changeMetadata({ description: event.target.value })} /></Form.Item>
          </Form>
          <MemoryEntryFields kind={metadata.kind} content={false} showTargetType={false} value={labels}
            disabled={busy} onChange={(value) => { setLabels(value); setTouched(true); }} />
        </> }]} />
        <Paragraph type="secondary" className="memory-top-space">创建后默认添加到归属项目。上传生成草稿，核对后再发布；不会自动共享或开启记忆。</Paragraph>
      </Card>
    </div>
    <Card title="文件状态" className="memory-top-space">
      {problem && <Alert type="warning" title={problem} />}
      <Table rowKey="name" pagination={false} scroll={{ x: 660 }}
        dataSource={file ? [{ name: file.name, size: file.size }] : saved ? [{ name: saved.filename, size: saved.size, source: saved.source }] : []}
        locale={{ emptyText: '尚未选择文件，点击或拖拽到上方上传区' }}
        columns={[
          { title: '文件名', dataIndex: 'name', width: 240 },
          { title: '大小', dataIndex: 'size', render: (size) => `${(size / 1024).toFixed(1)} KiB` },
          { title: '资料类型', render: (_, row) => labelFor(KIND_OPTIONS, row.source?.kind || metadata.kind) },
          { title: '状态', render: (_, row) => <Tag color={row.source ? 'green' : 'default'}>{row.source ? '已上传（生成草稿）' : busy ? '上传与解析中' : problem || error ? '待检查 / 重试' : '待上传'}</Tag> },
          { title: '操作', render: (_, row) => row.source
            ? <Button onClick={() => onPreview(row.source)}>核对草稿</Button>
            : <Button disabled={busy} onClick={() => { setFile(null); setError(null); }}>移除</Button> }
        ]} />
    </Card>
  </div>;
}
