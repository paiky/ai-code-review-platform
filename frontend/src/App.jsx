import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  Layout,
  List,
  message,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography
} from 'antd';
import { ArrowLeftOutlined, ReloadOutlined, SearchOutlined, SettingOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { fetchApi, riskColor, statusColor } from './api.js';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const dbFineTypes = new Set(['DB_SCHEMA', 'DB_SQL', 'ORM_MAPPING', 'ENTITY_MODEL', 'DATA_MIGRATION']);

function JsonBlock({ value }) {
  return <pre className="json-block">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function confidenceColor(value) {
  if (value === 'HIGH') return 'red';
  if (value === 'MEDIUM') return 'orange';
  if (value === 'LOW') return 'green';
  return 'default';
}

function TaskList({ onOpen }) {
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ pageNo: 1, pageSize: 20, total: 0 });
  const [error, setError] = useState(null);

  const load = async (next = {}) => {
    const pageNo = next.pageNo ?? pagination.pageNo;
    const pageSize = next.pageSize ?? pagination.pageSize;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ pageNo, pageSize });
      if (keyword.trim()) params.set('keyword', keyword.trim());
      const data = await fetchApi(`/api/review-tasks?${params.toString()}`);
      setTasks(data.items || []);
      setPagination({ pageNo: data.pageNo, pageSize: data.pageSize, total: data.total });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load({ pageNo: 1 });
  }, []);

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '项目', dataIndex: 'projectName', ellipsis: true },
    { title: 'MR', dataIndex: 'externalSourceId', width: 90, render: value => value ? `!${value}` : '-' },
    { title: '分支', width: 260, render: (_, row) => <Text>{row.sourceBranch || '-'}{' -> '}{row.targetBranch || '-'}</Text> },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <Tag color={statusColor(value)}>{value || '-'}</Tag> },
    { title: '风险', dataIndex: 'riskLevel', width: 110, render: value => <Tag color={riskColor(value)}>{value || '-'}</Tag> },
    { title: '风险项', dataIndex: 'riskItemCount', width: 90, render: value => value ?? 0 },
    { title: '创建时间', dataIndex: 'createdAt', width: 180 },
    { title: '操作', width: 90, render: (_, row) => <Button type="link" onClick={() => onOpen(row.id)}>详情</Button> }
  ];

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <Title level={3}>审查任务</Title>
          <Text type="secondary">查看 GitLab MR 触发的变更风险审查记录</Text>
        </div>
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="项目、分支或 MR"
            value={keyword}
            onChange={event => setKeyword(event.target.value)}
            onPressEnter={() => load({ pageNo: 1 })}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load({ pageNo: 1 })}>刷新</Button>
          <Button type="primary" onClick={() => load({ pageNo: 1 })}>搜索</Button>
        </Space>
      </div>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={tasks}
          pagination={{
            current: pagination.pageNo,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (pageNo, pageSize) => load({ pageNo, pageSize })
          }}
        />
      </Card>
    </div>
  );
}

