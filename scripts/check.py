#!/usr/bin/env python3
# Copyright (c) 2026, The Shekyl Foundation
#
# All rights reserved.
# BSD-3-Clause
"""The checks this repository's pull requests and `main` run (`check.yml`).

Two things here can be wrong without anything in shekyl-core noticing,
because shekyl-core holds every chain to its own pin:

1. **The workflows' embedded Python.** `actionlint` (the workflow's own
   step) lints the YAML and, through shellcheck, each `run:` script; it
   does not read a heredoc of Python. Each `<<'PY'` block in
   `.github/workflows/*.yml` is compiled here.
2. **The release record.** `RELEASES.md` names each published version, and
   each version's manifest is committed at
   `chains/<chain>/<commit>/manifest.json` (README, "Publishing"): the
   only copy that outlives the publish run's seven-day artifact. Every
   entry names exactly one committed manifest under its own chain and
   commit, every committed manifest has its entry, and each manifest is
   the one the registry published: its SHA-256 is the `manifest.json`
   layer's digest in the artifact the entry's digest names. The artifact's
   OCI manifest is read from GHCR's registry API by that digest,
   anonymously (the packages are public), and is itself held to the
   digest before anything in it is trusted.

    check.py              both checks against this checkout and the registry
    check.py --selftest   plant each failure and prove it refused

Exit status: 0 clean, 1 a check refused (each problem printed), 2 usage.
Rule 47: a record with no entry at all is refused, not passed. Rule 46:
every verdict is this process's exit status.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import textwrap
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "https://ghcr.io"
NAMESPACE = "shekyl-foundation/test-chains"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
TITLE = "org.opencontainers.image.title"
MANIFEST_FILE = "manifest.json"

HEADING = re.compile(r"^## (?P<chain>[a-z0-9][a-z0-9-]*) at shekyl-core `(?P<short>[0-9a-f]{7,40})`$")
DIGEST = re.compile(r"`(sha256:[0-9a-f]{64})`")
MANIFEST_LINK = re.compile(r"\]\((chains/[^)]+/manifest\.json)\)")
COMMITTED = re.compile(r"^chains/(?P<chain>[a-z0-9][a-z0-9-]*)/(?P<commit>[0-9a-f]{40})/manifest\.json$")


@dataclass(frozen=True)
class Entry:
    """One release note: a chain's published version."""

    chain: str
    short: str
    digest: str
    manifest: str


# Fetch an artifact's OCI manifest: (chain, digest) -> the manifest's bytes.
Fetch = Callable[[str, str], bytes]


def entries(text: str) -> tuple[list[Entry], list[str]]:
    """The release notes in `text`, and what is wrong with any of them."""
    found: list[Entry] = []
    problems: list[str] = []
    sections = re.split(r"(?m)^(?=## )", text)
    for section in sections:
        lines = section.splitlines()
        if not lines or not lines[0].startswith("## "):
            continue
        head = HEADING.match(lines[0])
        if not head:
            problems.append(f"`{lines[0]}` is not `## <chain> at shekyl-core `<commit>``")
            continue
        body = "\n".join(lines[1:])
        digest_lines = [line for line in lines[1:] if line.startswith("- **Digest:**")]
        manifests = MANIFEST_LINK.findall(body)
        name = f"{head['chain']} at {head['short']}"
        if len(digest_lines) != 1 or not DIGEST.search(digest_lines[0]):
            problems.append(f"{name}: needs one `- **Digest:**` line naming `sha256:<64 hex>`")
            continue
        if len(manifests) != 1:
            problems.append(f"{name}: needs one link to its committed manifest, has {len(manifests)}")
            continue
        found.append(
            Entry(head["chain"], head["short"], DIGEST.search(digest_lines[0])[1], manifests[0])
        )
    return found, problems


