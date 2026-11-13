"""Bounded text import. Uploaded instructions are data, never executable skills."""

from dataclasses import dataclass

from markdown_it import MarkdownIt
from pydantic import ValidationError
import yaml
from yaml.tokens import AliasToken, AnchorToken

from app.core.errors import AppError
from app.review_memory.document_parser import (
    DOCUMENT_PARSER_VERSION,
    MAX_DOCUMENT_BYTES,
    extract_document,
)
from app.review_memory.schemas import (
    MAX_SOURCE_CONTENT_BYTES,
    MAX_SOURCE_ENTRIES,
    MemoryEntryDraft,
    MemoryKind,
    MemorySourceDraft,
    MemoryUploadMetadata,
)


MAX_UPLOAD_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024
MAX_REQUEST_BYTES = MAX_DOCUMENT_BYTES + 64 * 1024
PARSER_VERSION = "text-markdown-v1"


@dataclass
class ParsedMemory:
    draft: MemorySourceDraft
    filename: str
    media_type: str
    text: str
    warnings: list[str]
    parser_version: str = PARSER_VERSION


def upload_byte_limit(filename: str | None) -> int:
    extension = (filename or "").rsplit(".", 1)[-1].lower()
    return MAX_DOCUMENT_BYTES if extension in {"docx", "pdf"} else MAX_UPLOAD_BYTES


class _SkillLoader(yaml.SafeLoader):
    def __init__(self, stream: str):
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent, index):
        self._depth += 1
        try:
            if self._depth > 16:
                raise yaml.YAMLError("front matter nesting exceeds 16 levels")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise yaml.YAMLError("front matter keys must be unique strings")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _front_matter(text: str) -> tuple[str, dict, list[str]]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text, {}, []
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise AppError("MEMORY_SKILL_YAML_INVALID", "Skill front matter is not closed", 400)
    header = "".join(lines[1:end])
    if len(header.encode("utf-8")) > 8192:
        raise AppError("MEMORY_SKILL_YAML_TOO_LARGE", "Skill front matter exceeds 8 KiB", 413)
    try:
        if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(header)):
            raise yaml.YAMLError("anchors and aliases are not supported")
        data = yaml.load(header, Loader=_SkillLoader)
        if not isinstance(data, dict):
            raise yaml.YAMLError("front matter must be a mapping")
        for key, limit in (("name", 255), ("description", 4000)):
            if key in data and (
                not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit
            ):
                raise yaml.YAMLError("invalid name or description")
    except (yaml.YAMLError, TypeError, ValueError, RecursionError) as exception:
        raise AppError(
            "MEMORY_SKILL_YAML_INVALID", "Skill front matter is invalid or unsupported", 400
        ) from exception
    ignored = sorted(key for key in data if key not in {"name", "description"})
    warnings = ["Skill 仅导入审查文本；脚本、工具权限与其它声明不执行。"]
    if ignored:
        warnings.append("未启用 front matter 字段：" + ", ".join(ignored)[:1000])
    return "".join(lines[end + 1 :]), data, warnings


def _markdown_sections(text: str, fallback: str) -> list[tuple[str, str]]:
    tokens = MarkdownIt("commonmark", {"html": False}).parse(text)
    # Only split the highest heading level. Preserve parent conditions and nested blocks together.
    headings = [
        (int(token.tag[1:]), token.map[0], token.content)
        for token in tokens
        if token.type == "heading_open" and token.level == 0 and token.map
    ]
    if not headings:
        return [(fallback, text)]
    lines = text.splitlines(keepends=True)
    minimum = min(level for level, _, _ in headings)
    top = [(line, level) for level, line, _ in headings if level == minimum]
    # A single document title is a wrapper: include its introductory conditions in every child.
    if len(top) == 1 and top[0][0] == headings[0][1]:
        children = [(level, line, label) for level, line, label in headings if level > minimum]
        if children:
            child_level = min(level for level, _, _ in children)
            top = [(line, level) for level, line, _ in children if level == child_level]
    prefix = "".join(lines[: top[0][0]])
    sections = []
    for index, (start, _) in enumerate(top):
        end = top[index + 1][0] if index + 1 < len(top) else len(lines)
        # Keep source text verbatim, including headings, code fences and HTML as inert text.
        body = prefix + "".join(lines[start:end])
        heading = lines[start].strip().lstrip("#").strip() or fallback
        if len(heading) > 255:
            raise AppError("MEMORY_HEADING_TOO_LONG", "Section heading exceeds 255 characters", 400)
        sections.append((heading, body))
    return sections