function RiskCardView({ riskCard }) {
  if (!riskCard) return <Empty description="暂无风险卡片" />;

  const resources = riskCard.affectedResources || [];
  const riskItems = riskCard.riskItems || [];
  const checks = riskCard.recommendedChecks || [];
  const roles = riskCard.suggestedReviewRoles || [];

  const resourceColumns = [
    { title: '类型', dataIndex: 'resourceType', width: 130 },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '文件', dataIndex: 'filePath', ellipsis: true },
    { title: '操作', dataIndex: 'operation', width: 110 }
  ];

  const evidenceColumns = [
    { title: '文件', dataIndex: 'filePath', ellipsis: true },
    { title: '规则', dataIndex: 'matcher', width: 180, ellipsis: true },
    {
      title: '片段',
      dataIndex: 'snippet',
      ellipsis: true,
      render: value => value ? <Text code className="evidence-snippet">{value}</Text> : '-'
    }
  ];

  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Space direction="vertical" size="small">
          <Tag color={riskColor(riskCard.riskLevel)}>{riskCard.riskLevel}</Tag>
          <Paragraph>{riskCard.summary}</Paragraph>
          <Space wrap>{roles.map(role => <Tag key={role}>{role}</Tag>)}</Space>
        </Space>
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="推荐检查">
            <List dataSource={checks} locale={{ emptyText: '暂无推荐检查项' }} renderItem={item => <List.Item>{item}</List.Item>} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="受影响资源">
            <Table rowKey={(row, index) => `${row.resourceType}-${row.name}-${index}`} size="small" columns={resourceColumns} dataSource={resources} pagination={false} />
          </Card>
        </Col>
      </Row>
      <Card title="风险项">
        <Collapse
          items={riskItems.map(item => ({
            key: item.riskId,
            label: (
              <Space className="risk-item-heading" wrap>
                <Tag color={riskColor(item.riskLevel)}>{item.riskLevel}</Tag>
                <Tag color={dbFineTypes.has(item.category) ? 'blue' : 'default'}>{item.category}</Tag>
                {item.confidence && <Tag color={confidenceColor(item.confidence)}>置信度 {item.confidence}</Tag>}
                <Text strong>{item.title}</Text>
              </Space>
            ),
            children: (
              <Space direction="vertical" className="full-width">
                <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                  <Descriptions.Item label="规则">{item.ruleCode || '-'}</Descriptions.Item>
                  <Descriptions.Item label="类型">{item.category || '-'}</Descriptions.Item>
                  <Descriptions.Item label="风险等级">{item.riskLevel || '-'}</Descriptions.Item>
                  <Descriptions.Item label="置信度">{item.confidence || '-'}</Descriptions.Item>
                </Descriptions>
                <Paragraph>{item.description}</Paragraph>
                {item.reason && <Alert type="info" showIcon message="命中原因" description={item.reason} />}
                {item.impact && <Text type="secondary">{item.impact}</Text>}
                {(item.relatedSignals || []).length > 0 && (
                  <Space direction="vertical" size="small">
                    <Text strong>关联信号</Text>
                    <Space wrap>{item.relatedSignals.map(signal => <Tag key={signal}>{signal}</Tag>)}</Space>
                  </Space>
                )}
                <Divider />
                <Text strong>命中证据</Text>
                <Table
                  rowKey={(row, index) => `${row.filePath}-${row.matcher}-${index}`}
                  size="small"
                  columns={evidenceColumns}
                  dataSource={item.evidences || []}
                  pagination={false}
                  locale={{ emptyText: '暂无命中证据' }}
                />
                <Divider />
                <Text strong>检查项</Text>
                <List size="small" dataSource={item.recommendedChecks || []} renderItem={check => <List.Item>{check}</List.Item>} />
              </Space>
            )
          }))}
        />
      </Card>
    </Space>
  );
}

function AnalysisView({ changeAnalysis }) {
  if (!changeAnalysis) return <Empty description="暂无分析结果" />;
  const files = changeAnalysis.changedFiles || [];
  const resources = changeAnalysis.impactedResources || [];
  return (
    <Space direction="vertical" size="large" className="full-width">
      <Card>
        <Paragraph>{changeAnalysis.summary}</Paragraph>
        <Space wrap>{(changeAnalysis.changeTypes || []).map(type => <Tag color="blue" key={type}>{type}</Tag>)}</Space>
      </Card>
      <Card title="变更文件">
        <Table
          rowKey={(row, index) => `${row.path}-${index}`}
          size="small"
          dataSource={files}
          pagination={false}
          columns={[
            { title: '文件', dataIndex: 'path', ellipsis: true },
            { title: '变更', dataIndex: 'changeType', width: 120 },
            { title: '命中类型', dataIndex: 'matchedChangeTypes', width: 220, render: values => <Space wrap>{(values || []).map(value => <Tag key={value}>{value}</Tag>)}</Space> }
          ]}
        />
      </Card>
      <Card title="影响资源">
        <Table
          rowKey={(row, index) => `${row.resourceType}-${row.name}-${index}`}
          size="small"
          dataSource={resources}
          pagination={false}
          columns={[
            { title: '类型', dataIndex: 'resourceType', width: 130 },
            { title: '名称', dataIndex: 'name', ellipsis: true },
            { title: '文件', dataIndex: 'filePath', ellipsis: true }
          ]}
        />
      </Card>
    </Space>
  );
}

