from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import hashlib
import json
from pathlib import Path
import re


_ASSETS = Path(__file__).with_name("assets")
_DEFAULT = "default.md"
_OBJC = "objc.md"
_MATLAB = "matlab.md"
_RESOLUTION_FAILED = "FILE_RULE_RESOLUTION_FAILED"
_RULE_NAME = re.compile(r"[a-z0-9_]+\.md")
_GLOB = re.compile(r"[\w./*{},-]+", re.ASCII)
_GLOB_TOKEN = re.compile(r"\*\*/|\*")
_OBJC_PREFIXES = (
    "#import", "#include", "#pragma", "#if", "#define",
    "@import", "@interface", "@implementation", "@class", "@protocol", "//", "/*",
)


@dataclass(frozen=True)
class FileRule:
    path: str
    name: str | None
    pattern: str | None
    fallback: bool
    reason: str | None = None


@dataclass(frozen=True)
class RuleCatalog:
    version: str
    default: str
    patterns: tuple[tuple[str, re.Pattern[str], str], ...]
    documents: dict[str, str]
    invalid_mapping: bool = False

    def match(self, path: str, content_prefix: str | None = None) -> FileRule:
        normalized = path.replace("\\", "/").casefold()
        if self.invalid_mapping:
            return self._fallback(path, None, _RESOLUTION_FAILED)
        for pattern, matcher, name in self.patterns:
            if not matcher.fullmatch(normalized):
                continue
            reason = None
            if name == _MATLAB and normalized.endswith(".m"):
                if content_prefix is None:
                    reason = "CONTENT_SNIFF_UNAVAILABLE"
                else:
                    lines = content_prefix[:4096].lstrip("\ufeff").splitlines()
                    first_line = next((line.strip() for line in lines if line.strip()), "")
                    if first_line.startswith(_OBJC_PREFIXES):
                        name = _OBJC
            if name not in self.documents:
                return self._fallback(path, pattern, _RESOLUTION_FAILED)
            return FileRule(path, name, pattern, False, reason)
        return self._fallback(path, None)

    def _fallback(self, path: str, pattern: str | None, reason: str | None = None) -> FileRule:
        if self.default in self.documents:
            return FileRule(path, self.default, pattern or "default", True, reason)
        return FileRule(path, None, pattern, True, _RESOLUTION_FAILED)


@cache
def built_in_catalog() -> RuleCatalog:
    return load_catalog(_ASSETS)


def load_catalog(assets: Path) -> RuleCatalog:
    digest = hashlib.sha256()
    try:
        raw = (assets / "system_rules.json").read_bytes().replace(b"\r\n", b"\n")
        digest.update(raw)
        mapping = json.loads(raw)
        default = mapping["default_rule"]
        if not isinstance(default, str) or not _RULE_NAME.fullmatch(default):
            raise ValueError("Invalid default rule")
        patterns = []
        for pattern, name in mapping["path_rule_map"].items():
            if not isinstance(name, str) or not _RULE_NAME.fullmatch(name):
                raise ValueError("Invalid file rule name")
            patterns.append((pattern, _compile_glob(pattern), name))
        if not patterns:
            raise ValueError("Empty file rules")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
        default = _DEFAULT
        patterns = []

    names = {default, *(name for _, _, name in patterns)}
    documents = {}
    for name in sorted(names):
        digest.update(b"\0" + name.encode("ascii") + b"\0")
        try:
            body = (assets / "rule_docs" / name).read_text(encoding="utf-8").strip()
            if body:
                documents[name] = body
                digest.update(body.encode("utf-8"))
        except (OSError, UnicodeError):
            continue
    # The bundled ordering already places narrower overlaps ahead of their generic rules.
    patterns.sort(key=lambda entry: _pattern_priority(entry[0]))
    return RuleCatalog(digest.hexdigest(), default, tuple(patterns), documents, not patterns)


def _pattern_priority(pattern: str) -> int:
    if pattern.startswith("**/") and "*" not in pattern[3:]:
        return 0
    if not pattern.startswith("**/*."):
        return 1
    return 2


def _compile_glob(pattern: str) -> re.Pattern[str]:
    if (
        not _GLOB.fullmatch(pattern)
        or pattern.startswith("/")
        or any(
            part in {"", ".", ".."} or ("**" in part and part != "**")
            for part in pattern.split("/")
        )
        or "**" in pattern.replace("**/", "")
    ):
        raise ValueError("Invalid file rule pattern")
    head, opening, tail = pattern.casefold().partition("{")
    if opening:
        alternatives, closing, suffix = tail.partition("}")
        if (
            not closing or set(head + alternatives + suffix) & {"{", "}"}
            or any(not part for part in alternatives.split(","))
        ):
            raise ValueError("Invalid file rule alternatives")
        globs = [head + item + suffix for item in alternatives.split(",")]
    else:
        if set(pattern) & {"}", ","}:
            raise ValueError("Invalid file rule alternatives")
        globs = [head]
    expressions = []
    for glob in globs:
        end = 0
        parts = []
        for token in _GLOB_TOKEN.finditer(glob):
            parts.append(re.escape(glob[end:token.start()]))
            parts.append("(?:[^/]+/)*" if token[0] == "**/" else "[^/]*")
            end = token.end()
        parts.append(re.escape(glob[end:]))
        expressions.append("".join(parts))
    return re.compile("|".join(expressions))
