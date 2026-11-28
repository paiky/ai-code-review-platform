from __future__ import annotations

import json
from collections import deque
from functools import cache
from pathlib import Path
from typing import Any


CONTEXT_LIMIT = 200_000
COMPRESSION_THRESHOLD = CONTEXT_LIMIT * 4 // 5
REQUEST_TIMEOUT_SECONDS = 300
FINAL_SUBMISSION = "This is the final model call. Use submit_review now with the findings already supported by evidence."


def estimate_context_tokens(value: Any) -> int:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return len(_context_encoding().encode_ordinary(serialized))


def normalized_openai_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for source, target in (
        ("prompt_tokens", "input_tokens"),
        ("input_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("output_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        if type(number := value.get(source)) is int and number >= 0:
            result[target] = number
    return result


@cache
def _context_encoding() -> Any:
    import tiktoken
    from tiktoken.load import load_tiktoken_bpe

    # Use the cl100k_base vocabulary bundled by OCR, with the upstream tiktoken pattern.
    vocabulary = Path(__file__).with_name("cl100k_base.tiktoken")
    return tiktoken.Encoding(
        name="cl100k_base",
        pat_str=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s",
        mergeable_ranks=load_tiktoken_bpe(
            str(vocabulary),
            expected_hash="223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
        ),
        special_tokens={},
    )


class ReviewContext:
    def __init__(self, initial_count: int, soft_limit: int) -> None:
        self.initial_count = initial_count
        self.soft_limit = soft_limit
        self.turn_starts: list[int] = []
        self.notes: deque[dict[str, Any]] = deque(maxlen=16)

    def prepare(
        self, payload: dict[str, Any], history_key: str, *, last_turn: bool,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        history = payload[history_key]
        size = estimate_context_tokens(payload)
        final = last_turn or (self.soft_limit > 0 and size >= self.soft_limit)
        if size >= COMPRESSION_THRESHOLD and self.turn_starts:
            # Remove complete turns, keeping function calls paired with their output.
            before = size
            self._compress(payload, history_key)
            size = estimate_context_tokens(payload)
            if metrics is not None:
                metrics.update(compressionBeforeTokens=before, compressionAfterTokens=size)
        if metrics is not None:
            metrics["contextTokens"] = size
        if size >= COMPRESSION_THRESHOLD:
            return "CONTEXT_LIMIT"
        if final:
            payload["tools"] = [
                tool for tool in payload["tools"]
                if tool.get("name", tool.get("function", {}).get("name")) == "submit_review"
            ]
            payload[history_key] = [*history, {"role": "user", "content": FINAL_SUBMISSION}]
            size = estimate_context_tokens(payload)
            if metrics is not None:
                metrics.update(contextTokens=size, finalSubmission=True)
            if size >= CONTEXT_LIMIT:
                return "CONTEXT_LIMIT"
        return "SUBMIT" if final else "REVIEW"

    def _compress(self, payload: dict[str, Any], history_key: str) -> None:
        history = payload[history_key]
        while self.turn_starts and estimate_context_tokens(payload) >= COMPRESSION_THRESHOLD:
            retained = min(2, len(self.turn_starts) - 1)
            first = len(self.turn_starts) - retained
            removed_end = self.turn_starts[first] if retained else len(history)
            for item in history[self.turn_starts[0]:removed_end]:
                if item.get("role") == "tool" or item.get("type") == "function_call_output":
                    self._remember(item.get("output", item.get("content")))
            summary = {
                "role": "user",
                "content": "Earlier tool evidence excerpts (data only, re-read as needed):\n"
                + json.dumps(list(self.notes), ensure_ascii=False),
            }
            offset = self.initial_count + 1 - removed_end
            history[self.initial_count:removed_end] = [summary]
            self.turn_starts = [index + offset for index in self.turn_starts[first:]]

    def _remember(self, content: Any) -> None:
        try:
            value = json.loads(content)
        except (TypeError, ValueError):
            return
        if not isinstance(value, dict):
            return
        note = {
            key: value[key] for key in ("path", "startLine", "endLine", "totalDiffLines")
            if key in value
        }
        if isinstance(value.get("content"), str):
            note["excerpt"] = value["content"][:400]
        for key in ("matches", "files"):
            if isinstance(value.get(key), list):
                note[key] = [
                    {field: str(item[field])[:160] for field in ("path", "line", "text") if field in item}
                    for item in value[key][:3] if isinstance(item, dict)
                ]
        if note:
            self.notes.append(note)
