// Groq CLOUD mode in a real browser against a FAKE Groq server (no network, no account): consent, write-only key, connection test,
// a graded interview with a cloud-written follow-up, the cost tracker, the spending limit, the fallback model, switching back, and
// a hard cap on how many cloud calls the whole run is allowed to make.
import { BASE, check, clickText, launch, reportIssues, shot, sleep, startBackend, textOf, waitText } from "./lib.mjs";
import { startFakeCloud } from "./fakecloud.mjs";
import { SWEEP } from "./sweep-lib.mjs";

const GOOD = "good-key-0123456789", WRONG = "wrong-key-0123456789";
const fc = await startFakeCloud({ key: GOOD });
const be = await startBackend({ GROQ_BASE_URL: `${fc.url}/openai/v1`, GROQ_API_KEY: "" });
const { browser, page, issues } = await launch({ width: 1280, height: 1000 });
const api = async (path, opts) => (await fetch(`${BASE}${path}`, opts)).json();
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const put = (path, body) => api(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const aiTab = async () => { await page.goto(`${BASE}/#/settings`, { waitUntil: "networkidle0" }); await clickText(page, ".tabbar button", "AI models"); await page.waitForSelector(".ai-page"); await sleep(300); };
const tagline = () => page.$eval(".sb-name small", (e) => e.textContent);
const cooldown = () => sleep(6400);       // the page (and the server) refuse back-to-back connection tests: this protects the rate limit, so wait it out
let setId, iv;
try {
  setId = (await api("/api/sets"))[0].id;
  await post(`/api/sets/${setId}/questions`, { text: "How do you make a data pipeline idempotent?", topic: "ETL" });

  // ---------------------------------------------------------------- default: local, and the cloud has never been contacted
  await page.goto(BASE, { waitUntil: "networkidle0" });
  check((await tagline()) === "Private · On-device", "default engine is local: the sidebar says Private · On-device");
  await aiTab();
  check(await page.$eval('button[aria-label="Use the local model"]', (b) => b.getAttribute("aria-checked") === "true"), "Settings → AI models: 'On this computer' is selected by default");
  check((await page.$('input[aria-label="Groq API key"]')) === null, "no API key field is shown until cloud is chosen");
  let st = await fc.stats();
  check(st.tags === 0 && st.chats.length === 0 && st.authFailures === 0, "the cloud has not been contacted at all (0 requests)");

  // ---------------------------------------------------------------- choosing cloud: consent first, nothing is switched yet
  await page.click('button[aria-label="Use Groq cloud models"]');
  await waitText(page, "Before you turn this on");
  const consentText = await textOf(page, ".ai-page");
  check(/Sent to Groq’s servers[\s\S]*Your answers/.test(consentText) && /Stays on this computer[\s\S]*Your voice recordings/.test(consentText), "the consent card lists exactly what is sent and what stays local");
  const prov = (await api("/api/ai")).provider;
  check(/up to 30 days/.test(await textOf(page, '[data-testid="retention"]')) && /Groq may keep request logs for up to 30 days/.test(consentText), "the consent card says Groq may log requests for up to 30 days");
  const links = await page.$$eval(".ai-page a", (a) => a.map((x) => ({ href: x.getAttribute("href"), target: x.target, rel: x.rel, text: x.textContent })));
  check(links.some((l) => l.href === prov.data_url && l.target === "_blank" && /noopener/.test(l.rel)) && links.some((l) => l.href === prov.keys_url && /Groq/.test(prov.name) && l.target === "_blank"), "the data-policy and key links come from the API and open in a new tab");
  check(/Create a free key at/.test(consentText) && /GROQ_API_KEY/.test(consentText), "the key card says 'Create a free key at' and mentions GROQ_API_KEY in .env");
  check(await page.$eval(".ai-page .btn.primary.big", (b) => b.disabled), "'Use cloud models' stays disabled until you add a key AND tick the consent box");
  check((await api("/api/ai")).mode === "local", "choosing the card changes nothing on the server");

  // ---------------------------------------------------------------- a WRONG key first: rejected clearly, and not retried
  await page.type('input[aria-label="Groq API key"]', WRONG);
  check(await page.$eval(".ai-page .btn.primary.big", (b) => b.disabled), "a key alone is not enough: the consent box is still required");
  await page.click('.ai-page input[type=checkbox]');
  check(!(await page.$eval(".ai-page .btn.primary.big", (b) => b.disabled)), "with a key and consent the button enables");
  await clickText(page, "button", "Use cloud models");
  await waitText(page, "Cloud mode is on");
  await page.waitForFunction(() => /voice stays local/.test(document.querySelector(".sb-name small")?.textContent || ""), { timeout: 5000 }).catch(() => {});
  check((await tagline()) === "Cloud AI · voice stays local", "the sidebar now says Cloud AI · voice stays local (no false 'on-device' claim)");
  check((await page.$$eval(".ai-page input[type=password]", (i) => i.length)) === 0, "the key field disappears after saving (the key is write-only)");
  const body1 = await page.evaluate(() => document.documentElement.innerHTML + JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  check(!body1.includes(WRONG) && !(await (await fetch(`${BASE}/api/ai`)).text()).includes(WRONG), "the key is nowhere in the page, storage or any API response");
  check(/saved ••••6789/.test(await textOf(page, ".ai-page")), "only the last four characters are shown (••••6789)");
  await clickText(page, "button", "Test connection (free)");
  await waitText(page, "Could not connect");
  check(/rejected the API key/.test(await textOf(page, ".ai-page")), "a wrong key is reported plainly: 'rejected the API key'");
  st = await fc.stats();
  check(st.authFailures === 1 && st.chats.length === 0, `exactly one rejected request, no model call (${st.authFailures} auth failure)`);
  check(await page.$eval(".ai-page .btn.primary", (b) => b.disabled) || (await page.$$eval(".ai-page button", (bs) => bs.filter((b) => /Test connection/.test(b.textContent)).every((b) => b.disabled))), "the test button is locked for a few seconds after use (rate-limit protection)");

  // ---------------------------------------------------------------- replace the key with the right one, then ONE click: list models + tiny message
  await clickText(page, "button", "Replace key");
  await page.type('input[aria-label="Groq API key"]', GOOD);
  await clickText(page, "button", "Save key");
  await waitText(page, "Key saved");
  await cooldown();
  await clickText(page, "button", "Send one tiny test message");
  await waitText(page, "Test message answered by");
  const t1 = await textOf(page, ".ai-page");
  check(/Connected · 4 cloud models available/.test(t1) && /Connected\. The models you chose are available\./.test(t1) && /Test message answered by openai\/gpt-oss-120b: “ok” \(30 \+ 10 tokens\)/.test(t1), "connection OK: 4 models listed and the tiny message answered by openai/gpt-oss-120b");
  check((await page.$$eval(".ai-role .badge.ok", (b) => b.length)) === 3, "all three chosen models are marked 'available'");
  st = await fc.stats();
  check(st.tags === 1 && st.chats.length === 1 && st.chats[0].kind === "test", `that click made exactly 1 listing + 1 tiny message (tags ${st.tags}, chats ${st.chats.length})`);

  // ---------------------------------------------------------------- models: exactly three, one dropdown per role, "(recommended)" on each role's own, price beside it
  const sel = (t) => `select[aria-label="${t} model"]`;
  const price = () => page.$$eval(".ai-role .ai-price", (e) => e.map((x) => x.textContent.replace(/\s+/g, " ").trim()));
  const BIG = "openai/gpt-oss-120b", SMALL = "openai/gpt-oss-20b";
  const ALL = [BIG, SMALL];
  const rec = { Grader: BIG, "Fallback / second opinion": SMALL, Conversation: SMALL };
  for (const [role, model] of Object.entries(rec)) {
    const info = await page.$eval(sel(role), (el) => ({ value: el.value, opts: [...el.options].map((o) => [o.value, o.textContent]) }));
    check(info.value === model && info.opts.map((o) => o[0]).join("|") === ALL.join("|"), `${role}: the dropdown offers exactly the two supported models`);
    check(info.opts.filter((o) => /recommended/.test(o[1])).map((o) => o[0]).join() === model, `${role}: only "${model}" is marked (recommended)`);
  }
  check((await page.$$eval("optgroup, option[value=__custom__]", (e) => e.length)) === 0 && (await page.$$(".ai-custom, input[aria-label$=' model name']")).length === 0, "no 'Other…' entry and no typing box: only the two models can be used");
  check((await price()).join(" || ") === "$0.150 in · $0.600 out per 1M tokens || $0.075 in · $0.300 out per 1M tokens || $0.075 in · $0.300 out per 1M tokens", `each row shows its price: ${(await price()).join("  |  ")}`);
  await page.select(sel("Grader"), SMALL);
  check((await price())[0] === "$0.075 in · $0.300 out per 1M tokens" && (await page.$$eval(".ai-role .badge.ok", (b) => b.length)) === 3, "the price beside a dropdown follows the model you pick");
  await page.select(sel("Fallback / second opinion"), SMALL);
  check(/same model as the grader/.test(await textOf(page, ".ai-page")), "choosing the grader's own model as fallback shows a warning");
  await page.select(sel("Grader"), BIG); await page.select(sel("Fallback / second opinion"), SMALL);
  check(!/same model as the grader/.test(await textOf(page, ".ai-page")) && (await page.$eval(sel("Grader"), (e) => e.value)) === BIG, "back to the recommended models: the warning is gone");
  await page.waitForSelector(".price-tbl");
  const planText = await textOf(page, ".ai-page");
  check(/Free plan[\s\S]*rate-limited per model[\s\S]*per-minute[\s\S]*daily allowance/.test(planText) && /estimates of what the same use would cost on a paid plan/.test(planText), "the page explains the Free plan (rate-limited per model) and that costs are estimates of a paid plan");
  check(!/credits|deep\s?seek|ollama\.com/i.test(planText), "the cloud settings never mention credits, other vendors or Ollama’s site");
  check((await page.$$eval(".price-tbl tbody tr", (r) => r.map((x) => x.querySelector("b").textContent))).join("|") === ALL.join("|"), "the price table lists just these two models");
  const dailyInput = 'input[placeholder="no limit"]';
  await page.click(dailyInput, { count: 3 }); await page.type(dailyInput, "5");
  check(await textOf(page, ".ai-page").then((t) => /unsaved changes/.test(t)), "unsaved changes are announced");
  await clickText(page, "button", "Save changes");
  await waitText(page, "Saved");
  check((await api("/api/ai")).config.daily_budget_usd === 5, "the daily limit was saved");
  await shot(page, "cloud-ai-tab-light");
  const sweep = await page.evaluate(SWEEP);
  check(sweep.length === 0, `AI models tab (cloud view) passes the accessibility/structure sweep${sweep.length ? ": " + sweep.join(" | ") : ""}`);

  // ---------------------------------------------------------------- an interview graded by the cloud, follow-up written by the conversation model
  await page.goto(`${BASE}/#/setup`, { waitUntil: "networkidle0" });
  await page.waitForSelector(".sec"); await sleep(700);
  const setupText = await textOf(page);
  check(/Cloud AI ready · openai\/gpt-oss-120b/.test(setupText) && /AI engine\s*Groq cloud/.test(setupText), "Setup shows 'Cloud AI ready · openai/gpt-oss-120b' and the AI engine");
  const est = await textOf(page, '[data-testid="cost-estimate"]');
  check(/Estimated cost: up to \$0\.00\d+/.test(est) && /sent to Groq’s servers/.test(est), `Setup shows an honest upper-bound cost estimate and the disclosure (${est.replace(/\s+/g, " ").slice(0, 90)})`);
  check(!setupText.includes("Low free memory") && !/Local model ready/.test(setupText), "no local-memory warning or 'runs offline' claim in cloud mode");
  await clickText(page, "button", "Start Interview");
  await page.waitForSelector("#answer", { timeout: 15000 });
  iv = Number((await page.evaluate(() => location.hash)).split("/").pop());
  await page.waitForFunction(() => /Cloud AI/.test(document.querySelector(".fs-top")?.textContent || ""), { timeout: 8000 }).catch(() => {});
  check(/Cloud AI/.test(await textOf(page, ".fs-top")) && (await page.$(".fs-top .badge svg")) !== null, "the interview screen shows a Cloud AI badge with a cloud icon");
  const before = (await fc.stats()).chats.length;
  await page.type("#answer", "A partial answer: I would deduplicate with a key.");
  await clickText(page, "button", "Submit Answer");
  await page.waitForFunction(() => /How would you choose a merge key/.test(document.querySelector(".interview-q")?.textContent || ""), { timeout: 30000 });
  const mid = await textOf(page);
  check(!/Graded by|Verdict|Strengths|\/ 10|Score\b/.test(mid), "no score, verdict or feedback is shown in the middle of the interview: the follow-up simply appears");
  const fq = await textOf(page, ".interview-q");
  check(fq === "How would you choose a merge key when some records arrive late?", `the follow-up was written by the conversation model, not the grader's draft ("${fq.slice(0, 60)}…")`);
  st = await fc.stats();
  const calls = st.chats.slice(before);
  check(calls.map((c) => `${c.kind}:${c.model}`).join(",") === "evaluation:openai/gpt-oss-120b,followup:openai/gpt-oss-20b", `grading went to gpt-oss-120b, the follow-up to gpt-oss-20b (${calls.map((c) => c.kind + ":" + c.model).join(", ")})`);
  check(st.chats.every((c) => !c.hasFormat) && st.chats.filter((c) => c.kind !== "test").every((c) => c.schemaInPrompt), "no request used `response_format` (the app does not rely on structured outputs); the JSON schema was in the prompt instead");
  check(st.chats.find((c) => c.kind === "evaluation").effort === "low" && st.chats.find((c) => c.kind === "evaluation").includeReasoning === false, "gpt-oss was asked for low reasoning effort and no reasoning text (reasoning tokens count against the limits)");
  await page.type("#answer", "I would merge on the business key and keep a processed-batch table.");
  await clickText(page, "button", "Submit Answer");
  await waitText(page, "Interview complete");
  await page.waitForSelector('[data-testid="final-score"] .ring', { timeout: 10000 });
  check(/final score/.test(await textOf(page, '[data-testid="final-score"]')), "when the interview ends the final score appears right away");
  await sleep(1200);
  await page.goto(`${BASE}/#/report/${iv}`, { waitUntil: "networkidle0" });
  await page.waitForSelector('[data-testid="scorecard"]');
  const gradedBy = await page.$eval('[data-testid="graded-by"]', (e) => e.textContent);
  check(/Graded by openai\/gpt-oss-120b \(Groq cloud\)/.test(gradedBy), "the report's feedback says which model graded the answer: openai/gpt-oss-120b (Groq cloud)");

  // ---------------------------------------------------------------- the cost tracker: Model usage, sidebar, report
  await page.goto(`${BASE}/#/usage`, { waitUntil: "networkidle0" });
  await page.waitForSelector(".usage-tbl tbody tr");
  await page.waitForFunction(() => document.body.innerText.includes("Estimated cloud cost"), { timeout: 8000 });
  const usageText = await textOf(page);
  check(/Grading an answer/.test(usageText) && /Writing a follow-up question/.test(usageText) && /Connection test message/.test(usageText) && /Report summary/.test(usageText), "Model usage names every cloud call type in plain English");
  const kpi = await textOf(page, '[data-testid="cost-kpi"]');
  const cost = Number((kpi.match(/\$(0\.\d+)/) || [])[1]);
  check(cost >= 0.0013 && cost < 0.0014 && /5 cloud calls/.test(kpi), `the estimated cloud cost adds up (${kpi.replace(/\s+/g, " ").trim()})`);
  check((await page.$$eval(".usage-tbl .badge.accent", (b) => b.length)) > 0 && /Cloud spending/.test(usageText) && /of \$5\.00/.test(usageText), "cloud rows carry a ☁ badge and the spending card shows today's spend against the $5.00 limit");
  const apiUsage = await api("/api/usage");
  const evalRow = apiUsage.summary.find((s) => s.purpose === "evaluation");
  check(evalRow.provider === "cloud" && evalRow.calls === 2 && Math.abs(evalRow.cost_usd - 0.00084) < 1e-9, "two gradings × (1,200 in, 400 out) at gpt-oss rates = $0.00084");
  const sidebar = await textOf(page, ".sidebar .status");
  check(/Groq cloud/.test(sidebar) && new RegExp(`Spent today \\$0\\.00\\d+`).test(sidebar), "the sidebar status panel shows Groq cloud and the spend today");
  await clickText(page, ".seg button", "This computer");
  await page.waitForFunction(() => { const t = document.querySelector(".usage-tbl")?.textContent || ""; return t.includes("Reading a question aloud") && !t.includes("Grading an answer"); }, { timeout: 8000 }).catch(() => {});
  const localOnly = await textOf(page, ".usage-tbl");
  check(!/Grading an answer/.test(localOnly) && !/Writing a follow-up question/.test(localOnly), "'This computer' hides every cloud call (only the local voice is left)");
  await clickText(page, ".seg button", "Cloud", { exact: true });
  await page.waitForFunction(() => { const t = document.querySelector(".usage-tbl")?.textContent || ""; return t.includes("Grading an answer") && !t.includes("Reading a question aloud"); }, { timeout: 8000 }).catch(() => {});
  const cloudOnly = await textOf(page, ".usage-tbl");
  check(/Grading an answer/.test(cloudOnly) && !/Reading a question aloud/.test(cloudOnly), "'Cloud' shows only the cloud calls");
  await shot(page, "cloud-usage-light");
  await page.goto(`${BASE}/#/report/${iv}`, { waitUntil: "networkidle0" });
  await page.waitForSelector('[data-testid="ai-usage"]');
  const rep = await textOf(page, '[data-testid="ai-usage"]');
  check(/4 model calls/.test(rep) && /estimated cloud cost/.test(rep), `the report shows what this interview cost (${rep.replace(/\s+/g, " ").trim().slice(0, 100)})`);

  // ---------------------------------------------------------------- the spending limit stops calls BEFORE they are made, and can be raised
  iv = (await post("/api/interviews", { set_id: setId, config: { title: "Budget test", max_followups: 0 } })).id;
  await aiTab();
  await page.click(dailyInput, { count: 3 }); await page.type(dailyInput, "0.0001");
  await clickText(page, "button", "Save changes"); await waitText(page, "Saved");
  const callsBefore = (await fc.stats()).chats.length;
  await page.goto(`${BASE}/#/interview/${iv}`, { waitUntil: "networkidle0" });
  await page.waitForSelector("#answer");
  await page.type("#answer", "A strong answer about idempotent loads.");
  await clickText(page, "button", "Submit Answer");
  await waitText(page, "daily cloud budget is used up");
  check((await fc.stats()).chats.length === callsBefore, "with the limit reached NO request was made to the cloud");
  check(/Retry evaluation/.test(await textOf(page)) && /A strong answer about idempotent loads/.test(await textOf(page)), "the answer is kept and Retry is offered");
  await page.goto(`${BASE}/#/setup`, { waitUntil: "networkidle0" }); await page.waitForSelector(".sec"); await sleep(500);
  check(/Daily budget used up/.test(await textOf(page, ".summary")), "Setup warns that the daily budget is used up before you start another interview");
  await aiTab();
  await page.click(dailyInput, { count: 3 }); await page.type(dailyInput, "5");
  await clickText(page, "button", "Save changes"); await waitText(page, "Saved");
  await page.goto(`${BASE}/#/interview/${iv}`, { waitUntil: "networkidle0" });
  await clickText(page, "button", "Retry evaluation");
  await page.waitForFunction(() => /Score/.test(document.body.innerText), { timeout: 30000 });
  check((await fc.stats()).chats.length === callsBefore + 1, "after raising the limit, Retry made exactly one call");

  // ---------------------------------------------------------------- the fallback model rescues grading when the grader is down
  await post(`/api/interviews/${iv}/end`, {});                  // one interview at a time
  const iv2 = (await post("/api/interviews", { set_id: setId, config: { title: "Fallback test", max_followups: 0 } })).id;
  await fc.control({ failNext: [503] });
  await page.goto(`${BASE}/#/interview/${iv2}`, { waitUntil: "networkidle0" });
  await page.waitForSelector("#answer");
  await page.type("#answer", "An answer while the grader is down.");
  await clickText(page, "button", "Submit Answer");
  await waitText(page, "Graded by");
  const gb = await textOf(page, '[data-testid="graded-by"]');
  check(/openai\/gpt-oss-20b/.test(gb) && /openai\/gpt-oss-120b was unavailable/.test(gb), `the feedback explains the fallback (${gb.slice(0, 120)})`);
  st = await fc.stats();
  check(st.chats.slice(-2).map((c) => c.model).join(",") === "openai/gpt-oss-120b,openai/gpt-oss-20b", "exactly two attempts: the grader (503), then the fallback model");

  // ---------------------------------------------------------------- a rate limit (Groq's free plan): the reset time is shown, the answer is kept, one Retry works
  await post(`/api/interviews/${iv2}/end`, {});
  await sleep(2500);                                              // let the closing summary of the previous interview finish first
  const iv3 = (await post("/api/interviews", { set_id: setId, config: { title: "Rate limit test", max_followups: 0 } })).id;
  await page.goto(`${BASE}/#/interview/${iv3}`, { waitUntil: "networkidle0" });
  await page.waitForSelector("#answer");
  await fc.control({ rateLimitNext: [600] });
  const rlBefore = (await fc.stats()).chats.length;
  await page.type("#answer", "An answer while the rate limit is reached.");
  await clickText(page, "button", "Submit Answer");
  await waitText(page, "It resets in");
  const rl = await textOf(page);
  check(/Groq['’]s rate limit for “openai\/gpt-oss-120b”/.test(rl) && /It resets in about 10 minutes\./.test(rl) && !/credit/i.test(rl), "a 429 shows Groq's rate-limit message with the reset time (about 10 minutes) and no mention of credits");
  check((await fc.stats()).chats.length === rlBefore + 1, "a long wait is not slept through: exactly one request was made");
  check(/Retry evaluation/.test(rl) && /An answer while the rate limit is reached/.test(rl), "the answer is kept and Retry is offered");
  await clickText(page, "button", "Retry evaluation");
  await page.waitForFunction(() => /Score/.test(document.body.innerText), { timeout: 30000 });
  check((await fc.stats()).chats.length === rlBefore + 2, "after the limit passes, Retry made exactly one more call");
  await post(`/api/interviews/${iv3}/end`, {});

  // ---------------------------------------------------------------- dark theme for the new tab
  await page.evaluate(() => localStorage.setItem("lai.theme", "dark"));
  await aiTab();
  await shot(page, "cloud-ai-tab-dark");

  // ---------------------------------------------------------------- back to local: the cloud goes quiet again
  await page.evaluate(() => localStorage.setItem("lai.theme", "light"));
  await aiTab();
  await page.click('button[aria-label="Use the local model"]');
  await clickText(page, "button", "Switch back to this computer");
  await waitText(page, "Back on this computer");
  const quiet = (await fc.stats()).chats.length + (await fc.stats()).tags;
  await page.waitForFunction(() => /On-device/.test(document.querySelector(".sb-name small")?.textContent || ""), { timeout: 5000 }).catch(() => {});
  check((await tagline()) === "Private · On-device" && (await api("/api/ai")).mode === "local", "switching back restores 'Private · On-device'");
  for (const h of ["#/home", "#/usage", "#/settings", "#/history", "#/reports"]) { await page.goto(`${BASE}/${h}`, { waitUntil: "networkidle0" }); await sleep(300); }
  check((await fc.stats()).chats.length + (await fc.stats()).tags === quiet, "after switching back, browsing every page made zero cloud requests");
  check(/Cloud AI is off: nothing is sent to any server/.test(await (async () => { await page.goto(`${BASE}/#/settings`, { waitUntil: "networkidle0" }); await sleep(500); return textOf(page); })()), "the privacy list says Cloud AI is off in local mode");

  // ---------------------------------------------------------------- removing the key
  await aiTab();
  await page.click('button[aria-label="Use Groq cloud models"]');
  await clickText(page, "button", "Remove key");
  await page.waitForSelector('[role=dialog]');
  await clickText(page, '[role=dialog] button', "Remove key");
  await waitText(page, "Key removed");
  const after = await api("/api/ai");
  check(after.key.set === false && after.mode === "local", "removing the key deletes it and keeps the app on local");

  // ---------------------------------------------------------------- rate-limit safety: the whole run made only a handful of calls
  st = await fc.stats();
  check(st.chats.length <= 14 && st.tags === 1, `the entire run made only ${st.chats.length} model calls and ${st.tags} model listing (hard cap: 14 calls)`);
  reportIssues(issues, ["api/speech/synthesize net::ERR_ABORTED"]);   // leaving a page mid-sentence cancels the question audio: harmless
} catch (e) { console.log("FAIL  exception: " + (e.stack || e)); process.exitCode = 1; }
finally { await browser.close(); be.proc.kill(); await fc.stop(); }
console.log(process.exitCode ? "\nSOME CHECKS FAILED" : "\nALL CHECKS PASSED");
