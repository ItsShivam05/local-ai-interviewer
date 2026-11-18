// A stand-in for Groq's documented API (Bearer key, GET /openai/v1/models, POST /openai/v1/chat/completions as server-sent events, or
// plain JSON when "stream" is false) so the whole cloud experience can be tested in a real browser WITHOUT any network or account.
// It records every request so tests can prove what was sent and how many calls were made. The backend is pointed at `${url}/openai/v1`.
import { createServer } from "node:http";

export const CLOUD_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"];

const evaluation = (answer) => ({
  question_level: "standard", correct_points: ["Explained the core idea"], missing_concepts: /partial/i.test(answer) ? ["Merge keys"] : [], misconceptions: [],
  dimension_scores: { correctness: 7, completeness: 7, depth: 6, practical_application: 6, clarity: 8, production_awareness: 5 }, production_relevant: false,
  verdict_summary: "A solid answer from the cloud grader.", suggested_improvements: ["Add an example"], ideal_answer: "A concise reference answer.", confidence: "high",
  uncertainty_note: "", needs_followup: /partial/i.test(answer), followup_question: /partial/i.test(answer) ? "Draft: which keys would you use?" : "", followup_reason: "A key concept was missing.",
});

export async function startFakeCloud({ key = "good-key-0123456789", port = 0 } = {}) {
  const state = { key, models: [...CLOUD_MODELS], models_calls: 0, chats: [], failNext: [], rateLimitNext: [], authFailures: 0, tinyTokens: [30, 10], gradeTokens: [1200, 400], followTokens: [400, 80] };
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      const send = (code, body) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
      const url = new URL(req.url, "http://x");
      if (url.pathname === "/__stats") return send(200, { tags: state.models_calls, chats: state.chats, authFailures: state.authFailures });
      if (url.pathname === "/__control") { Object.assign(state, JSON.parse(raw || "{}")); return send(200, { ok: true }); }
      const fail = (code, message, headers = {}) => { res.writeHead(code, { "content-type": "application/json", ...headers }); res.end(JSON.stringify({ error: { message, type: "invalid_request_error" } })); };
      if (!url.pathname.startsWith("/openai/v1/")) return fail(404, "unknown path");
      if ((req.headers.authorization || "") !== `Bearer ${state.key}`) { state.authFailures++; return fail(401, "Invalid API Key"); }
      if (url.pathname === "/openai/v1/models" && req.method === "GET") {
        state.models_calls++;
        return send(200, { object: "list", data: state.models.map((m) => ({ id: m, object: "model", created: 1, owned_by: m.split("/")[0], active: true, context_window: 131072 })) });
      }
      if (url.pathname === "/openai/v1/chat/completions" && req.method === "POST") {
        const body = JSON.parse(raw);
        const system = body.messages?.[0]?.content ?? "";
        const user = body.messages?.[body.messages.length - 1]?.content ?? "";
        const kind = /evaluating ONE candidate answer/.test(system) ? "evaluation" : /repair speech-recognition/.test(system) ? "repair" : /Write ONE short follow-up/.test(system) ? "followup"
          : /closing assessment/.test(system) ? "summary" : body.stream === false ? "test" : "other";
        state.chats.push({ kind, model: body.model, stream: body.stream, hasFormat: "response_format" in body, effort: body.reasoning_effort, includeReasoning: body.include_reasoning, maxTokens: body.max_completion_tokens, schemaInPrompt: /OUTPUT FORMAT/.test(system), user: user.slice(0, 400) });
        if (!state.models.includes(body.model)) return fail(404, `The model \`${body.model}\` does not exist or you do not have access to it.`);
        if (state.rateLimitNext.length) { const wait = state.rateLimitNext.shift(); return fail(429, "Rate limit reached for model in organization org_x on tokens per minute (TPM)", { "retry-after": String(wait) }); }
        if (state.failNext.length) { const code = state.failNext.shift(); return fail(code, `simulated ${code}`); }
        const answer = (user.match(/<<<CANDIDATE_ANSWER\n([\s\S]*?)\nCANDIDATE_ANSWER>>>/) || [, ""])[1];
        const payload = kind === "evaluation" ? evaluation(answer)
          : kind === "followup" ? { question: "How would you choose a merge key when some records arrive late?" }
          : kind === "repair" ? { text: answer || "ok", unclear: [] }
          : kind === "summary" ? { overall_summary: "A solid cloud-graded session.", strengths: ["Clear explanations"], knowledge_gaps: [], repeated_misconceptions: [], topics_to_revise: [], recommendations: ["Keep practicing"] }
          : { ok: true };
        const text = kind === "test" ? "ok" : JSON.stringify(payload);
        const [pt, ot] = kind === "test" ? state.tinyTokens : kind === "followup" ? state.followTokens : state.gradeTokens;
        const usage = { queue_time: 0.05, prompt_tokens: pt, prompt_time: 0.3, completion_tokens: ot, completion_time: 4, total_tokens: pt + ot, total_time: 4.3 };
        if (body.stream === false) return send(200, { id: "chatcmpl-1", object: "chat.completion", model: body.model, choices: [{ index: 0, message: { role: "assistant", content: text }, finish_reason: "stop" }], usage });
        res.writeHead(200, { "content-type": "text/event-stream" });
        const ev = (o) => res.write("data: " + JSON.stringify({ id: "chatcmpl-1", object: "chat.completion.chunk", model: body.model, ...o }) + "\n\n");
        ev({ choices: [{ index: 0, delta: { role: "assistant", content: "" }, finish_reason: null }] });
        ev({ choices: [{ index: 0, delta: { reasoning: "(reasoning)" }, finish_reason: null }] });
        ev({ choices: [{ index: 0, delta: { content: text.slice(0, 20) }, finish_reason: null }] });
        ev({ choices: [{ index: 0, delta: { content: text.slice(20) }, finish_reason: null }] });
        ev({ choices: [{ index: 0, delta: {}, finish_reason: "stop" }] });
        ev({ choices: [], usage });
        res.end("data: [DONE]\n\n");
        return;
      }
      fail(404, "unknown path");
    });
  });
  await new Promise((r) => server.listen(port, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const get = async (p) => (await fetch(base + p)).json();
  return {
    url: base, key,
    stats: () => get("/__stats"),
    control: (patch) => fetch(base + "/__control", { method: "POST", body: JSON.stringify(patch) }),
    stop: () => new Promise((r) => server.close(r)),
  };
}
