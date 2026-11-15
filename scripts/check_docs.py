#!/usr/bin/env python3
"""Validate the repository's Markdown: every relative link and image must exist, and every #anchor must match a heading.

Offline and deterministic (external URLs are not fetched; see docs/maintainers/releasing.md for the manual external-link check).
Usage: python scripts/check_docs.py            exit code 1 and a list of problems if anything is broken.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"node_modules", ".venv", "dist", "data", "logs", ".git", ".pytest_cache", ".ruff_cache"}
LINK = re.compile(r"(?<!\\)!?\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_REF = re.compile(r"""<(?:img|a|source)\b[^>]*?\b(?:src|href|srcset)=["']([^"']+)["']""", re.I)
FENCE = re.compile(r"^(```|~~~)")


def markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts))


def slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation except - and _, spaces to -."""
    text = re.sub(r"<[^>]+>", "", heading).strip().lower()
    text = re.sub(r"[`*_~]", lambda m: "_" if m.group(0) == "_" else "", text)
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    out: dict[str, int] = {}
    found: set[str] = set()
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m and not in_code:
            base = slug(m.group(1))
            n = out.get(base, 0)
            found.add(base if n == 0 else f"{base}-{n}")
            out[base] = n + 1
        for a in re.findall(r"<a\s+(?:name|id)=[\"']([^\"']+)[\"']", line):
            found.add(a)
    return found


def links(path: Path) -> list[tuple[int, str]]:
    out, in_code = [], False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        if in_code:
            continue
        line = re.sub(r"`[^`]*`", "", line)          # inline code is not a link
        out += [(n, m) for m in LINK.findall(line)] + [(n, m) for m in HTML_REF.findall(line)]
    return out


def check() -> list[str]:
    problems: list[str] = []
    cache: dict[Path, set[str]] = {}
    for md in markdown_files():
        for n, target in links(md):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
                continue                               # external URL, mailto: ... (not fetched)
            ref, _, frag = target.partition("#")
            dest = md if not ref else (md.parent / unquote(ref)).resolve()
            where = f"{md.relative_to(ROOT)}:{n}"
            if ref and not dest.exists():
                problems.append(f"{where}: missing file {ref}")
                continue
            if frag and dest.suffix == ".md":
                if dest not in cache:
                    cache[dest] = anchors(dest)
                if frag.lower() not in cache[dest]:
                    problems.append(f"{where}: no heading for #{frag} in {dest.relative_to(ROOT)}")
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p)
    print(f"{len(markdown_files())} Markdown files checked: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
