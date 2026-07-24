from app.review_quality.agent_observation import (
    aggregate_agent_observation,
    percentile_nearest_rank,
)


def test_nearest_rank_percentiles_are_deterministic() -> None:
    values = [3000, 1000, 2000, 4000]

    assert percentile_nearest_rank(values, 0.50) == 2000
    assert percentile_nearest_rank(values, 0.95) == 4000
    assert percentile_nearest_rank([], 0.95) == 0


def test_observation_aggregates_pairs_annotations_fallback_and_safe_usage() -> None:
    snapshot = {
        "results": [
            _result(1, "standard-1", "STANDARD", "STANDARD", 2),
            _result(1, "agent-1", "AGENT", "AGENT", 1),
            _result(2, "standard-2", "STANDARD", "STANDARD", 1),
            _result(2, "agent-2", "AGENT", "STANDARD_FALLBACK", 1),
            _result(3, "agent-3", "AGENT", "AGENT", 0),
        ],
        "runs": [
            _run(1, "SUCCEEDED", "AGENT", 1000, 2, 4, 100, {"input_tokens": 10, "prompt": "do not export"}),
            _run(2, "FAILED", "STANDARD_FALLBACK", 3000, 0, 1, 0, {}),
            _run(3, "SUCCEEDED", "AGENT", 2000, 4, 8, 300, {"outputTokens": 5, "totalTokens": 15}),
        ],
        "cases": [
            _case(1, "standard-1", "std-1", "TRUE_POSITIVE"),
            _case(1, "agent-1", "agent-1", "FALSE_POSITIVE"),
            _case(2, "standard-2", "std-2", "MISSING_FINDING"),
            _case(2, "agent-2", "agent-2", "CONTEXT_MISSING"),
        ],
        "feedback": [
            {
                "id": 1,
                "taskId": 1,
                "reviewKey": "agent-1",
                "fingerprint": "feedback-1",
                "feedbackType": "USEFUL",
                "reasonType": "CONTEXT_MISSING",
            }
        ],
    }

    result = aggregate_agent_observation(snapshot)

    assert result["sampleSummary"] == {
        "taskCount": 3,
        "standardSampleCount": 2,
        "agentSampleCount": 3,
        "pairedTaskCount": 2,
        "unpairedStandardTaskCount": 0,
        "unpairedAgentTaskCount": 1,
    }
    assert result["annotationProgress"]["annotatedPairedTaskCount"] == 2
    assert result["annotationProgress"]["annotationSampleCount"] == 5
    assert result["findingSummary"]["humanFalsePositiveCount"] == 1
    assert result["findingSummary"]["missingFindingCount"] == 1
    assert result["findingSummary"]["contextInsufficientCount"] == 2
    assert result["agentReliability"]["successRate"] == 0.6667
    assert result["agentReliability"]["failureRate"] == 0.3333
    assert result["agentReliability"]["fallbackRate"] == 0.3333
    assert result["agentExecutionMetrics"]["durationMs"]["p50"] == 2000
    assert result["agentExecutionMetrics"]["durationMs"]["p95"] == 3000
    assert result["agentExecutionMetrics"]["turnCount"]["p95"] == 4
    assert result["agentExecutionMetrics"]["toolCallCount"]["p95"] == 8
    assert result["agentExecutionMetrics"]["sourceBytesReturned"]["p95"] == 300
    assert result["agentExecutionMetrics"]["usageSummary"]["inputTokens"] == 10
    assert result["agentExecutionMetrics"]["usageSummary"]["outputTokens"] == 5
    assert "prompt" not in result["agentExecutionMetrics"]["usageSummary"]
    assert result["sampleGate"]["status"] == "INSUFFICIENT_SAMPLE"
    assert result["sampleGate"]["observedAnnotatedSampleCount"] == 5
    assert result["sampleGate"]["conclusionCalculated"] is False
    assert result["sampleGate"]["expansionConclusion"] is None


def _result(task_id: int, review_key: str, requested: str, effective: str, findings: int) -> dict:
    return {
        "taskId": task_id,
        "projectId": 1,
        "projectName": "demo",
        "groupId": 1,
        "groupName": "demo",
        "profile": "profile",
        "reviewKey": review_key,
        "requestedEngine": requested,
        "effectiveEngine": effective,
        "findingCount": findings,
        "observedAt": f"2026-07-18T0{task_id}:00:00",
    }


def _run(
    task_id: int,
    status: str,
    effective: str,
    duration: int,
    turns: int,
    calls: int,
    source_bytes: int,
    usage: dict,
) -> dict:
    return {
        "taskId": task_id,
        "status": status,
        "effectiveEngine": effective,
        "durationMs": duration,
        "turnCount": turns,
        "toolCallCount": calls,
        "sourceBytesReturned": source_bytes,
        "diffBytesReturned": 0,
        "usage": usage,
    }


def _case(task_id: int, review_key: str, fingerprint: str, verdict: str) -> dict:
    return {
        "id": task_id,
        "taskId": task_id,
        "reviewKey": review_key,
        "fingerprint": fingerprint,
        "verdict": verdict,
    }
