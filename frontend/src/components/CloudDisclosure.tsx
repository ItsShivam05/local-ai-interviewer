import type { AIProvider } from "../types";

/** A link that always opens outside the app; the address itself comes from the API, never from this source. */
export function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
}

/** What the cloud provider does with the text (sentence from the API) plus a link to its data policy. */
export function RetentionNote({ provider }: { provider: AIProvider }) {
  return (
    <>
      <p className="muted small" data-testid="retention" style={{ margin: "10px 0 0" }}>{provider.retention} <ExtLink href={provider.data_url}>Read {provider.name}’s data policy</ExtLink>.</p>
      {provider.custom_host && (
        <p className="small" data-testid="custom-endpoint" style={{ margin: "8px 0 0", color: "var(--warn-ink)" }}>
          This installation is set up (GROQ_BASE_URL) to send cloud requests to <b>{provider.custom_host}</b>, not to {provider.name}. The policy above does not describe that server.
        </p>
      )}
    </>
  );
}
