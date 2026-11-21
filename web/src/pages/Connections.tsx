import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Plug, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { API_URL, api, type MyKey } from "../api";
import { Button, cx, Empty, ErrorNote, Module, SkeletonRows, Table, td, th } from "../components/ui";
import { when } from "../format";
import { usePack } from "../packContext";

const SCOPE_TEXT: Array<{ scope: string; text: string }> = [
  { scope: "read", text: "Read cases, documents and metrics" },
  { scope: "submit", text: "Submit documents" },
  { scope: "propose", text: "Suggest a decision (changes nothing)" },
  { scope: "post", text: "Post approved cases (still needs your grant for each one)" },
];

function KeysTable({ rows, onDisable, busy }: { rows: MyKey[]; onDisable: (id: string) => void; busy: boolean }) {
  return (
    <Table label="API keys">
      <thead>
        <tr>
          <th className={th}>Name</th>
          <th className={th}>Key</th>
          <th className={th}>Can</th>
          <th className={th}>Last used</th>
          <th className={th}>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.id} className={cx(p.disabled && "opacity-50")}>
            <td className={td}>
              {p.name} {p.disabled && <span className="text-xs text-ink-2">disabled</span>}
            </td>
            <td className={`${td} font-mono text-[13px] text-ink-2`}>{p.key_prefix}…</td>
            <td className={`${td} font-mono text-xs text-ink-2`}>{p.scopes.join(", ")}</td>
            <td className={`${td} text-ink-2`}>{p.last_used_at ? when(p.last_used_at) : "never"}</td>
            <td className={td}>
              {!p.disabled && (
                <Button variant="danger" disabled={busy} onClick={() => onDisable(p.id)}>
                  Disable
                </Button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function Connections() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  const account = Boolean(me.data?.account);
  const admin = Boolean(me.data?.scopes.includes("admin"));
  const { packs } = usePack();

  // A key can do no more than the person who makes it, and never decide anything.
  const mine = new Set(me.data?.scopes ?? []);
  const offered = SCOPE_TEXT.filter(({ scope }) => (scope === "propose" ? mine.has("read") : mine.has(scope) || !account));

  const keys = useQuery({
    queryKey: ["keys", account],
    queryFn: () => (account ? api.myKeys() : api.principals()),
    enabled: me.isSuccess,
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.users, enabled: account && admin });
  const [label, setLabel] = useState("");
  const [scopes, setScopes] = useState<string[]>(["read", "propose"]);
  const [chosenPacks, setChosenPacks] = useState<string[] | null>(null);
  const allowedPacks = chosenPacks ?? packs.map((p) => p.id);
  const [issued, setIssued] = useState<{ name: string; key: string } | null>(null);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["keys"] });
  const create = useMutation({
    mutationFn: () =>
      account
        ? api.createMyKey({ label: label.trim(), scopes, packs: allowedPacks })
        : api.createPrincipal({ name: label.trim(), kind: "agent", scopes, packs: allowedPacks }),
    onSuccess: (row) => {
      setIssued({ name: row.name, key: row.key });
      setLabel("");
      refresh();
    },
  });
  const disable = useMutation({
    mutationFn: (id: string) => (account ? api.disableMyKey(id) : api.disablePrincipal(id)),
    onSuccess: () => {
      toast.success("Key disabled. It stops working immediately.");
      refresh();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "That did not work"),
  });
  const toggleUser = useMutation({
    mutationFn: (u: { id: string; disabled: boolean }) => api.setUserDisabled(u.id, u.disabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
    onError: (e) => toast.error(e instanceof Error ? e.message : "That did not work"),
  });

  function toggle(scope: string) {
    setScopes((s) => (s.includes(scope) ? s.filter((x) => x !== scope) : [...s, scope]));
  }

  if (me.isSuccess && !account && !admin) {
    return (
      <Empty title="Sign in with an account">API keys belong to a person. Sign out, then create an account or sign in with your email.</Empty>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="label-mono">API keys</p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight">Let an agent work for you</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Generate a key when an agent or integration needs to read cases and suggest decisions on your behalf. A key
          can do no more than you can, can never approve or reject (you decide), and stops working if your account is
          disabled. Posting an approved case also needs a grant you issue for that one case.
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-12">
        <Module icon={KeyRound} title="Generate a key" className="lg:col-span-5" bodyClassName="space-y-4 p-4">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label className="block text-sm font-semibold" htmlFor="key-label">
              What is it for?
              <input
                id="key-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="claude-desktop"
                className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"
              />
            </label>
            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold">What it may do</legend>
              {offered.map(({ scope, text }) => (
                <label key={scope} className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={scopes.includes(scope)} onChange={() => toggle(scope)} className="mt-1 accent-[hsl(var(--accent))]" />
                  <span>
                    <span className="font-mono text-[13px]">{scope}</span> <span className="text-ink-2">{text}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {packs.length > 1 && (
              <fieldset className="space-y-2">
                <legend className="text-sm font-semibold">Which workflows</legend>
                {packs.map((p) => (
                  <label key={p.id} className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={allowedPacks.includes(p.id)}
                      onChange={() => setChosenPacks(allowedPacks.includes(p.id) ? allowedPacks.filter((x) => x !== p.id) : [...allowedPacks, p.id])}
                      className="mt-1 accent-[hsl(var(--accent))]"
                    />
                    <span>{p.name}</span>
                  </label>
                ))}
              </fieldset>
            )}
            <ErrorNote error={create.error} />
            <Button type="submit" disabled={label.trim().length < 2 || scopes.length === 0 || allowedPacks.length === 0 || create.isPending}>
              Generate key
            </Button>
          </form>

          {issued && (
            <div role="status" className="space-y-2 rounded-xl border border-accent/60 bg-accent-tint p-3">
              <p className="text-sm font-semibold">Key for {issued.name}. Copy it now: it is not shown again.</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded-lg bg-fill px-2 py-1.5 font-mono text-[13px]">{issued.key}</code>
                <Button
                  variant="secondary"
                  aria-label="Copy the key"
                  onClick={() => {
                    void navigator.clipboard?.writeText(issued.key);
                    toast.success("Copied");
                  }}
                >
                  <Copy aria-hidden className="h-4 w-4" />
                </Button>
              </div>
              <Button variant="ghost" onClick={() => setIssued(null)}>
                I have saved it
              </Button>
            </div>
          )}
        </Module>

        <Module icon={Plug} title={account ? "Your keys" : "Keys"} count={keys.data?.length} className="lg:col-span-7">
          <ErrorNote error={keys.error} />
          {keys.isLoading && <SkeletonRows rows={4} cols={4} />}
          {keys.data && keys.data.length === 0 && <Empty title="No keys yet">Generate one to let an agent read cases and suggest decisions.</Empty>}
          {keys.data && keys.data.length > 0 && <KeysTable rows={keys.data as MyKey[]} onDisable={(id) => disable.mutate(id)} busy={disable.isPending} />}
          <p className="border-t border-line px-4 py-3 text-xs text-ink-2">
            Agents send the key as <code className="font-mono">Authorization: Bearer &lt;key&gt;</code> to{" "}
            <code className="font-mono">{API_URL}/mcp</code> (MCP) or <code className="font-mono">{API_URL}</code> (API).
          </p>
        </Module>

        {account && admin && (
          <Module icon={Users} title="People" count={users.data?.length} className="lg:col-span-12">
            <ErrorNote error={users.error} />
            {users.isLoading && <SkeletonRows rows={3} cols={4} />}
            {users.data && (
              <Table label="People with accounts">
                <thead>
                  <tr>
                    <th className={th}>Name</th>
                    <th className={th}>Email</th>
                    <th className={th}>Role</th>
                    <th className={th}>Last sign-in</th>
                    <th className={th}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.data.map((u) => (
                    <tr key={u.id} className={cx(u.disabled && "opacity-50")}>
                      <td className={td}>{u.name}</td>
                      <td className={`${td} font-mono text-[13px] text-ink-2`}>{u.email}</td>
                      <td className={`${td} text-ink-2`}>{u.is_admin ? "Administrator" : "Reviewer"}</td>
                      <td className={`${td} text-ink-2`}>{u.last_login_at ? when(u.last_login_at) : "never"}</td>
                      <td className={td}>
                        {u.email !== me.data?.email && (
                          <Button variant={u.disabled ? "secondary" : "danger"} disabled={toggleUser.isPending} onClick={() => toggleUser.mutate({ id: u.id, disabled: !u.disabled })}>
                            {u.disabled ? "Enable" : "Disable"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Module>
        )}
      </div>
    </div>
  );
}
