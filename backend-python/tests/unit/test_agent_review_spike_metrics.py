from app.agent_review_spike.metrics import build_report_metrics


def _cases(count=30):
    cases = []
    for index in range(count):
        should_report = index < 20
        cases.append(
            {
                "id": f"case-{index}",
                "verdict": "TRUE_POSITIVE" if should_report else "FALSE_POSITIVE",
                "contextRelated": not should_report,
            }
        )
    return cases


def _execution(reported, *, duration=100, status="SUCCESS", security=0):
    return {
        "status": status,
        "durationMs": duration,
        "targetReported": reported,
        "contextMissingCount": 0,
        "blockedAccessCount": security,
        "securityViolationCount": security,
    }


def test_metrics_pass_all_acceptance_gates():
    cases = _cases()
    results = []
    for index, case in enumerate(cases):
        baseline_reported = True
        candidate_reported = index < 20 or index < 27
        results.append(
            {
                "caseId": case["id"],
                "baseline": _execution(baseline_reported),
                "candidate": _execution(candidate_reported),
            }
        )

    metrics = build_report_metrics(
        cases,
        results,
        {"readOnlyMount": True, "deepseekOnlyEgress": True},
    )

    assert metrics["status"] == "PASS"
    assert metrics["baseline"]["falsePositiveCount"] == 10
    assert metrics["candidate"]["falsePositiveCount"] == 7
    assert metrics["delta"]["contextFalsePositiveRelativeReduction"] == 0.3
    assert all(metrics["gates"].values())


def test_metrics_marks_small_sample_insufficient_even_when_other_gates_pass():
    cases = _cases(10)
    results = [
        {
            "caseId": case["id"],
            "baseline": _execution(True),
            "candidate": _execution(index < 7),
        }
        for index, case in enumerate(cases)
    ]

    metrics = build_report_metrics(
        cases,
        results,
        {"readOnlyMount": True, "deepseekOnlyEgress": True},
    )

    assert metrics["status"] == "INSUFFICIENT_SAMPLE"
    assert metrics["gates"]["minimumSampleCount"] is False


def test_metrics_fail_on_security_violation_and_recall_drop():
    cases = _cases()
    results = []
    for index, case in enumerate(cases):
        results.append(
            {
                "caseId": case["id"],
                "baseline": _execution(True),
                "candidate": _execution(index < 15, security=1 if index == 0 else 0),
            }
        )

    metrics = build_report_metrics(
        cases,
        results,
        {"readOnlyMount": True, "deepseekOnlyEgress": True},
    )

    assert metrics["status"] == "FAIL"
    assert metrics["gates"]["recallDropWithin5Points"] is False
    assert metrics["gates"]["securityViolationCountZero"] is False
