import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Report } from "../types";
import fixture from "./fixtures/report.json";      // made by the backend itself: backend/tests/test_report_fixture.py

const report = vi.fn<(id: number) => Promise<Report>>();
const regenerate = vi.fn<(id: number) => Promise<Report>>();
vi.mock("../api", async (importOriginal) => {
  const real = await importOriginal<typeof import("../api")>();
  return { ...real, api: { ...real.api,
    report: (id: number) => report(id),
    regenerateReport: (id: number) => regenerate(id),
    exportReportUrl: (id: number, fmt: string, redact = false) => `/api/interviews/${id}/report/export?format=${fmt}${redact ? "&redact=true" : ""}`,
    downloadReportPdf: vi.fn(async () => "report.pdf"),
  } };
});
const { default: ReportPage } = await import("../pages/Report");

const base = fixture as unknown as Report;
const show = async (r: Report = base) => {
  report.mockResolvedValue(structuredClone(r));
  render(<ReportPage id={base.interview.id} />);
  return screen.findByRole("heading", { name: "Interview Report" });
};

beforeEach(() => { report.mockReset(); regenerate.mockReset(); localStorage.clear(); sessionStorage.clear(); });   // the chosen tab is remembered per report

describe("Report page (real report shape from the backend)", () => {
  it("shows the app-computed result and never counts a skipped question as zero", async () => {
    await show();
    expect(screen.getByText("Fixture interview")).toBeInTheDocument();
    const hero = screen.getByText(/1 of 2 questions scored · 1 skipped/).closest(".txt") as HTMLElement;
    expect(within(hero).getByText(base.summary.verdict as string)).toBeInTheDocument();
    const stats = screen.getByText("Average Score").parentElement as HTMLElement;
    expect(within(stats).getByText(String(base.summary.average_score))).toBeInTheDocument();     // 8, not (8 + 0) / 2
  });

  it("offers the full exports and a share-safe copy without answers", async () => {
    await show();
    const id = base.interview.id;
    expect(screen.getByRole("link", { name: /Export as JSON/ })).toHaveAttribute("href", `/api/interviews/${id}/report/export?format=json`);
    expect(screen.getByRole("link", { name: /^Markdown$/ })).toHaveAttribute("href", `/api/interviews/${id}/report/export?format=md`);
    fireEvent.click(screen.getByRole("button", { name: /Share-safe export/ }));
    const md = await screen.findByRole("menuitem", { name: /Markdown/ });
    expect(md).toHaveAttribute("href", `/api/interviews/${id}/report/export?format=md&redact=true`);
  });

  it("the Questions tab shows each question with its score or why it has none", async () => {
    await show();
    fireEvent.click(screen.getByRole("tab", { name: /Questions/ }));
    const answered = base.questions.find((q) => q.status === "answered")!;
    const skipped = base.questions.find((q) => q.status === "skipped")!;
    const panel = screen.getByRole("tabpanel");
    const row = (text: string) => within(panel).getAllByText(text).map((e) => e.closest("summary")).find(Boolean) as HTMLElement;
    expect(within(row(answered.text)).getByText(String(answered.score))).toBeInTheDocument();
    expect(within(row(skipped.text)).getByText("skipped")).toBeInTheDocument();
  });

  it("while the written summary is pending it says so, and offers Regenerate once it is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const pending = { ...structuredClone(base), narrative_status: "pending" as const };
      report.mockResolvedValueOnce(pending).mockResolvedValue(structuredClone(base));
      render(<ReportPage id={base.interview.id} />);
      expect(await screen.findByText(/Writing summary/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
      await act(async () => { await vi.advanceTimersByTimeAsync(2600); });      // the page polls every 2.5 s while pending
      expect(await screen.findByRole("button", { name: "Regenerate" })).toBeInTheDocument();
      expect(report.mock.calls.length).toBeGreaterThanOrEqual(2);
    } finally { vi.useRealTimers(); }
  });

  it("reports a failed load instead of spinning forever", async () => {
    report.mockRejectedValue(new Error("Report not found."));
    render(<ReportPage id={999} />);
    expect(await screen.findByText(/Report not found/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to reports/ })).toBeInTheDocument();
  });
});
