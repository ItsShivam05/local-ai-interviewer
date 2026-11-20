// Self-test of the e2e harness (lib.mjs): it must never test a server it did not start.
// Review round 0 (2026-11-19): two e2e runs shared port 3100; the second reported PASS against the first one's backend.
// Run: cd frontend && node e2e/harness-selftest.mjs        (needs backend/.venv; uses a free port it picks itself, no browser)
import { createServer } from "node:http";

const free = await new Promise((r) => { const s = createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); }); });
process.env.E2E_PORT = String(free);
const { PORT, startBackend } = await import("./lib.mjs");
let failed = 0;
const check = (ok, what) => { console.log(`${ok ? "PASS" : "FAIL"}  ${what}`); if (!ok) failed++; };

check(PORT === free, `E2E_PORT is honoured (${PORT})`);

// 1. a foreign server that even answers /api/health like ours: the harness must refuse it
const foreign = createServer((req, res) => { res.writeHead(200, { "content-type": "application/json" }); res.end('{"app":"ok"}'); });
await new Promise((r) => foreign.listen(PORT, "127.0.0.1", r));
let refused = null;
try { const b = await startBackend(); b.proc.kill(); } catch (e) { refused = e; }
check(refused && /already in use/.test(refused.message), "refuses a port another server is listening on");
await new Promise((r) => foreign.close(r));

// 2. with the port free it starts its own backend, and that process is the one answering
const b = await startBackend();
check(b.proc.exitCode === null, "its own backend is running");
const health = await (await fetch(`http://127.0.0.1:${PORT}/api/health`)).json();
check(health.bind === `127.0.0.1:${PORT}`, "the backend answering is bound to the test port");
b.proc.kill();

console.log(failed ? `${failed} FAILED` : "ALL CHECKS PASSED");
process.exit(failed ? 1 : 0);