function TaskDetail({ taskId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const taskDetail = await fetchApi(`/api/review-tasks/${taskId}`);
      setDetail(taskDetail);
      try {
        const taskResult = await fetchApi(`/api/review-tasks/${taskId}/result`);
        setResult(taskResult);
      } catch {
        setResult(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [taskId]);

  const tabItems = useMemo(() => [
    { key: 'risk', label: '风险卡片', children: <RiskCardView riskCard={result?.riskCard} /> },
    { key: 'analysis', label: '分析结果', children: <AnalysisView changeAnalysis={result?.changeAnalysis} /> },
    { key: 'event', label: '原始事件摘要', children: <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card title="changedFiles 摘要"><JsonBlock value={detail?.changedFilesSummary} /></Card></Col><Col xs={24} lg={12}><Card title="raw payload"><JsonBlock value={detail?.rawPayload} /></Card></Col></Row> }
  ], [detail, result]);

  return (
    <div className="page-shell">
      <Space className="detail-toolbar">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        {detail ? (
          <Space direction="vertical" size="large" className="full-width">
            <Card>
              <div className="detail-title-row">
                <div>
                  <Title level={3}>{detail.projectName} MR !{detail.mrId}</Title>
                  <Text type="secondary">{detail.sourceBranch || '-'}{' -> '}{detail.targetBranch || '-'}</Text>
                </div>
                <Space>
                  <Tag color={statusColor(detail.status)}>{detail.status}</Tag>
                  <Tag color={riskColor(detail.riskLevel)}>{detail.riskLevel || '-'}</Tag>
                </Space>
              </div>
              <Divider />
              <Descriptions column={{ xs: 1, md: 2, xl: 3 }} size="small">
                <Descriptions.Item label="任务 ID">{detail.id}</Descriptions.Item>
                <Descriptions.Item label="GitLab 项目">{detail.gitProjectId}</Descriptions.Item>
                <Descriptions.Item label="触发类型">{detail.triggerType}</Descriptions.Item>
                <Descriptions.Item label="作者">{detail.authorName || detail.authorUsername || '-'}</Descriptions.Item>
                <Descriptions.Item label="模板">{detail.templateCode}</Descriptions.Item>
                <Descriptions.Item label="事件时间">{detail.eventTime || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
            <Tabs items={tabItems} />
          </Space>
        ) : !loading ? <Empty description="任务不存在" /> : null}
      </Spin>
    </div>
  );
}


function TemplateConfig() {
  const [templates, setTemplates] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [messageApi, contextHolder] = message.useMessage();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [templateData, projectData] = await Promise.all([
        fetchApi('/api/rule-templates'),
        fetchApi('/api/projects')
      ]);
      setTemplates(Array.isArray(templateData) ? templateData : (templateData.items || []));
      setProjects(Array.isArray(projectData) ? projectData : (projectData.items || []));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateProjectTemplate = async (projectId, templateCode) => {
    try {
      await fetchApi(`/api/projects/${projectId}/default-template`, {
        method: 'PUT',
        body: JSON.stringify({ templateCode })
      });
      messageApi.success('默认模板已更新');
      load();
    } catch (err) {
      messageApi.error(err.message);
    }
  };

  const templateOptions = templates.map(template => ({
    label: `${template.templateName} (${template.templateCode})`,
    value: template.templateCode
  }));

  return (
    <div className="page-shell">
      {contextHolder}
      <div className="page-heading">
        <div>
          <Title level={3}>模板配置</Title>
          <Text type="secondary">配置项目默认模板，查看模板启用规则和推荐检查项</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </div>
      {error && <Alert className="section-gap" type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card title="项目默认模板">
              <Table
                rowKey="id"
                size="small"
                dataSource={projects}
                pagination={false}
                columns={[
                  { title: '项目', dataIndex: 'name', ellipsis: true },
                  { title: 'GitLab', dataIndex: 'gitProjectId', width: 110 },
                  {
                    title: '默认模板',
                    dataIndex: 'defaultTemplateCode',
                    width: 260,
                    render: (value, row) => (
                      <Select
                        className="full-width"
                        value={value}
                        options={templateOptions}
                        onChange={next => updateProjectTemplate(row.id, next)}
                      />
                    )
                  }
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card title="审查模板">
              <Collapse
                items={templates.map(template => ({
                  key: template.templateCode,
                  label: <Space><Text strong>{template.templateName}</Text><Tag>{template.targetType}</Tag><Tag color="blue">{template.templateCode}</Tag></Space>,
                  children: (
                    <Space direction="vertical" className="full-width">
                      <Paragraph>{template.description}</Paragraph>
                      <Text strong>启用规则</Text>
                      <Space wrap>{(template.enabledRuleCodes || []).map(code => <Tag key={code}>{code}</Tag>)}</Space>
                      <Divider />
                      <Text strong>模板推荐检查项</Text>
                      <List size="small" dataSource={template.recommendedChecks || []} renderItem={item => <List.Item>{item}</List.Item>} />
                    </Space>
                  )
                }))}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
export default function App() {
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [view, setView] = useState('tasks');

  const openTasks = () => {
    setSelectedTaskId(null);
    setView('tasks');
  };

  const openTemplates = () => {
    setSelectedTaskId(null);
    setView('templates');
  };

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="brand">AI 变更风险审查平台</div>
        <Space className="top-nav">
          <Button icon={<UnorderedListOutlined />} type={view === 'tasks' ? 'primary' : 'default'} onClick={openTasks}>任务</Button>
          <Button icon={<SettingOutlined />} type={view === 'templates' ? 'primary' : 'default'} onClick={openTemplates}>模板配置</Button>
        </Space>
      </Header>
      <Content>
        {selectedTaskId ? (
          <TaskDetail taskId={selectedTaskId} onBack={openTasks} />
        ) : view === 'templates' ? (
          <TemplateConfig />
        ) : (
          <TaskList onOpen={setSelectedTaskId} />
        )}
      </Content>
    </Layout>
  );
}
