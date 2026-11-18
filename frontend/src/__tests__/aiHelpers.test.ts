import { describe, expect, it } from "vitest";
import { checkKeyDraft, cleanKeyDraft, estimateInterviewCost, fmtRate, fmtUsd, modelOptions, normaliseModel, priceFor, priceKey, RECOMMENDED, selectedOption, SUPPORTED_MODELS } from "../aiHelpers";
import type { AIConfig, ModelPrice } from "../types";
import { ago, isActive } from "../components/ActiveInterviews";
import { chipsFor, clip, questionNote } from "../scorecardHelpers";

const P = (i: number, o: number, oi: number | null = null, oo: number | null = null): ModelPrice => ({ input_per_m: i, output_per_m: o, offpeak_input_per_m: oi, offpeak_output_per_m: oo });
const CFG: AIConfig = {
  mode: "cloud", cloud_consent_at: "x", grader_model: "openai/gpt-oss-120b", fallback_model: "openai/gpt-oss-20b", use_fallback: true, conversation_model: "openai/gpt-oss-20b", fallback_to_local: false,
  enforce_budget: true, daily_budget_usd: 1, total_budget_usd: null,
  prices: { "openai/gpt-oss-120b": P(0.15, 0.6), "openai/gpt-oss-20b": P(0.075, 0.3) },
};

describe("money formatting", () => {
  it("never shows a real cloud cost as $0.00", () => {
    expect(fmtUsd(0.000405)).toBe("$0.0004");
    expect(fmtUsd(0.0123)).toBe("$0.012");
    expect(fmtUsd(1.5)).toBe("$1.50");
    expect(fmtUsd(0)).toBe("$0");
    expect(fmtUsd(null)).toBe("–");
  });
});

describe("model names and prices", () => {
  it("treats the short and the full spelling as the same model, ignoring case", () => {
    expect(normaliseModel("GPT-OSS-120b")).toBe("openai/gpt-oss-120b");
    expect(normaliseModel(" openai/GPT-OSS-20B ")).toBe("openai/gpt-oss-20b");
    expect(normaliseModel("llama-3.3-70b-versatile")).toBe("llama-3.3-70b-versatile");
    expect(priceFor("gpt-oss-120b", CFG.prices)).toBe(CFG.prices["openai/gpt-oss-120b"]);
    expect(priceFor("kimi-k3", CFG.prices)).toBeNull();
  });
  it("no longer knows the old cloud suffixes", () => {
    expect(normaliseModel("gpt-oss-120b-cloud")).not.toBe("openai/gpt-oss-120b");
  });
});

describe("interview cost estimate", () => {
  it("is a small, honest upper bound for the default models", () => {
    const one = estimateInterviewCost(CFG, 1, 0)!;
    expect(one).toBeGreaterThan(0.0003);
    expect(one).toBeLessThan(0.002);                                    // about a tenth of a cent per question
    const ten = estimateInterviewCost(CFG, 10, 2)!;
    expect(ten).toBeGreaterThan(one * 10);                              // follow-ups are counted
    expect(ten).toBeLessThan(0.1);                                      // a 10-question interview costs well under ten cents
  });
  it("uses the plain rate and prices the cheaper model lower", () => {
    const small = { ...CFG, grader_model: "openai/gpt-oss-20b" };
    expect(estimateInterviewCost(small, 5, 1)!).toBeLessThan(estimateInterviewCost(CFG, 5, 1)!);
  });
  it("says unknown, not free, when a model has no price", () => {
    expect(estimateInterviewCost({ ...CFG, grader_model: "kimi-k3" }, 3, 1)).toBeNull();
  });
  it("costs nothing for an interview with no questions", () => {
    expect(estimateInterviewCost(CFG, 0, 2)).toBe(0);
  });
});

describe("API key draft", () => {
  it("drops an accidental Bearer prefix and surrounding spaces", () => {
    expect(cleanKeyDraft("  Bearer abcdefgh12345  ")).toBe("abcdefgh12345");
    expect(cleanKeyDraft("bearer   k")).toBe("k");
    expect(cleanKeyDraft("abcdefgh")).toBe("abcdefgh");
  });
  it("mirrors the server rules (8+ characters, no inner spaces)", () => {
    expect(checkKeyDraft("").state).toBe("empty");
    expect(checkKeyDraft("   ").state).toBe("empty");
    expect(checkKeyDraft("abc").state).toBe("short");
    expect(checkKeyDraft("abcdefg").state).toBe("short");
    expect(checkKeyDraft("abcdefgh").state).toBe("ok");
    expect(checkKeyDraft("abcd efgh1234").state).toBe("spaces");
    expect(checkKeyDraft("Bearer abcdefgh1234").state).toBe("ok");
    expect(checkKeyDraft("abcdefgh1234").text).toContain("12 characters");
    expect(checkKeyDraft("").text).toContain("Groq");
  });
  it("never echoes the key itself in its message", () => {
    for (const k of ["secret-abcdef-123", "abc def", "x"]) expect(checkKeyDraft(k).text).not.toContain(k);
  });
});

