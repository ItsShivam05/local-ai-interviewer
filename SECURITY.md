# Security policy

## Supported versions

Only the latest release on `main` receives fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting
(*Security → Report a vulnerability* on the repository). Include steps to reproduce, the affected version/commit and the impact.
You should get an acknowledgement within a week.

## Security model (summary)

- The server binds to `127.0.0.1` only; the launcher refuses non-loopback hosts. Requests with a non-loopback `Host`, or a cross-site
  `Origin` on state-changing requests, are rejected (DNS-rebinding and CSRF protection).
- Local mode makes no outbound connections except to the local Ollama on loopback. Cloud mode is opt-in, needs explicit consent, never
  acts as a silent fallback, and resumes need a separate per-resume consent before any of their content is sent.
- Candidate answers and resume text are fenced as untrusted data in every prompt; model output is schema-validated and the application
  computes all scores. Resume lines that look like instructions to an AI are flagged in the candidate profile.
- Resume uploads: PDF magic-byte check, size and page limits, server-generated storage names (never the user's file name), files
  `0600` in a `0700` data directory.
- Logs contain ids, sizes and timings — never answers, resume text or API keys.
- `GET /api/backup` and report exports are downloads to the same computer; the backup contains everything, including any saved cloud API
  key. *Share-safe* report exports (`redact=true`) remove answers, evidence quotes and resume excerpts.

## Known limitations

Single-user, no login: anyone with access to your logged-in desktop session can open the app. See README §11.
