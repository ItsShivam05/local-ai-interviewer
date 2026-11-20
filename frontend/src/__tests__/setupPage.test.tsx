import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearApiCache } from "../api";
import Setup from "../pages/Setup";
import api from "./fixtures/setup-api.json";          // real GET responses from the backend: backend/tests/test_report_fixture.py

type Json = Record<string, unknown>;
const posts: { path: string; body: Json }[] = [];

/** The real API client talks to a fake server that answers with what the backend really returned. */
function serve(gets: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (method === "POST") {
      posts.push({ path, body: JSON.parse(String(init?.body ?? "{}")) });
      return path === "/api/interviews" ? reply(201, api.created) : reply(200, {});
    }
    return path in gets ? reply(200, structuredClone(gets[path])) : reply(404, { error: { code: "not_found", message: `no fixture for ${path}` } });
  }));
}

const startButton = () => screen.findByRole("button", { name: /Start Interview/ });

beforeEach(() => { posts.length = 0; clearApiCache(); localStorage.clear(); sessionStorage.clear(); window.location.hash = "#/setup"; });
afterEach(() => vi.unstubAllGlobals());

describe("Interview setup page (real API responses)", () => {
  it("starts an interview with the chosen settings and opens it", async () => {
    serve(api.idle);
    render(<Setup />);
    const start = await startButton();
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    await waitFor(() => expect(posts.some((p) => p.path === "/api/interviews")).toBe(true));
    const sent = posts.find((p) => p.path === "/api/interviews")!.body as { set_id: number; config: Json };
    expect(sent.set_id).toBe(api.idle["/api/sets"][0].id);
    expect(sent.config).toMatchObject({ mode: "fixed", include_bank: true, question_ids: null });
    expect(sent.config).not.toHaveProperty("strategy");                       // a fixed interview sends none of the adaptive settings
    await waitFor(() => expect(window.location.hash).toBe(`#/interview/${api.created.id}`));
  });

  it("a preset fills the settings that are sent", async () => {
    serve(api.idle);
    render(<Setup />);
    await waitFor(async () => expect(await startButton()).toBeEnabled());
    const full = within(screen.getByRole("radiogroup", { name: "Interview preset" })).getByRole("radio", { name: /Full mock/ });
    await waitFor(() => expect(full).toBeEnabled());                         // presets wait for the question list
    fireEvent.click(full);
    expect(full).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByText(/Full mock applied/)).toBeInTheDocument();
    fireEvent.click(await startButton());
    await waitFor(() => expect(posts.some((p) => p.path === "/api/interviews")).toBe(true));
    const { config } = posts.find((p) => p.path === "/api/interviews")!.body as { config: Json };
    expect(config).toMatchObject({ mode: "adaptive", strategy: "progressive", time_limit_minutes: 45, max_questions: 8, max_followups: 2 });
  });

  it("refuses to start a second interview while one is still running", async () => {
    serve({ ...api.idle, ...api.active });
    render(<Setup />);
    const start = await startButton();
    expect((await screen.findAllByText(new RegExp(api.active["/api/interviews"][0].title as string))).length).toBeGreaterThan(0);   // the running one is shown
    await screen.findByText(/^3 · In order$/);                                // questions loaded: with no interview running it would be enabled now
    expect(start).toBeDisabled();
    fireEvent.click(start);
    expect(posts.filter((p) => p.path === "/api/interviews")).toHaveLength(0);
  });
});