describe("model pickers", () => {
  it("offers exactly the two supported models in every dropdown, marking each role's own recommendation", () => {
    expect(SUPPORTED_MODELS).toEqual(["openai/gpt-oss-120b", "openai/gpt-oss-20b"]);
    expect(RECOMMENDED).toEqual({ grader: "openai/gpt-oss-120b", fallback: "openai/gpt-oss-20b", conversation: "openai/gpt-oss-20b" });
    expect(modelOptions("grader").map((o) => o.label)).toEqual(["openai/gpt-oss-120b (recommended)", "openai/gpt-oss-20b"]);
    expect(modelOptions("fallback").map((o) => o.label)).toEqual(["openai/gpt-oss-120b", "openai/gpt-oss-20b (recommended)"]);
    expect(modelOptions("conversation").map((o) => o.label)).toEqual(["openai/gpt-oss-120b", "openai/gpt-oss-20b (recommended)"]);
    for (const role of ["grader", "fallback", "conversation"] as const) expect(modelOptions(role).map((o) => o.value)).toEqual([...SUPPORTED_MODELS]);
  });
  it("matches the short spelling to the same entry and returns null for any other name", () => {
    const o = modelOptions("grader");
    expect(selectedOption("gpt-oss-120b", o)).toBe("openai/gpt-oss-120b");
    expect(selectedOption("  OPENAI/GPT-OSS-20B ", o)).toBe("openai/gpt-oss-20b");
    expect(selectedOption("kimi-k3", o)).toBeNull();
    expect(selectedOption("", o)).toBeNull();
  });
  it("shows rates with a steady three decimals", () => {
    expect(fmtRate(0.15)).toBe("$0.150");
    expect(fmtRate(0.6)).toBe("$0.600");
    expect(fmtRate(1.2)).toBe("$1.200");
  });
});

describe("price list lookups", () => {
  const prices = { "openai/gpt-oss-20b": P(0.075, 0.3), "openai/gpt-oss-120b": P(0.15, 0.6) };
  it("finds an exact entry (either spelling) and never guesses a family", () => {
    expect(priceKey("gpt-oss-120b", prices)).toBe("openai/gpt-oss-120b");
    expect(priceFor("openai/gpt-oss-20b", prices)?.input_per_m).toBe(0.075);
    expect(priceFor("gpt-oss", prices)).toBeNull();
    expect(priceFor("llama-3.3-70b-versatile", prices)).toBeNull();
    expect(priceFor("", prices)).toBeNull();
  });
});

describe("active interview bar helpers", () => {
  const now = Date.parse("2026-11-01T12:00:00Z");
  it("describes how long ago something happened", () => {
    expect(ago("2026-11-01T11:59:40Z", now)).toBe("just now");
    expect(ago("2026-11-01T11:48:00Z", now)).toBe("12 min ago");
    expect(ago("2026-11-01T09:00:00Z", now)).toBe("3 h ago");
    expect(ago("2026-10-30T12:00:00Z", now)).toBe("2 days ago");
    expect(ago("2026-10-31T12:00:00Z", now)).toBe("1 day ago");
    expect(ago(null, now)).toBe("earlier");
    expect(ago("not a date", now)).toBe("earlier");
  });
  it("counts running and paused interviews as active, nothing else", () => {
    const row = (status: string) => ({ status }) as never;
    expect(["in_progress", "paused"].map((s) => isActive(row(s)))).toEqual([true, true]);
    expect(["completed", "ended"].map((s) => isActive(row(s)))).toEqual([false, false]);
  });
});

describe("scorecard helpers", () => {
  const turn = (kind: string, status: string, score: number | null) => ({ kind, status, score }) as never;
  it("labels the answer and each follow-up with its own score", () => {
    const chips = chipsFor({ turns: [turn("main", "evaluated", 8), turn("followup", "evaluated", 6.5), turn("followup", "evaluated", 9)] });
    expect(chips).toEqual([{ label: "Answer", score: 8, note: null }, { label: "Follow-up 1", score: 6.5, note: null }, { label: "Follow-up 2", score: 9, note: null }]);
  });
  it("says why a turn has no score instead of showing a zero", () => {
    expect(chipsFor({ turns: [turn("main", "evaluated", 7), turn("followup", "skipped", null)] })[1]).toEqual({ label: "Follow-up 1", score: null, note: "skipped" });
    expect(chipsFor({ turns: [turn("main", "submitted", null)] })[0].note).toBe("not scored");
    expect(chipsFor({ turns: [turn("main", "evaluated", 5), turn("followup", "asked", null)] })[1].note).toBe("not answered");
    expect(chipsFor({ turns: [] })).toEqual([]);
  });
  it("describes a question without a score", () => {
    expect(questionNote({ status: "skipped", score: null })).toBe("Skipped");
    expect(questionNote({ status: "unanswered", score: null })).toBe("Not reached");
    expect(questionNote({ status: "answered", score: null })).toBe("Not scored");
    expect(questionNote({ status: "answered", score: 7 })).toBeNull();
  });
  it("shortens long questions on a single line", () => {
    expect(clip("a  b\n c", 50)).toBe("a b c");
    expect(clip("x".repeat(200), 20)).toHaveLength(20);
    expect(clip("x".repeat(200), 20).endsWith("…")).toBe(true);
  });
});
