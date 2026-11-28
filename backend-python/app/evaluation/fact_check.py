"""Run a fixed-diff fact check against labeled EvaluationCase records."""

from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session

from app.agent_review import repository as agent_repository
from app.agent_review.crypto import decrypt_api_key
from app.agent_review.runtime import OPENAI_CHAT_RUNNER, OPENAI_RESPONSES_RUNNER, runtime_record_snapshot
from app.agent_review_spike.chat_completions_runner import (
    ChatCompletionsRunnerConfig,
    HttpxChatCompletionsTransport,
    OpenAIChatCompletionsAgentRunner,
)
from app.agent_review_spike.diff import split_diff_sections
from app.agent_review_spike.fact_check import FACT_CHECK_PROMPT, FactCheckRunner, check_findings
from app.agent_review_spike.responses_runner import (
    HttpxResponsesTransport,
    OpenAIResponsesAgentRunner,
    ResponsesRunnerConfig,
)
from app.code_quality.repository import scrub_sensitive
from app.core.database import SessionLocal
from app.evaluation.repository import get_evaluation_cases_by_ids
from app.evaluation.service import create_evaluation_run_response, update_evaluation_run_item_response


def run_evaluation(
    db: Session, runner: FactCheckRunner, samples: list[dict[str, Any]], *, name: str, provider: str,
) -> dict[str, Any]:
    if not isinstance(samples, list) or not samples:
        raise ValueError("Expected a nonempty array of samples")
    by_id = {}
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("Expected a sample object")
        case_id = sample.get("caseId")
        if type(case_id) is not int or case_id < 1 or case_id in by_id:
            raise ValueError("Each sample requires a different positive integer caseId")
        if not all(isinstance(sample.get(key), str) and sample[key].strip() for key in ("base", "head", "diff")):
            raise ValueError(f"Case {case_id} requires base, head and a nonempty unified diff")
        by_id[case_id] = sample

    cases = {case.id: case for case in get_evaluation_cases_by_ids(db, list(by_id))}
    findings = {}
    for case_id in by_id:
        case = cases.get(case_id)
        finding = json.loads(case.item_snapshot_json or "null") if case else None
        if not isinstance(finding, dict) or not isinstance(finding.get("filePath"), str) or not finding["filePath"]:
            raise ValueError(f"Case {case_id} requires an existing Finding snapshot")
        findings[case_id] = finding

    prompt_hash = sha256(FACT_CHECK_PROMPT.encode("utf-8")).hexdigest()
    run = create_evaluation_run_response(db, {
        "caseIds": list(by_id), "name": name, "provider": provider, "model": runner.config.model,
        "promptHash": prompt_hash, "baseline": {"source": "ORIGINAL_FINDINGS"},
        "candidate": {"source": "FACT_CHECK", "budgets": runner.config.effective_budgets()},
    })
    rows = []
    for item in run["items"]:
        case_id = item["caseId"]
        sample = by_id[case_id]
        finding = findings[case_id]
        started = monotonic()
        outcomes, usage = check_findings(
            runner, [finding], split_diff_sections(sample["diff"], unheaded_path=finding["filePath"]),
        )
        outcome = outcomes[0]
        check = outcome.model_dump(exclude_none=True)
        if outcome.reason:
            check["reason"] = scrub_sensitive(outcome.reason)
        row = {
            "caseId": case_id, "base": sample["base"], "head": sample["head"],
            "diffSha256": sha256(sample["diff"].encode("utf-8")).hexdigest(),
            "humanVerdict": item["verdict"], "severity": finding.get("severity"),
            "factCheck": check, "usage": usage,
            "durationMs": int((monotonic() - started) * 1000),
        }
        rows.append(row)
        update_evaluation_run_item_response(db, run["id"], item["id"], {
            "status": "COMPLETED" if outcome.status == "COMPLETED" else "FAILED",
            "durationMs": row["durationMs"], "resultSummary": row, "errorMessage": outcome.reasonCode,
        })

    def counts(selected: list[dict[str, Any]]) -> dict[str, int]:
        false_positives = [row for row in selected if row["humanVerdict"] == "FALSE_POSITIVE"]
        true_positives = [
            row for row in selected if row["humanVerdict"] in {"TRUE_POSITIVE", "LEVEL_TOO_HIGH", "LEVEL_TOO_LOW"}
        ]
        return {
            "falsePositives": len(false_positives),
            "decidableFalsePositives": sum(
                row["factCheck"].get("verdict") in {"KEEP", "CONTRADICTED"} for row in false_positives
            ),
            "correctlyContradicted": sum(row["factCheck"].get("verdict") == "CONTRADICTED" for row in false_positives),
            "truePositives": len(true_positives),
            "incorrectlyContradicted": sum(row["factCheck"].get("verdict") == "CONTRADICTED" for row in true_positives),
        }

    return {
        "evaluationRunId": run["id"], "model": runner.config.model, "promptHash": prompt_hash,
        "metrics": {
            **counts(rows),
            "highSeverity": counts([
                row for row in rows if row["severity"] in {"MAJOR", "HIGH", "CRITICAL", "BLOCKER"}
            ]),
            "outcomes": dict(Counter(
                row["factCheck"].get("verdict") or row["factCheck"]["reasonCode"] for row in rows
            )),
            "durationMs": sum(row["durationMs"] for row in rows),
            "totalTokens": sum(row["usage"].get(
                "total_tokens", row["usage"].get("input_tokens", 0) + row["usage"].get("output_tokens", 0),
            ) for row in rows),
        },
        "items": rows,
    }


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=Path, help="UTF-8 JSON array with caseId, base, head and diff")
    parser.add_argument("--name", default="Finding fact-check evaluation")
    args = parser.parse_args()
    samples = json.loads(args.samples.read_text(encoding="utf-8-sig"))
    with SessionLocal() as db:
        record = agent_repository.selected_agent_runtime_record(db)
        runtime = runtime_record_snapshot(record)
        runner_type = runtime["runnerType"]
        if not record.enabled or runner_type not in {OPENAI_CHAT_RUNNER, OPENAI_RESPONSES_RUNNER}:
            parser.error("Select an enabled Chat Completions or Responses Agent Runtime first")
        key = decrypt_api_key(record.api_key_ciphertext)
        base = runtime["baseUrl"].rstrip("/")
        model = runtime["model"]
        budgets, _ = agent_repository.effective_agent_budgets(agent_repository.get_agent_settings_record(db))
        runner: FactCheckRunner
        if runner_type == OPENAI_RESPONSES_RUNNER:
            runner = OpenAIResponsesAgentRunner(
                HttpxResponsesTransport(f"{base}/responses", key, verify_tls=runtime["tlsVerify"]),
                ResponsesRunnerConfig.from_budgets(budgets, model=model, reasoning_effort=runtime["reasoningEffort"]),
            )
        else:
            runner = OpenAIChatCompletionsAgentRunner(
                HttpxChatCompletionsTransport(f"{base}/chat/completions", key, verify_tls=runtime["tlsVerify"]),
                ChatCompletionsRunnerConfig.from_budgets(budgets, model=model),
            )
        report = run_evaluation(db, runner, samples, name=args.name, provider=runtime["runtimeCode"])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
