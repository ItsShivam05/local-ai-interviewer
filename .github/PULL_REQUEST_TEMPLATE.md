## What and why

<!-- What does this change, and what problem does it solve? Link issues with "Fixes #123". -->

## How it was tested

- [ ] `python -m pytest backend` passes
- [ ] `npm run typecheck && npm test && npm run build` pass (frontend changes)
- [ ] New behaviour has tests; no existing test was weakened or removed
- [ ] Manually checked in the app (describe):

## Checklist

- [ ] No new network calls in local mode; cloud use stays opt-in
- [ ] Database changes are additive migrations with an upgrade test
- [ ] Docs / `CHANGELOG.md` updated
