# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com/); versions follow semantic versioning.

## [Unreleased] — 2.0.0

### Added
- **Interview Intelligence 2.0** ([docs/evaluation.md](docs/evaluation.md)): category evaluation profiles (SQL, Python, data
  engineering, ML, system design, software engineering, behavioural, general) with extra dimensions (conceptual understanding,
  problem-solving, edge cases, trade-offs); verbatim evidence quotes verified against the answer; ungrounded "misconceptions" shown but
  never counted; deterministic consistency rules; answer classification (correct / correct but incomplete / partially correct /
  incorrect / no attempt / uncertain); provenance on every evaluation (prompt, profile and rubric versions, model route, temperature,
  input hash). Still one grading call per answer.
- **Adaptive interviews** ([docs/adaptive-interviews.md](docs/adaptive-interviews.md)): a question pool and a deterministic engine with
  six strategies (progressive, deep-dive, practical, conceptual, mixed, resume-based), four levels with confidence-weighted, cool-down
  and anti-oscillation rules, topic coverage, one revisit of weak topics, evidence-based early end, and clarify / deepen / scenario /
  probe-gap follow-ups with a loop guard. Every decision is persisted with a plain-language reason.
- **Time limits** for fixed and adaptive interviews (paused time excluded).
- **Candidate profile** for every resume ([docs/resume-intelligence.md](docs/resume-intelligence.md)): skill inventory with
  evidence-based confidence and source line references, extraction-quality check against the raw text, projects, experience summary
  and gaps, technology relationships, clarification areas, prompt-injection warnings, practice history and unexplored areas. Offline,
  no model call.
- **Offline claim-grounded resume questions** (`resume_auto`): technology implications and a project deep-dive progression, each tied
  to its resume excerpt; same per-resume cloud-consent rule as AI-written questions.
- **Report analytics**: classification breakdown, difficulty-wise and conceptual-vs-practical performance, profile usage, progress per
  topic versus your previous attempt, learning plan, adaptive decision timeline, resume coverage.
- **Share-safe exports** (`?redact=true`, PDF/Markdown/JSON): allow-list of scores and topics; answers, grader prose, follow-ups,
  resume names, labels and excerpts removed.
- **Database backup download** (`GET /api/backup`, Settings → Profile) and a read-only evaluation-profile view in Settings.
- Docs: architecture decision records, contribution guide, security policy, issue/PR templates, tag-triggered release workflow.

### Changed
- Questions that match a category profile are scored with that profile's weights, so their scores can differ from 1.x. Uncategorised
  questions use the *general* profile, identical to 1.x. Your rubric weights in Settings still apply to every profile.
- A short answer containing "I don't know" that the grader still found nothing of value in is capped at 2 per dimension.
- Database schema v6 (additive: new columns and tables; existing data untouched; upgrades automatically from every earlier version).

### Security
- Resume lines that look like instructions to an AI are flagged and excluded from offline questions and excerpts.
- Backups are written inside the private data folder (never the shared temp folder) and removed after download.

## [1.0.0]

Initial public release: local mock interviews with question bank, voice, Whisper microphone input, follow-ups, reports, resumes and
optional Ollama cloud mode.
