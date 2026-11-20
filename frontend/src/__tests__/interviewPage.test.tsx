import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InterviewState } from "../types";
import states from "./fixtures/interview-states.json";     // real API states: backend/tests/test_report_fixture.py

const S = states as unknown as Record<"awaiting" | "failed" | "next", InterviewState>;
const clone = (s: InterviewState) => structuredClone(s);
const interview = vi.fn<(id: number) => Promise<InterviewState>>();
const answer = vi.fn<(id: number, turn: number, text: string, source: string) => Promise<InterviewState>>();
const action = vi.fn<(id: number, kind: string, turn: number) => Promise<InterviewState>>();

vi.mock("../api", async (importOriginal) => {
  const real = await importOriginal<typeof import("../api")>();
  return { ...real, api: { ...real.api,
    interview: (id: number) => interview(id),
    answer: (...a: [number, number, string, string]) => answer(...a),
    action: (...a: [number, string, number]) => action(...a),
    health: async () => ({ ai: { mode: "local" } }),
    warm: async () => ({}),
  } };
});
const { default: Interview } = await import("../pages/Interview");
const { ApiError } = await import("../api");

const iid = S.awaiting.id;
beforeEach(() => { interview.mockReset(); answer.mockReset(); action.mockReset(); localStorage.clear(); });

describe("Interview page (real interview states from the backend)", () => {
  it("submits the typed answer for the current turn exactly once, even on a double click", async () => {
    interview.mockResolvedValue(clone(S.awaiting));
    let resolve!: (s: InterviewState) => void;
    answer.mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<Interview id={iid} />);
    const box = await screen.findByLabelText("Your answer");
    fireEvent.change(box, { target: { value: "  Reruns give the same final state.  " } });
    const submit = screen.getByRole("button", { name: /Submit Answer/ });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(answer).toHaveBeenCalledTimes(1);
    expect(answer).toHaveBeenCalledWith(iid, S.awaiting.current_turn_id, "Reruns give the same final state.", "typed");
    await act(async () => { resolve({ ...clone(S.awaiting), phase: "evaluating" }); });
    expect(await screen.findByText(/Evaluating your answer with the local model/)).toBeInTheDocument();
  });

  it("keeps an unsent draft on this computer and restores it after a reload", async () => {
    interview.mockResolvedValue(clone(S.awaiting));
    const first = render(<Interview id={iid} />);
    fireEvent.change(await screen.findByLabelText("Your answer"), { target: { value: "half an answer" } });
    first.unmount();
    render(<Interview id={iid} />);
    const box = await screen.findByLabelText("Your answer");
    await waitFor(() => expect(box).toHaveValue("half an answer"));       // restored by an effect right after the first render
  });

  it("after a failed evaluation shows the saved answer and the error, and Retry moves on", async () => {
    interview.mockResolvedValue(clone(S.failed));
    action.mockResolvedValue(clone(S.next));
    render(<Interview id={iid} />);
    expect(await screen.findByText(/The answer was saved, but it couldn’t be evaluated/)).toBeInTheDocument();
    expect(screen.getByText(S.failed.error as string)).toBeInTheDocument();
    expect(screen.getByText(S.failed.current!.turn!.answer_text as string)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry evaluation" }));
    expect(action).toHaveBeenCalledWith(iid, "retry", S.failed.current_turn_id);
    expect(await screen.findByText(S.next.current!.turn!.question_text)).toBeInTheDocument();
  });

  it("when the server says the page was stale (409), it shows why and reloads the real state", async () => {
    interview.mockResolvedValueOnce(clone(S.awaiting)).mockResolvedValue(clone(S.next));
    answer.mockRejectedValue(new ApiError("stale_turn", "That question is no longer current. The page was out of date.", 409));
    render(<Interview id={iid} />);
    fireEvent.change(await screen.findByLabelText("Your answer"), { target: { value: "my answer" } });
    fireEvent.click(screen.getByRole("button", { name: /Submit Answer/ }));
    expect(await screen.findByText(/no longer current/)).toBeInTheDocument();
    expect(await screen.findByText(S.next.current!.turn!.question_text)).toBeInTheDocument();
    expect(interview).toHaveBeenCalledTimes(2);
  });
});
