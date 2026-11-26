"""Create the synthetic Git inputs for the review evidence replay workflow."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    folder = args.directory.resolve()
    root = folder / "source"
    root.mkdir(parents=True)

    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()

    git("init", "--quiet")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Review fixture")
    git("config", "core.autocrlf", "false")
    git("config", "commit.gpgsign", "false")
    before = """class OrderService {
    private final OrderPolicy orderPolicy = new OrderPolicy();
    public void submit(String orderId) {
        if (!orderPolicy.validateOrderAccess(orderId)) {
            throw new IllegalArgumentException();
        }
        System.out.println(orderId);
    }
}
"""
    deleted = """        if (!orderPolicy.validateOrderAccess(orderId)) {
            throw new IllegalArgumentException();
        }
"""
    (root / "OrderService.java").write_bytes(before.encode())
    (root / "OrderPolicy.java").write_bytes(b"""class OrderPolicy {
    public boolean validateOrderAccess(String orderId) {
        return orderId != null && !orderId.isEmpty();
    }
}
""")
    git("add", ".")
    git("commit", "--quiet", "-m", "Fixture base")
    base = git("rev-parse", "HEAD")
    (root / "OrderService.java").write_bytes(before.replace(deleted, "").encode())
    git("add", "OrderService.java")
    git("commit", "--quiet", "-m", "Fixture head")
    head = git("rev-parse", "HEAD")

    common = {"base": base, "head": head, "changedFiles": ["OrderService.java"]}
    deleted_line_hash = sha256(b"-        if (!orderPolicy.validateOrderAccess(orderId)) {").hexdigest()
    agent = common | {
        "kind": "AGENT_DIFF",
        "probes": [
            {"path": "OrderService.java", "startLine": 6, "endLine": 6,
             "expectedContentSha256": deleted_line_hash},
            {"path": "OrderService.java", "startLine": 400, "endLine": 400,
             "expectedErrorCode": "DIFF_RANGE_OUT_OF_BOUNDS"},
        ],
    }
    standard = common | {
        "kind": "STANDARD_CONTEXT", "expectedEvidencePaths": ["OrderService.java", "OrderPolicy.java"],
        "targetContextChars": 6000,
    }
    for name, material in (("agent", agent), ("standard", standard)):
        (folder / f"{name}.json").write_text(json.dumps(material), encoding="utf-8")


if __name__ == "__main__":
    main()
