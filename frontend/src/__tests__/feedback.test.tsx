import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Feedback from "../components/Feedback";
import type { Evaluation } from "../types";

const base: Evaluation = {
  correct_points: ["Said it is relational"], missing_concepts: [], misconceptions: [],
  dimension_scores: { correctness: 6, completeness: 5, depth: 3, practical_application: 2, clarity: 5, production_awareness: 0 },
  production_relevant: false, suggested_improvements: [], ideal_answer: "", confidence: "high", uncertainty_note: "",
  needs_followup: false, followup_reason: "", score: 4.9, verdict: "Fair", followup_asked: false,
};

describe("Feedback", () => {
  it("tells a voice answerer what the grader actually read", () => {
    render(<Feedback ev={{ ...base, interpreted_answer: "MySQL is a relational database with DML and DDL." }} score={4.9} />);
    const note = screen.getByTestId("graded-as");
    expect(note).toHaveTextContent("You answered by voice");
    expect(note).toHaveTextContent("MySQL is a relational database with DML and DDL.");
    expect(note).toHaveTextContent("not held against you");
  });
  it("shows nothing extra for typed answers", () => {
    render(<Feedback ev={base} score={4.9} />);
    expect(screen.queryByTestId("graded-as")).toBeNull();
  });
  it("says which model graded the answer and where it ran", () => {
    const { rerender } = render(<Feedback ev={{ ...base, graded_by: { provider: "cloud", model: "openai/gpt-oss-120b", fell_back_from: null } }} score={4.9} />);
    expect(screen.getByTestId("graded-by")).toHaveTextContent("Graded by openai/gpt-oss-120b (Groq cloud)");
    expect(screen.getByTestId("graded-by")).not.toHaveTextContent("unavailable");
    rerender(<Feedback ev={{ ...base, graded_by: { provider: "cloud", model: "openai/gpt-oss-20b", fell_back_from: "openai/gpt-oss-120b" } }} score={4.9} />);
    expect(screen.getByTestId("graded-by")).toHaveTextContent("openai/gpt-oss-120b was unavailable, so the fallback model graded this");
    rerender(<Feedback ev={{ ...base, graded_by: { provider: "local", model: "qwen3.5:4b", fell_back_from: "openai/gpt-oss-120b", reason: "Groq had a problem" } }} score={4.9} />);
    expect(screen.getByTestId("graded-by")).toHaveTextContent("Graded on this computer by qwen3.5:4b");
    expect(screen.getByTestId("graded-by")).toHaveTextContent("the cloud was unavailable (Groq had a problem)");
  });
  it("shows nothing about the engine for old evaluations that have no record of it", () => {
    render(<Feedback ev={base} score={4.9} />);
    expect(screen.queryByTestId("graded-by")).toBeNull();
  });
  it("explains why a basic question weighs depth less", () => {
    render(<Feedback ev={{ ...base, question_level: "basic" }} score={4.9} />);
    expect(screen.getByText(/depth and real-world examples count less/)).toBeInTheDocument();
  });
  it("shows the classification, profile, evidence and how it was graded", () => {
    const ev: Evaluation = { ...base, classification: "correct_incomplete", profile_label: "SQL",
      dimension_scores: { ...base.dimension_scores, tradeoffs: 7, edge_cases: null },
      evidence: [{ kind: "correct", point: "joins", quote: "joins combine rows", verified: true }, { kind: "incorrect", point: "nulls", quote: "nulls equal", verified: false }],
      unverified_misconceptions: ["Confuses UNION with JOIN"], adjustments: ["Capped at 6 because a key point was missing."], consistency_flags: [{ code: "x", message: "Score and verdict were aligned." }],
      weights: { correctness: 0.3, edge_cases: 0.1 }, provenance: { prompt_version: "eval-2.0", rubric: "sql-v2", graded_by: { provider: "local", model: "qwen3.5:4b" } } };
    render(<Feedback ev={ev} score={6} />);
    expect(screen.getByTestId("fb-class")).toHaveTextContent("Correct but incomplete");
    expect(screen.getByText("Graded as: SQL")).toBeInTheDocument();
    expect(screen.getByText(/Trade-off analysis: 7\/10/)).toBeInTheDocument();
    expect(screen.queryByText(/Edge-case awareness: /)).toBeNull();
    expect(screen.getByText("Verified in your answer")).toBeInTheDocument();
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByTestId("fb-unverified")).toHaveTextContent("Possible errors (not found in your answer, not counted as mistakes)");
    expect(screen.getByTestId("fb-unverified")).toHaveTextContent("Confuses UNION with JOIN");
    const how = screen.getByTestId("how-graded");
    expect(how).toHaveTextContent("Capped at 6"); expect(how).toHaveTextContent("Score and verdict were aligned.");
    expect(how).toHaveTextContent("Correctness 30%"); expect(how).toHaveTextContent("eval-2.0"); expect(how).toHaveTextContent("sql-v2"); expect(how).toHaveTextContent("qwen3.5:4b");
  });
  it("adds nothing for evaluations without the new fields", () => {
    render(<Feedback ev={base} score={4.9} />);
    for (const id of ["fb-class", "fb-unverified", "fb-evidence", "how-graded", "fb-tags"]) expect(screen.queryByTestId(id)).toBeNull();
  });

  it("labels a resume question's reference as an outline and shows figures nobody mentioned", () => {
    const flag = { code: "reference_figures_unverified", message: "The suggested answer mentions figures that are not in your answer or your resume (200, 600). They are illustrations, not facts about your work." };
    const { rerender } = render(<Feedback ev={{ ...base, ideal_answer: "Latency is ~200-600 ms.", consistency_flags: [flag] }} score={7} resume />);
    fireEvent.click(screen.getByRole("tab", { name: "Ideal Answer" }));
    expect(screen.getByText("What a strong answer covers")).toBeInTheDocument();
    expect(screen.queryByText("Suggested answer (written by the AI)")).toBeNull();
    expect(screen.getByTestId("fb-unverified-figures")).toHaveTextContent("200, 600");
    rerender(<Feedback ev={{ ...base, ideal_answer: "A primary key uniquely identifies a row." }} score={7} />);
    expect(screen.getByText("Suggested answer (written by the AI)")).toBeInTheDocument();
    expect(screen.queryByTestId("fb-unverified-figures")).toBeNull();
  });

  it("warns that the suggested answer is unchecked when the question has no expected answer (review round 3)", () => {
    const ev = { ...base, ideal_answer: "Any tuple can be a dictionary key." };      // the kind of false statement the review found
    const { rerender } = render(<Feedback ev={ev} score={7} hasRubric={false} />);
    fireEvent.click(screen.getByRole("tab", { name: "Ideal Answer" }));
    expect(screen.getByTestId("fb-unchecked-answer")).toHaveTextContent("Not checked");
    rerender(<Feedback ev={ev} score={7} hasRubric />);
    expect(screen.queryByTestId("fb-unchecked-answer")).toBeNull();
    rerender(<Feedback ev={ev} score={7} hasRubric={false} resume />);
    expect(screen.queryByTestId("fb-unchecked-answer")).toBeNull();           // resume questions already say it is an outline
  });
});
