"""Repository consistency: docs links, configuration documentation, versions and CI hygiene. Fast, offline, deterministic."""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_check_docs():
    spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts" / "check_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_markdown_links_images_and_anchors_are_valid():
    problems = _load_check_docs().check()
    assert problems == [], "\n".join(problems)


def test_the_docs_checker_catches_broken_links_and_anchors(tmp_path, monkeypatch):
    cd = _load_check_docs()
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Title\n\n## Getting started\n\n[ok](docs/a.md) [bad](docs/missing.md) [anchor](#getting-started) "
                                        "[badanchor](#nope) ![img](docs/x.png) `[not a link](nowhere.md)`\n", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text("# A\n```\n[in code](nowhere.md)\n```\n[back](../README.md#getting-started)\n", encoding="utf-8")
    monkeypatch.setattr(cd, "ROOT", tmp_path)
    problems = cd.check()
    assert len(problems) == 3, problems
    assert any("missing.md" in p for p in problems) and any("#nope" in p for p in problems) and any("x.png" in p for p in problems)


def test_github_heading_slugs():
    cd = _load_check_docs()
    assert cd.slug("5a. Resumes — interview questions about your own experience") == "5a-resumes--interview-questions-about-your-own-experience"
    assert cd.slug("`code` and *emphasis*") == "code-and-emphasis"


def test_every_setting_is_documented_and_every_documented_setting_is_used():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s?([A-Z][A-Z0-9_]+)=", example, re.M))
    sources = "".join(p.read_text(encoding="utf-8") for p in [*(ROOT / "backend" / "app").rglob("*.py"), ROOT / "scripts" / "manage.py"])
    read = set(re.findall(r"""(?:_env\w*|environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']""", (ROOT / "backend/app/config.py").read_text(encoding="utf-8")))
    assert read - documented == set(), f"settings missing from .env.example: {sorted(read - documented)}"
    unused = {k for k in documented if k not in sources}
    assert unused == set(), f".env.example documents settings nothing reads: {sorted(unused)}"


def test_backend_and_frontend_versions_match():
    from app import __version__
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-.](?:dev|rc|a|b)\.?\d+)?", __version__)


def test_workflow_actions_are_pinned_to_commit_shas_and_permissions_are_explicit():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for wf in workflows:
        text = wf.read_text(encoding="utf-8")
        for ref in re.findall(r"uses:\s*([^\s#]+)", text):
            if ref.startswith("./"):
                continue
            assert re.search(r"@[0-9a-f]{40}$", ref), f"{wf.name}: {ref} is not pinned to a full commit SHA"
        assert re.search(r"^permissions:", text, re.M), f"{wf.name}: no top-level permissions block (least privilege)"


def test_no_secrets_or_personal_data_files_are_committed():
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    if not files:          # not a git checkout (e.g. a source archive): nothing to check
        return
    bad = [f for f in files if re.search(r"(^|/)\.env$|\.sqlite3?$|\.pem$|\.key$|(^|/)data/|(^|/)logs/|id_rsa", f)]
    assert bad == []
    secret = re.compile(r"(sk-[A-Za-z0-9]{24,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
    for f in files:
        p = ROOT / f
        if p.suffix in {".png", ".jpg", ".ico", ".woff2", ".pdf"} or not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        assert not secret.search(p.read_text(encoding="utf-8", errors="ignore")), f"possible secret in {f}"
