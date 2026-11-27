from hashlib import sha256
import json
import os
from pathlib import Path


MAX_FIXTURE_BYTES = 128_000
KINDS = {"AGENT": "AGENT_DIFF", "STANDARD": "STANDARD_CONTEXT"}


def approved_material(project_id: int, issue: dict, sample: dict) -> tuple[Path, Path, str] | None:
    directory = os.getenv("REVIEW_QUALITY_GOVERNANCE_REPLAY_ROOT")
    if not directory:
        return None
    # Bind agent material to its Run and Standard material to its event.
    evidence_id = sample.get("runId") if issue["engine"] == "AGENT" else sample.get("eventId")
    if not evidence_id:
        return None
    kind = KINDS[issue["engine"]]
    try:
        root = Path(directory).resolve(strict=True)
        sample_root = root / str(project_id) / str(sample["taskId"]) / str(evidence_id) / kind
        fixture = sample_root / "fixture.json"
        worktree = sample_root / "source"
        if fixture.resolve(strict=True) != fixture or worktree.resolve(strict=True) != worktree:
            return None
        with fixture.open("rb") as stream:
            raw = stream.read(MAX_FIXTURE_BYTES + 1)
        if len(raw) > MAX_FIXTURE_BYTES or json.loads(raw).get("kind") != kind or not worktree.is_dir():
            return None
    except (OSError, ValueError, AttributeError, RuntimeError):
        return None
    return fixture, worktree, sha256(raw).hexdigest()


def approved_samples(project_id: int, issue: dict) -> dict[str, str]:
    materials = {}
    for sample in issue["samples"]:
        material = approved_material(project_id, issue, sample)
        if material:
            materials[str(sample["taskId"])] = material[2]
    return materials