def parse_upload(
    filename: str | None,
    media_type: str | None,
    content: bytes,
    metadata: MemoryUploadMetadata,
) -> ParsedMemory:
    limit = upload_byte_limit(filename)
    if len(content) > limit:
        raise AppError("MEMORY_UPLOAD_TOO_LARGE", f"File exceeds {limit // (1024 * 1024)} MiB", 413)
    filename = (filename or "").replace("\\", "/").split("/")[-1]
    if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
        raise AppError("MEMORY_FILENAME_INVALID", "Invalid original filename", 400)
    extension = filename.rsplit(".", 1)[-1].lower()
    allowed = {"text/plain", "application/octet-stream"}
    if extension == "md":
        allowed |= {"text/markdown", "text/x-markdown"}
    elif extension == "docx":
        allowed = {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        }
    elif extension == "pdf":
        allowed = {"application/pdf", "application/octet-stream"}
    if (
        extension not in {"md", "txt", "docx", "pdf"}
        or (media_type or "").split(";", 1)[0].lower() not in allowed
    ):
        raise AppError(
            "MEMORY_FORMAT_UNSUPPORTED",
            "Supported formats: UTF-8 MD/TXT, DOCX, text PDF; Skill requires MD",
            415,
        )
    if metadata.kind == MemoryKind.SKILL and extension != "md":
        raise AppError("MEMORY_FORMAT_UNSUPPORTED", "Skill must be a Markdown document", 415)
    document = None
    if extension in {"docx", "pdf"}:
        document = extract_document(content, extension)
        text = document["text"]
    else:
        try:
            text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError as exception:
            raise AppError("MEMORY_TEXT_INVALID", "File must use UTF-8 encoding", 400) from exception
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise AppError("MEMORY_TEXT_INVALID", "File contains binary control characters", 400)
    warnings = list(document["warnings"]) if document else []
    info = {}
    if metadata.kind == MemoryKind.SKILL:
        text, info, warnings = _front_matter(text)
        if not warnings:
            warnings.append("Skill 仅导入审查文本；脚本和工具声明不执行。")
    if len(text.encode("utf-8")) > MAX_SOURCE_CONTENT_BYTES:
        raise AppError("MEMORY_SOURCE_TOO_LARGE", "Extracted text exceeds 256 KiB", 413)
    if not text.strip():
        raise AppError("MEMORY_TEXT_INVALID", "Document has no review text", 400)
    title = metadata.title or info.get("name") or filename
    if metadata.kind in {MemoryKind.PITFALL, MemoryKind.INCIDENT}:
        sections = [(title, text)]
    elif document:
        sections = [(heading or title, body) for heading, body in document["sections"]]
    elif extension == "md":
        sections = _markdown_sections(text, title)
    else:
        sections = [(title, text)]
    if len(sections) > MAX_SOURCE_ENTRIES:
        raise AppError("MEMORY_TOO_MANY_ENTRIES", "Document exceeds 200 sections", 413)
    if sum(len(body.encode("utf-8")) for _, body in sections) > MAX_SOURCE_CONTENT_BYTES:
        raise AppError(
            "MEMORY_SOURCE_TOO_LARGE", "Sections with shared conditions exceed 256 KiB", 413
        )
    if any(len(body.encode("utf-8")) > 4000 for _, body in sections):
        warnings.append("部分章节超过 4000 UTF-8 字节，保留完整草稿，发布前需人工拆分。")
    try:
        entries = [
            MemoryEntryDraft(
                heading=heading,
                content=body,
                target_type=metadata.target_type,
                issue_type=metadata.issue_type,
                path_globs=metadata.path_globs,
                keywords=metadata.keywords,
                load_mode=metadata.load_mode,
            )
            for heading, body in sections
        ]
        draft = MemorySourceDraft(
            kind=metadata.kind,
            title=title,
            description=metadata.description
            if metadata.description is not None
            else info.get("description"),
            entries=entries,
        )
    except ValidationError as exception:
        raise AppError(
            "MEMORY_PARSE_INVALID", "Parsed headings or metadata are invalid", 400
        ) from exception
    canonical_media_type = {
        "md": "text/markdown",
        "txt": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }[extension]
    return ParsedMemory(
        draft,
        filename,
        canonical_media_type,
        text,
        warnings,
        DOCUMENT_PARSER_VERSION if document else PARSER_VERSION,
    )