def committed(root: Path) -> tuple[set[str], list[str]]:
    """The manifests committed under `chains/`, and any misplaced file."""
    paths: set[str] = set()
    problems: list[str] = []
    chains = root / "chains"
    if not chains.is_dir():
        return paths, problems
    for path in sorted(chains.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if COMMITTED.match(relative):
            paths.add(relative)
        else:
            problems.append(f"{relative} is not chains/<chain>/<40-hex commit>/manifest.json")
    return paths, problems


def fetch_from_registry(chain: str, digest: str) -> bytes:
    """`chain`'s artifact manifest at `digest`, from GHCR, anonymously."""
    scope = f"repository:{NAMESPACE}/{chain}:pull"
    with urllib.request.urlopen(f"{REGISTRY}/token?scope={scope}", timeout=60) as reply:
        token = json.load(reply)["token"]
    request = urllib.request.Request(
        f"{REGISTRY}/v2/{NAMESPACE}/{chain}/manifests/{digest}",
        headers={"Authorization": f"Bearer {token}", "Accept": OCI_MANIFEST},
    )
    with urllib.request.urlopen(request, timeout=60) as reply:
        return reply.read()


def published_manifest_digest(chain: str, digest: str, fetch: Fetch) -> str:
    """The `manifest.json` layer's SHA-256 (hex) in the artifact at `digest`.

    The fetched bytes must hash to `digest` before anything in them counts.
    """
    body = fetch(chain, digest)
    got = "sha256:" + hashlib.sha256(body).hexdigest()
    if got != digest:
        raise ValueError(f"the registry answered {digest} with bytes that hash to {got}")
    layers = [
        layer
        for layer in json.loads(body).get("layers", [])
        if layer.get("annotations", {}).get(TITLE) == MANIFEST_FILE
    ]
    if len(layers) != 1:
        raise ValueError(f"the artifact at {digest} has {len(layers)} `{MANIFEST_FILE}` layers")
    layer = layers[0]["digest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", layer):
        raise ValueError(f"the artifact at {digest} names its manifest layer `{layer}`")
    return layer.removeprefix("sha256:")


def check_record(root: Path, fetch: Fetch) -> list[str]:
    """Every problem with the release record in `root`."""
    release_notes = root / "RELEASES.md"
    if not release_notes.is_file():
        return ["RELEASES.md is missing"]
    notes, problems = entries(release_notes.read_text())
    paths, misplaced = committed(root)
    problems += misplaced
    if not notes and not problems:
        problems.append("RELEASES.md names no published version (rule 47: the subject is absent)")
    named: set[str] = set()
    for entry in notes:
        name = f"{entry.chain} at {entry.short}"
        placed = COMMITTED.match(entry.manifest)
        if not placed:
            problems.append(f"{name}: its manifest link `{entry.manifest}` is not chains/<chain>/<commit>/manifest.json")
            continue
        if placed["chain"] != entry.chain or not placed["commit"].startswith(entry.short):
            problems.append(f"{name}: its manifest link `{entry.manifest}` is another chain's or commit's")
            continue
        if entry.manifest in named:
            problems.append(f"{name}: `{entry.manifest}` is named by two entries")
            continue
        named.add(entry.manifest)
        if entry.manifest not in paths:
            problems.append(f"{name}: `{entry.manifest}` is not committed")
            continue
        ours = hashlib.sha256((root / entry.manifest).read_bytes()).hexdigest()
        try:
            theirs = published_manifest_digest(entry.chain, entry.digest, fetch)
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as fault:
            problems.append(f"{name}: {fault}")
            continue
        if ours != theirs:
            problems.append(
                f"{name}: `{entry.manifest}` hashes to {ours}; the published artifact's manifest is {theirs}"
            )
    for path in sorted(paths - named):
        problems.append(f"`{path}` has no entry in RELEASES.md")
    return problems


def check_workflow_python(root: Path) -> list[str]:
    """Every embedded `<<'PY'` block in the workflows that does not compile."""
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        lines = workflow.read_text().splitlines()
        index = 0
        while index < len(lines):
            if not re.search(r"<<\s*'PY'\s*$", lines[index]):
                index += 1
                continue
            start = index + 1
            end = start
            while end < len(lines) and lines[end].strip() != "PY":
                end += 1
            if end == len(lines):
                problems.append(f"{workflow.name}:{start}: a `<<'PY'` block with no closing `PY`")
                break
            source = textwrap.dedent("\n".join(lines[start:end]))
            try:
                compile(source, f"{workflow.name}:{start + 1}", "exec")
            except SyntaxError as fault:
                problems.append(f"{workflow.name}:{start + 1}: {fault}")
            index = end + 1
    return problems


def selftest() -> int:
    """Plant each failure; every one must be refused, and a clean record pass."""
    manifest = b'{"format_version": 6}\n'
    layer = hashlib.sha256(manifest).hexdigest()
    commit = "ab" * 20

    def artifact(layer_digest: str) -> bytes:
        return json.dumps(
            {"layers": [{"digest": f"sha256:{layer_digest}", "annotations": {TITLE: MANIFEST_FILE}}]}
        ).encode()

    good_body = artifact(layer)
    good_digest = "sha256:" + hashlib.sha256(good_body).hexdigest()

    def note(digest: str = good_digest, path: str = f"chains/demo/{commit}/manifest.json") -> str:
        return (
            "# Release notes\n\n"
            f"## demo at shekyl-core `{commit[:10]}`\n\n"
            f"- **Digest:** `{digest}`, published by run 1.\n"
            f"- **Manifest:** [`{path}`]({path})\n"
        )

    def fetch_good(_chain: str, digest: str) -> bytes:
        return good_body if digest == good_digest else b"{}"

    def tree(notes: str | None, files: dict[str, bytes]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="check-selftest-"))
        if notes is not None:
            (root / "RELEASES.md").write_text(notes)
        for relative, data in files.items():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(data)
        return root

    placed = {f"chains/demo/{commit}/manifest.json": manifest}
    cases: list[tuple[str, Path, Fetch, bool]] = [
        ("a clean record", tree(note(), placed), fetch_good, True),
        ("no RELEASES.md", tree(None, placed), fetch_good, False),
        ("no entry at all", tree("# Release notes\n", {}), fetch_good, False),
        ("an entry whose manifest is not committed", tree(note(), {}), fetch_good, False),
        (
            "a committed manifest with no entry",
            tree(note(), {**placed, f"chains/demo/{'cd' * 20}/manifest.json": manifest}),
            fetch_good,
            False,
        ),
        (
            "a manifest that is not the published one",
            tree(note(), {f"chains/demo/{commit}/manifest.json": b"{}\n"}),
            fetch_good,
            False,
        ),
        (
            "a registry answer that does not hash to its digest",
            tree(note(), placed),
            lambda _chain, _digest: artifact(layer) + b" ",
            False,
        ),
        (
            "a link to another commit's manifest",
            tree(note(path=f"chains/demo/{'cd' * 20}/manifest.json"), {f"chains/demo/{'cd' * 20}/manifest.json": manifest}),
            fetch_good,
            False,
        ),
        ("a misplaced file under chains/", tree(note(), {**placed, "chains/demo/notes.txt": b"x"}), fetch_good, False),
    ]
    failed = 0
    for name, root, fetch, clean in cases:
        problems = check_record(root, fetch)
        if (not problems) != clean:
            print(f"selftest FAILED: {name}: {problems or 'passed'}")
            failed += 1
        else:
            print(f"selftest ok: {name}")

    workflows = Path(tempfile.mkdtemp(prefix="check-selftest-")) / ".github" / "workflows"
    workflows.mkdir(parents=True)
    good = "jobs:\n  x:\n    steps:\n      - run: |\n          python3 - <<'PY'\n          print('ok')\n          PY\n"
    (workflows / "good.yml").write_text(good)
    if check_workflow_python(workflows.parent.parent):
        print("selftest FAILED: compiling Python passed through a heredoc")
        failed += 1
    else:
        print("selftest ok: a heredoc of Python that compiles")
    (workflows / "bad.yml").write_text(good.replace("print('ok')", "print('ok'"))
    if not check_workflow_python(workflows.parent.parent):
        print("selftest FAILED: a heredoc of Python with a syntax error passed")
        failed += 1
    else:
        print("selftest ok: a heredoc of Python with a syntax error is refused")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if argv:
        print(__doc__)
        return 2
    problems = check_workflow_python(ROOT)
    problems += check_record(ROOT, fetch_from_registry)
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        return 1
    notes, _ = entries((ROOT / "RELEASES.md").read_text())
    print(f"the workflows' Python compiles; {len(notes)} release note(s), each manifest the published one")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
