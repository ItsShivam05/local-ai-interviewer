import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExtLink, RetentionNote } from "../components/CloudDisclosure";

const provider = { name: "Groq", keys_url: "/fake/keys", data_url: "/fake/policy", retention: "Groq says it does not keep your text by default, but may log requests for up to 30 days." };

describe("cloud disclosure", () => {
  it("says so when cloud requests go to a custom server instead of the named provider", () => {
    const { rerender } = render(<RetentionNote provider={provider} />);
    expect(screen.queryByTestId("custom-endpoint")).toBeNull();
    rerender(<RetentionNote provider={{ ...provider, custom_host: "llm.example.test" }} />);
    expect(screen.getByTestId("custom-endpoint")).toHaveTextContent("llm.example.test, not to Groq");
  });

  it("shows the retention sentence from the API and links to the data policy, opening outside the app", () => {
    render(<RetentionNote provider={provider} />);
    expect(screen.getByTestId("retention")).toHaveTextContent("up to 30 days");
    const a = screen.getByRole("link", { name: /Groq’s data policy/ });
    expect(a).toHaveAttribute("href", provider.data_url);
    expect(a).toHaveAttribute("target", "_blank");
    expect(a.getAttribute("rel")).toContain("noopener");
  });
  it("ExtLink never leaks the opener", () => {
    render(<ExtLink href={provider.keys_url}>keys</ExtLink>);
    expect(screen.getByRole("link", { name: "keys" })).toHaveAttribute("rel", "noreferrer noopener");
  });
});
