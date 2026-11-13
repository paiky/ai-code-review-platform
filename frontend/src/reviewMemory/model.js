import { TARGET_TYPE_OPTIONS } from '../project-config/projectConfigurationModel.js';

export { TARGET_TYPE_OPTIONS };
export const KIND_OPTIONS = [
  { value: 'STANDARD', label: '代码规范' },
  { value: 'ARCHITECTURE', label: '架构约定' },
  { value: 'SKILL', label: '审查 Skill' },
  { value: 'PITFALL', label: '踩坑案例' },
  { value: 'INCIDENT', label: '事故模式' }
];
export const ISSUE_OPTIONS = [
  ['GENERAL', '通用问题'],
  ['API_CONTRACT', '接口契约'],
  ['DATABASE', '数据库'],
  ['CACHE', '缓存'],
  ['MQ', '消息队列'],
  ['TRANSACTION', '事务'],
  ['SECURITY', '安全'],
  ['CONFIG', '配置'],
  ['ERROR_HANDLING', '异常处理'],
  ['TESTING', '测试']
].map(([value, label]) => ({ value, label }));
export const STATE_OPTIONS = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'PUBLISHED', label: '已发布' },
  { value: 'DISABLED', label: '已停用' },
  { value: 'DELETED', label: '已删除' }
];
export const STATE_LABELS = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  ACTIVE: '已发布',
  DISABLED: '已停用',
  DELETED: '已删除'
};
export const ORIGIN_LABELS = { MANUAL: '手工录入', UPLOAD: '文件上传', FEEDBACK: '反馈确认' };
export const CASE_TEMPLATE = [
  '适用条件',
  '原误判及原因',
  '正确判断方法',
  '下次应查证据',
  '例外/失效条件'
]
  .map((label) => `## ${label}\n\n`)
  .join('\n');
export const bytes = (text) => new TextEncoder().encode(text || '').length;
export const allowsCore = (kind) => ['STANDARD', 'ARCHITECTURE'].includes(kind);
export const labelFor = (options, value) =>
  options.find((item) => item.value === value)?.label || value;
export const stateColor = (state) =>
  ({ ACTIVE: 'green', PUBLISHED: 'green', DRAFT: 'gold', DISABLED: 'default', DELETED: 'red' })[
    state
  ];
export function blankEntry(kind) {
  return {
    heading: '',
    content: ['PITFALL', 'INCIDENT'].includes(kind) ? CASE_TEMPLATE : '',
    targetType: null,
    issueType: null,
    pathGlobs: [],
    keywords: [],
    loadMode: 'ON_DEMAND'
  };
}
export function entryDraft(entry) {
  return Object.fromEntries(
    ['heading', 'content', 'targetType', 'issueType', 'pathGlobs', 'keywords', 'loadMode'].map(
      (key) => [key, entry[key]]
    )
  );
}
export function validateEntry(entry) {
  if (!entry.heading?.trim() || !entry.content?.trim()) return '请填写章节标题和正文。';
  if (bytes(entry.content) > 256 * 1024) return '草稿正文不能超过 256 KiB。';
  if (
    entry.pathGlobs.length > 8 ||
    entry.pathGlobs.some(
      (value) =>
        !value ||
        value.length > 256 ||
        /(^\/|\\|:|[\x00-\x1f])/.test(value) ||
        value.split('/').some((part) => ['', '.', '..'].includes(part))
    )
  )
    return '路径最多 8 条，请使用不含越界片段的相对 glob。';
  if (
    entry.keywords.length > 12 ||
    entry.keywords.some((value) => !value.trim() || value.length > 64)
  )
    return '关键词最多 12 个，每个 1–64 字符。';
  return null;
}
export function publicationError(entry) {
  if (bytes(entry.content) > 4000) return '超过 4000 字节，需人工拆分';
  if (entry.validationErrors?.length)
    return entry.validationErrors
      .map(
        (code) =>
          ({
            MEMORY_ENTRY_TOO_LARGE: '正文超限，需人工拆分',
            MEMORY_CASE_TEMPLATE_REQUIRED: '案例五段模板需完整且非空'
          })[code] || code
      )
      .join('；');
  return null;
}

export function sourceUseProblem(source, projectId, hasActiveEntries) {
  if (!source) return '资料已缺失，无法修改关系';
  if (source.state !== 'PUBLISHED') return `资料${STATE_LABELS[source.state] || '未发布'}`;
  if (source.replacementOfId && source.confirmedAt === null) return '替换草稿尚未首次发布';
  if (String(source.projectId) !== String(projectId)) {
    if (source.origin === 'FEEDBACK' || ['PITFALL', 'INCIDENT'].includes(source.kind))
      return '案例仅限归属项目使用';
    if (source.visibility !== 'SHARED') return '私有资料不能跨项目使用';
  }
  if (hasActiveEntries === false) return '无已发布章节';
  return null;
}

export function uploadProblem(file, kind) {
  const extension = file.name.split('.').at(-1).toLowerCase();
  if (kind === 'SKILL' && extension !== 'md') return 'Skill 仅支持 Markdown（.md）文件。';
  if (!['md', 'txt', 'docx', 'pdf'].includes(extension)) {
    return '请选择 .md / .txt / .docx / .pdf 文件；不支持旧 .doc、图片或压缩包。';
  }
  const limit = ['docx', 'pdf'].includes(extension) ? 5 : 1;
  return file.size > limit * 1024 * 1024 ? `该格式文件不能超过 ${limit} MiB。` : null;
}

export const DOCUMENT_ERRORS = {
  MEMORY_DOCUMENT_INVALID:
    '文档损坏、格式不符或含不支持的结构，请转换为普通 DOCX／文本 PDF 后重试。',
  MEMORY_DOCUMENT_ENCRYPTED: '不支持加密文档，请先解除加密后重新上传。',
  MEMORY_PDF_NO_TEXT: 'PDF 没有可提取文字，可能是扫描件；当前不支持 OCR。',
  MEMORY_DOCUMENT_LIMIT:
    '文档超出解析限制：PDF 最多 100 页，DOCX 最多 1000 个内部文件、总解压量 20 MiB。',
  MEMORY_SOURCE_TOO_LARGE: '抽取正文或包含上级条件的章节总量超过 256 KiB，请拆分原文件后重试。',
  MEMORY_TOO_MANY_ENTRIES: '章节超过 200 条，请拆分原文件后重试。',
  MEMORY_PARSE_TIMEOUT: '文档解析超过 10 秒，请简化或拆分文件后重试；旧发布资料仍有效。',
  MEMORY_PARSE_FAILED: '文档解析未能完成，请重试或转换为文本格式；旧发布资料仍有效。',
  MEMORY_PARSER_UNAVAILABLE: '服务端文档解析依赖尚未就绪，请联系维护人员；仍可导入 MD／TXT。'
};
