"""Bounded DOCX/PDF extraction in a short-lived, credential-free process."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_ZIP_MEMBERS = 1000
MAX_PDF_PAGES = 100
PARSE_TIMEOUT_SECONDS = 10
MAX_RESULT_BYTES = 2 * 1024 * 1024
DOCUMENT_PARSER_VERSION = "docx-pdf-v1"


class _DocumentError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status


def extract_document(content: bytes, extension: str) -> dict:
    # Imported only by the Backend, never when executing this file with Python -I.
    from app.core.errors import AppError

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    }
    try:
        with tempfile.TemporaryDirectory(prefix="review-memory-") as directory:
            source = Path(directory) / ("source." + extension)
            source.write_bytes(content)
            result_path = Path(directory) / "result.json"
            with result_path.open("wb") as output:
                subprocess.run(
                    [sys.executable, "-I", str(Path(__file__).resolve()), extension, str(source)],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    cwd=directory,
                    env=environment,
                    timeout=PARSE_TIMEOUT_SECONDS,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            with result_path.open("rb") as output:
                payload = output.read(MAX_RESULT_BYTES + 1)
            if len(payload) > MAX_RESULT_BYTES:
                raise AppError("MEMORY_SOURCE_TOO_LARGE", "Parser output exceeds bounded size", 413)
            result = json.loads(payload)
    except subprocess.TimeoutExpired as exception:
        # subprocess.run kills and waits for this child before raising; no parser grandchildren.
        raise AppError(
            "MEMORY_PARSE_TIMEOUT", "Document parsing exceeded 10 seconds", 422
        ) from exception
    except (OSError, subprocess.CalledProcessError, ValueError) as exception:
        raise AppError(
            "MEMORY_PARSE_FAILED", "Document parser could not complete", 422
        ) from exception
    if "error" in result:
        error = result["error"]
        raise AppError(error["code"], error["message"], error["status"])
    return result


def _check_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if any(ord(char) < 32 and char not in "\n\t" for char in text) or "\ufffd" in text:
        raise _DocumentError("MEMORY_TEXT_INVALID", "Document contains undecodable or control text")
    return text


def _check_size(size: int) -> None:
    if size > MAX_EXTRACTED_BYTES:
        raise _DocumentError("MEMORY_SOURCE_TOO_LARGE", "Extracted text exceeds 256 KiB", 413)


def _docx(content: bytes) -> dict:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from lxml import etree

    if not content.startswith(b"PK\x03\x04"):
        raise _DocumentError("MEMORY_DOCUMENT_INVALID", "DOCX must be an OOXML ZIP document")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(members) > MAX_ZIP_MEMBERS or sum(m.file_size for m in members) > MAX_ZIP_BYTES:
            raise _DocumentError(
                "MEMORY_DOCUMENT_LIMIT", "DOCX exceeds 1000 members or 20 MiB", 413
            )
        if len(names) != len(set(names)) or any(m.flag_bits & 1 for m in members):
            raise _DocumentError(
                "MEMORY_DOCUMENT_INVALID", "DOCX is encrypted or has duplicate members"
            )
        if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
            raise _DocumentError("MEMORY_DOCUMENT_INVALID", "DOCX document structure is missing")
        if any("vbaproject" in name.lower() or "/embeddings/" in name.lower() for name in names):
            raise _DocumentError(
                "MEMORY_DOCUMENT_INVALID", "Macros and embedded objects are unsupported"
            )
        expanded = 0
        xml_parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        for member in members:
            with archive.open(member) as stream:
                data = stream.read(MAX_ZIP_BYTES - expanded + 1)
            expanded += len(data)
            if expanded > MAX_ZIP_BYTES:
                raise _DocumentError("MEMORY_DOCUMENT_LIMIT", "DOCX expansion exceeds 20 MiB", 413)
            if member.filename.endswith((".xml", ".rels")):
                root = etree.fromstring(data, parser=xml_parser)
                if root.getroottree().docinfo.doctype:
                    raise _DocumentError("MEMORY_DOCUMENT_INVALID", "DOCX XML DTDs are unsupported")
                if member.filename == "[Content_Types].xml":
                    types = {node.get("ContentType", "") for node in root}
                    expected = (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document.main+xml"
                    )
                    if expected not in types or any(
                        "macroenabled" in value.lower() for value in types
                    ):
                        raise _DocumentError(
                            "MEMORY_DOCUMENT_INVALID", "DOCX content types are invalid"
                        )

    document = Document(io.BytesIO(content))
    blocks = []
    paragraphs = tables = total = 0
    warnings = [
        "DOCX 仅提取正文段落和表格；页眉页脚、批注、图片及文本框未导入，自动编号可能丢失，请人工核对。"
    ]
    for block in document.iter_inner_content():
        level = None
        if isinstance(block, Paragraph):
            paragraphs += 1
            text = block.text
            location = f"段落 {paragraphs}"
            # Explicit outline levels only; do not infer headings from font size or keywords.
            style = block.style
            visited = set()
            properties = [block._p.pPr]
            while style is not None and style.style_id not in visited:
                visited.add(style.style_id)
                properties.append(style.element.pPr)
                style = style.base_style
            for properties_node in properties:
                if properties_node is None:
                    continue
                outline = properties_node.find(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}outlineLvl"
                )
                if outline is not None:
                    value = int(
                        outline.get(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"
                        )
                    )
                    level = value + 1 if 0 <= value < 9 else None
                    break
        elif isinstance(block, Table):
            tables += 1
            location = f"表格 {tables}"
            # Rows stay together; merged cells can repeat, which the diagnostic makes explicit.
            if block._tbl.xpath(".//w:tc/w:tbl"):
                raise _DocumentError(
                    "MEMORY_DOCUMENT_INVALID", "Nested DOCX tables require manual conversion"
                )
            rows = [[cell.text.replace("\n", " / ") for cell in row.cells] for row in block.rows]
            text = (
                "\n".join(" | ".join(row) for row in rows)
                if any(cell.strip() for row in rows for cell in row)
                else ""
            )
        else:
            continue
        text = _check_text(text).strip()
        if not text:
            continue
        total += len(text.encode("utf-8")) + 2
        _check_size(total)
        blocks.append((level, text, location))
    if not blocks:
        raise _DocumentError("MEMORY_TEXT_INVALID", "DOCX has no extractable body text")
    headings = [(index, level) for index, (level, _, _) in enumerate(blocks) if level is not None]
    starts = []
    if headings:
        minimum = min(level for _, level in headings)
        starts = [index for index, level in headings if level == minimum]
        if len(starts) == 1 and starts[0] == headings[0][0]:
            children = [(index, level) for index, level in headings if level > minimum]
            if children:
                child_level = min(level for _, level in children)
                starts = [index for index, level in children if level == child_level]
    if len(starts) > 200:
        raise _DocumentError("MEMORY_TOO_MANY_ENTRIES", "Document exceeds 200 sections", 413)
    prefix = "\n\n".join(text for _, text, _ in blocks[: starts[0]]) if starts else ""
    sections = []
    for ordinal, start in enumerate(starts):
        end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(blocks)
        heading = blocks[start][1]
        body = "\n\n".join(([prefix] if prefix else []) + [b[1] for b in blocks[start:end]])
        sections.append([heading, body])
        warnings.append(f"章节 {ordinal + 1}：{blocks[start][2]} 至 {blocks[end - 1][2]}。")
    text = "\n\n".join(block[1] for block in blocks)
    warnings.insert(
        0,
        f"DOCX 正文共 {paragraphs} 个段落、{tables} 个表格；表格以行/单元格文字保存，合并单元格可能重复。",
    )
    return {"text": text, "sections": sections or [["", text]], "warnings": warnings}


def _pdf(content: bytes) -> dict:
    from pypdf import PdfReader

    if not content.startswith(b"%PDF-"):
        raise _DocumentError("MEMORY_DOCUMENT_INVALID", "PDF header is missing")
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise _DocumentError("MEMORY_DOCUMENT_ENCRYPTED", "Encrypted PDF is unsupported")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise _DocumentError("MEMORY_DOCUMENT_LIMIT", "PDF exceeds 100 pages", 413)
    pages, empty, total = [], [], 0
    for number, page in enumerate(reader.pages, 1):
        text = _check_text(page.extract_text(extraction_mode="layout")).strip()
        if not text:
            empty.append(str(number))
        body = f"[第 {number} 页]\n{text}"
        total += len(body.encode("utf-8")) + 2
        _check_size(total)
        pages.append(body)
    if not pages or len(empty) == len(pages):
        raise _DocumentError(
            "MEMORY_PDF_NO_TEXT", "PDF has no extractable text; OCR is unsupported"
        )
    text = "\n\n".join(pages)
    warnings = [
        f"PDF 共 {len(pages)} 页，保留页码及布局文字；无法可靠推断标题和表格语义，请人工核对阅读顺序并拆分章节。",
        "PDF 不执行 OCR；图片内文字、复杂表格及字体映射可能无法完整提取，请对照原件确认。",
    ]
    if empty:
        warnings.append("无可提取文字的页码：" + ", ".join(empty) + "；可能为空白页或扫描页。")
    return {"text": text, "sections": [["", text]], "warnings": warnings}


def _main() -> None:
    try:
        content = Path(sys.argv[2]).read_bytes()
        if len(content) > MAX_DOCUMENT_BYTES:
            raise _DocumentError("MEMORY_UPLOAD_TOO_LARGE", "File exceeds 5 MiB", 413)
        result = _docx(content) if sys.argv[1] == "docx" else _pdf(content)
        _check_size(len(result["text"].encode("utf-8")))
        _check_size(sum(len(body.encode("utf-8")) for _, body in result["sections"]))
    except _DocumentError as exception:
        result = {
            "error": {
                "code": exception.code,
                "message": exception.message,
                "status": exception.status,
            }
        }
    except ImportError:
        result = {
            "error": {
                "code": "MEMORY_PARSER_UNAVAILABLE",
                "message": "Document parser dependencies are unavailable",
                "status": 503,
            }
        }
    except Exception:
        # Never return library errors containing document contents, paths or credentials.
        result = {
            "error": {
                "code": "MEMORY_DOCUMENT_INVALID",
                "message": "Document is damaged or unsupported",
                "status": 400,
            }
        }
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    _main()
