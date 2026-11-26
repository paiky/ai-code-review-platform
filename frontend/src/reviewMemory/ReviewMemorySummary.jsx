import { useEffect, useState } from 'react';
import { Alert, Button, Collapse, Descriptions, Empty, Space, Spin, Table, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { getRunMemorySummary } from './api.js';
import { KIND_OPTIONS, labelFor, TARGET_TYPE_OPTIONS } from './model.js';
import './reviewMemory.css';

const LOOKUP_LABELS = {
  DISABLED: '未启用', EMPTY: '记忆库为空', NO_MATCH: '无匹配背景',
  LOADED: '已加载背景', PARTIAL_LOOKUP: '部分读取失败'
};
const ADOPTION_LABELS = {
  HISTORICAL: '历史未记录', PENDING: '等待执行结果', AGENT: 'Agent 已完成',
  NOT_LOADED: '未加载新增记忆', STANDARD_FALLBACK: 'Standard 未采用新增记忆', UNAVAILABLE: '执行采用情况不可确认'
};
const REASON_LABELS = {
  CORE_REQUIRED: '必载规范', ON_DEMAND: '按需选择', ISSUE_MATCH: '问题类型匹配',
  PATH_MATCH: '限定适用路径', KEYWORD_MATCH: '关键词匹配'
};
const SKIP_LABELS = {
  PATH_SCOPE: '路径范围未命中', FEEDBACK_STALE: '原反馈已失效', INVALID_ENTRY: '条目校验未通过',
  LEGACY_POLICY_LOADED: '已在旧策略完整加载', DUPLICATE_CONTENT: '相同内容已覆盖',
  LEGACY_TRUNCATED_OVERLAP: '与截断旧策略重叠（仍可加载）', ON_DEMAND_COUNT_BUDGET: '按需条数超限',
  ON_DEMAND_BYTE_BUDGET: '按需字节超限', OPTIONAL_LOOKUP_FAILED: '按需查询失败'
};

export default function ReviewMemorySummary({ projectId, runId, reviewStatus, effectiveEngine, requestRecorded = false }) {
  const [expanded, setExpanded] = useState(false);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    setSummary(null);
    setError(null);
    if (!expanded || !runId || !projectId) return undefined;
    const controller = new AbortController();
    setLoading(true);
    getRunMemorySummary(projectId, runId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setSummary(data); })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, runId, expanded, reviewStatus, effectiveEngine, retry]);

  const snapshot = summary?.snapshot;
  const selected = snapshot?.selected || [];
  const coreCount = selected.filter((item) => item.loadMode === 'CORE').length;
  const adoption = effectiveEngine === 'STANDARD_FALLBACK' ? 'STANDARD_FALLBACK' : summary?.adoption;
  const columns = [
    { title: '当时的资料', width: 230, render: (_, item) => <>
      <div className="memory-snapshot-text">{item.title}</div>
      {item.heading && <div className="memory-snapshot-text">{item.heading}</div>}
      <Link to={`/settings/review-memory?tab=projects&projectId=${encodeURIComponent(projectId)}&sourceId=${item.sourceId}`}>
        查看当前资料 #{item.sourceId}
      </Link>
    </> },
    { title: '类型 / 加载方式', width: 150, render: (_, item) => <>
      <div>{labelFor(KIND_OPTIONS, item.kind)}</div><Tag>{item.loadMode === 'CORE' ? '必载' : '按需'}</Tag>
    </> },
    { title: '冻结版本', width: 185, render: (_, item) => <>
      <div>资料 v{item.sourceVersion} · 章节 v{item.entryVersion}</div>
      <div>关联 v{item.bindingVersion} · {item.ownerProjectId == null ? '公共资料' : `维护项目 #${item.ownerProjectId}`}</div>
      <Typography.Text type="secondary">章节 #{item.entryId} · 关联 #{item.bindingId}</Typography.Text>
    </> },
    { title: '适用范围（摘要）', width: 280, render: (_, item) => <div className="memory-snapshot-text">
      {item.applicability}
      {item.pathCount > 0 && <div>路径示例：{item.pathSample}（共 {item.pathCount} 条）</div>}
    </div> },
    { title: '选择原因', width: 200, render: (_, item) => <Space wrap>
      {(item.selectionReason || []).map((reason) => <Tag key={reason}>{REASON_LABELS[reason] || reason}</Tag>)}
    </Space> }
  ];
  const content = !runId || !projectId ? <Space orientation="vertical" className="full-width">
    {adoption === 'STANDARD_FALLBACK' && <Alert type="warning" showIcon title="最终 Standard 结果未采用新增记忆" />}
    <Empty description="历史任务未记录本次记忆背景" />
  </Space>
    : loading ? <Spin aria-label="正在读取审查背景" />
      : error ? <Alert type="error" showIcon title="审查背景读取失败" description={error}
        action={<Button onClick={() => setRetry((value) => value + 1)}>重试背景读取</Button>} />
        : !summary ? null
          : !summary.recorded || !snapshot ? <Space orientation="vertical" className="full-width">
            {adoption === 'STANDARD_FALLBACK' && <Alert type="warning" showIcon title="最终 Standard 结果未采用新增记忆" />}
            <Empty description="历史任务未记录本次记忆背景；不使用当前资料补造历史" />
          </Space>
            : <Space orientation="vertical" size="middle" className="full-width">
              <Space wrap>
                <Tag color={snapshot.lookupStatus === 'PARTIAL_LOOKUP' ? 'orange' : 'blue'}>
                  {LOOKUP_LABELS[snapshot.lookupStatus] || snapshot.lookupStatus}
                </Tag>
                <Tag color={adoption === 'STANDARD_FALLBACK' ? 'orange' : undefined}>
                  {requestRecorded && selected.length > 0 && adoption !== 'STANDARD_FALLBACK'
                    ? '已随 Agent 首轮请求交付'
                    : ADOPTION_LABELS[adoption] || '执行采用情况不可确认'}
                </Tag>
              </Space>
              {adoption === 'STANDARD_FALLBACK' && <Alert type="warning" showIcon title="最终 Standard 结果未采用新增记忆"
                description={selected.length ? '下方是 Agent 入队时加载的背景，不代表最终 Standard 结果采用了这些资料。' : '本次最终由 Standard 产出结果，新增项目记忆未被采用。'} />}
              {adoption === 'UNAVAILABLE' && <Alert type="warning" showIcon title="背景曾装入任务，执行采用情况不可确认"
                description="任务未成功完成，加载记录不代表已经形成有效审查结论。" />}
              {snapshot.lookupStatus === 'DISABLED' && <Alert type="info" showIcon
                title={snapshot.disabledReason === 'SCHEMA_PENDING' ? '入队时记忆设置尚未就绪' : '入队时项目记忆未启用'}
                description="这里展示入队时的冻结状态；之后修改开关不会改变本次背景。" />}
              {snapshot.lookupStatus === 'PARTIAL_LOOKUP' && <Alert type="warning" showIcon title="按需背景查询失败"
                description="已取得的核心背景仍保留，按需背景可能缺失。" />}
              <Descriptions size="small" column={{ xs: 1, md: 3 }}>
                <Descriptions.Item label="Agent Run">#{runId}</Descriptions.Item>
                <Descriptions.Item label="项目 / 端">#{snapshot.projectId} · {labelFor(TARGET_TYPE_OPTIONS, snapshot.targetType) || '未指定端'}</Descriptions.Item>
                <Descriptions.Item label="记忆设置版本">v{snapshot.policyVersion}</Descriptions.Item>
                <Descriptions.Item label="加载条数">{selected.length}（必载 {coreCount} / 按需 {selected.length - coreCount}）</Descriptions.Item>
                <Descriptions.Item label="新增背景大小">{snapshot.injectedBytes} / 14000 字节</Descriptions.Item>
                <Descriptions.Item label="实际引擎">{summary.effectiveEngine || '尚未确定'}</Descriptions.Item>
              </Descriptions>
              <Space wrap>{KIND_OPTIONS.map(({ value, label }) => <Tag key={value}>
                {label} {selected.filter((item) => item.kind === value).length}
              </Tag>)}</Space>
              {snapshot.issueHintsUnknown && <Typography.Text type="secondary">问题线索未知，已保留近期专项候选。</Typography.Text>}
              {snapshot.candidateScanLimited && <Alert type="warning" showIcon title="按需候选扫描达到上限"
                description="较旧资料可能未进入本次候选；必载规范独立读取。" />}
              {Object.keys(snapshot.skipReasons || {}).length > 0 && <div>
                <Typography.Paragraph type="secondary">筛选事件计数（同条资料可能重复计数；重叠事件不一定表示跳过）：</Typography.Paragraph>
                <Space wrap>{Object.entries(snapshot.skipReasons).map(([reason, count]) => <Tag key={reason}>
                  {SKIP_LABELS[reason] || '其它筛选事件'}：{count}
                </Tag>)}</Space>
              </div>}
              {selected.length > 0 ? <>
                <Typography.Text type="secondary">下表为冻结摘要；链接打开当前资料，其内容和版本可能已变化或失效。背景加载不保证审查结论正确。</Typography.Text>
                <Table rowKey="entryId" size="small" pagination={false} scroll={{ x: 1045 }} columns={columns} dataSource={selected} />
              </> : <Empty description={snapshot.lookupStatus === 'EMPTY' ? '入队时记忆库没有可用资料' : snapshot.lookupStatus === 'NO_MATCH' ? '本次未选中匹配背景，请查看筛选事件' : '本次未加载新增记忆'} />}
            </Space>;

  return <Collapse className="memory-run-summary" activeKey={expanded ? ['memory'] : []}
    onChange={(keys) => setExpanded(keys.includes('memory'))}
    items={[{ key: 'memory', label: '本次审查背景', children: content }]} />;
}
