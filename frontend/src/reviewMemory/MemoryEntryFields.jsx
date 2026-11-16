import { Form, Input, Select, Typography } from 'antd';
import { allowsCore, bytes, ISSUE_OPTIONS, TARGET_TYPE_OPTIONS } from './model.js';

export default function MemoryEntryFields({
  value,
  onChange,
  kind,
  content = true,
  showTargetType = true,
  disabled = false
}) {
  const change = (key, next) => onChange({ ...value, [key]: next });
  return (
    <Form layout="vertical" disabled={disabled}>
      {content && (
        <>
          <Form.Item label="章节标题" required>
            <Input
              aria-label="章节标题"
              maxLength={255}
              value={value.heading}
              onChange={(event) => change('heading', event.target.value)}
            />
          </Form.Item>
          <Form.Item
            label={`章节正文 · ${bytes(value.content)} UTF-8 字节`}
            required
            extra="草稿保留完整正文；发布时每条不超过 4000 字节。代码块和例外条件请完整保留。"
          >
            <Input.TextArea
              aria-label="章节正文"
              autoSize={{ minRows: 9, maxRows: 22 }}
              value={value.content}
              onChange={(event) => change('content', event.target.value)}
            />
          </Form.Item>
          {['PITFALL', 'INCIDENT'].includes(kind) && (
            <Typography.Paragraph type="secondary">
              {kind === 'PITFALL'
                ? '必填“原误判及原因”；适用条件、正确判断方法、下次应查证据、例外/失效条件可按需补充。'
                : '请依次填写五段：适用条件、原误判及原因、正确判断方法、下次应查证据、例外/失效条件。'}
            </Typography.Paragraph>
          )}
        </>
      )}
      <div className="memory-field-grid">
        {showTargetType && <Form.Item label="适用端" extra="留空不限定端；“通用”是独立端。">
          <Select
            aria-label="适用端"
            allowClear
            value={value.targetType || undefined}
            options={TARGET_TYPE_OPTIONS}
            placeholder="所有端"
            onChange={(next) => change('targetType', next || null)}
          />
        </Form.Item>}
        <Form.Item label="问题类型">
          <Select
            aria-label="问题类型"
            allowClear
            value={value.issueType || undefined}
            options={ISSUE_OPTIONS}
            placeholder="不限定"
            onChange={(next) => change('issueType', next || null)}
          />
        </Form.Item>
      </div>
      <Form.Item label="路径范围" extra="每行一个相对 glob，最多 8 条；留空不限定路径。">
        <Input.TextArea
          aria-label="路径范围"
          rows={2}
          value={value.pathGlobs.join('\n')}
          placeholder="例如 src/order/**"
          onChange={(event) =>
            change('pathGlobs', event.target.value ? event.target.value.split('\n') : [])
          }
        />
      </Form.Item>
      <Form.Item label="关键词" extra="输入后按回车分隔，最多 12 个。">
        <Select
          aria-label="关键词"
          mode="tags"
          value={value.keywords}
          onChange={(next) => change('keywords', next)}
        />
      </Form.Item>
      <Form.Item
        label="加载方式"
        extra={
          allowsCore(kind)
            ? '核心约定须通过服务端的项目总预算校验。'
            : 'Skill 和案例只允许按需加载。'
        }
      >
        <Select
          aria-label="加载方式"
          value={value.loadMode}
          onChange={(next) => change('loadMode', next)}
          options={[
            { value: 'ON_DEMAND', label: '按需背景' },
            ...(allowsCore(kind) ? [{ value: 'CORE', label: '核心约定' }] : [])
          ]}
        />
      </Form.Item>
    </Form>
  );
}
