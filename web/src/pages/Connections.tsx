import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Plug } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { API_URL, api } from "../api";
import { Button, Empty, ErrorNote, Module, SkeletonRows, Table, td, th } from "../components/ui";
import { when } from "../format";
import { usePack } from "../packContext";

const AGENT_SCOPES: Array<{ scope: string; text: string }> = [
  { scope: "read", text: "Read cases, documents and metrics" },
  { scope: "submit", text: "Submit documents" },
  { scope: "propose", text: "Suggest a decision (changes nothing)" },
  { scope: "post", text: "Post approved cases (still needs a human's grant)" },
];

export default function Connections() {
  const queryClient = useQueryClient();
  const principals = useQuery({ queryKey: ["principals"], queryFn: api.principals });
  const [name, setName] = useState("");
  const { packs } = usePack();
  const [scopes, setScopes] = useState<string[]>(["read", "propose"]);
  const [chosenPacks, setChosenPacks] = useState<string[] | null>(null);
  const allowed = chosenPacks ?? packs.map((p) => p.id);
  const [issued, setIssued] = useState<{ name: string; key: string } | null>(null);

  const create = useMutation({
    mutationFn: () => api.createPrincipal({ name: name.trim(), kind: "agent", scopes, packs: allowed }),
    onSuccess: (row) => {
      setIssued({ name: row.name, key: row.key });
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["principals"] });
    },
  });
  const disable = useMutation({
    mutationFn: (id: string) => api.disablePrincipal(id),
    onSuccess: () => {
      toast.success("Key disabled. It stops working immediately.");
      void queryClient.invalidateQueries({ queryKey: ["principals"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "That did not work"),
  });

  function toggle(scope: string) {
    setScopes((s) => (s.includes(scope) ? s.filter((x) => x !== scope) : [...s, scope]));
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="label-mono">Connections</p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight">Agents and integrations</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          An agent can read, submit and suggest. It can never approve or reject: a person decides. Posting an approved
          case also needs a grant a person issues for that one case.
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-12">
        <Module icon={KeyRound} title="Issue a key" className="lg:col-span-5" bodyClassName="space-y-4 p-4">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label className="block text-sm font-semibold" htmlFor="agent-name">
              Name
              <input
                id="agent-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="claude-desktop-ap-team"
                className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"
              />
            </label>
            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold">What it may do</legend>
              {AGENT_SCOPES.map(({ scope, text }) => (
                <label key={scope} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope)}
                    onChange={() => toggle(scope)}
                    className="mt-1 accent-[hsl(var(--accent))]"
                  />
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
                      checked={allowed.includes(p.id)}
                      onChange={() =>
                        setChosenPacks(allowed.includes(p.id) ? allowed.filter((x) => x !== p.id) : [...allowed, p.id])
                      }
                      className="mt-1 accent-[hsl(var(--accent))]"
                    />
                    <span>{p.name}</span>
                  </label>
                ))}
              </fieldset>
            )}
            <ErrorNote error={create.error} />
            <Button type="submit" disabled={name.trim().length < 2 || scopes.length === 0 || allowed.length === 0 || create.isPending}>
              Issue key
            </Button>
          </form>

          {issued && (
            <div role="status" className="space-y-2 rounded-xl border border-accent/60 bg-accent-tint p-3">
              <p className="text-sm font-semibold">Key for {issued.name}. Copy it now: it is not shown again.</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded-lg bg-fill px-2 py-1.5 font-mono text-[13px]">
                  {issued.key}
                </code>
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

        <Module icon={Plug} title="Connected" count={principals.data?.length} className="lg:col-span-7">
          <ErrorNote error={principals.error} />
          {principals.isLoading && <SkeletonRows rows={4} cols={4} />}
          {principals.data && principals.data.length === 0 && (
            <Empty title="No agents yet">Issue a key to let an agent read cases and suggest decisions.</Empty>
          )}
          {principals.data && principals.data.length > 0 && (
            <Table label="Agents and integrations">
              <thead>
                <tr>
                  <th className={th}>Name</th>
                  <th className={th}>Key</th>
                  <th className={th}>Scopes</th>
                  <th className={th}>Last used</th>
                  <th className={th}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {principals.data.map((p) => (
                  <tr key={p.id} className={p.disabled ? "opacity-50" : ""}>
                    <td className={td}>
                      {p.name} {p.disabled && <span className="text-xs text-ink-2">disabled</span>}
                    </td>
                    <td className={`${td} font-mono text-[13px] text-ink-2`}>{p.key_prefix}…</td>
                    <td className={`${td} font-mono text-xs text-ink-2`}>{p.scopes.join(", ")}</td>
                    <td className={`${td} text-ink-2`}>{p.last_used_at ? when(p.last_used_at) : "never"}</td>
                    <td className={td}>
                      {!p.disabled && (
                        <Button variant="danger" disabled={disable.isPending} onClick={() => disable.mutate(p.id)}>
                          Disable
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <p className="border-t border-line px-4 py-3 text-xs text-ink-2">
            Agents send the key as <code className="font-mono">Authorization: Bearer &lt;key&gt;</code> to{" "}
            <code className="font-mono">{API_URL}</code>.
          </p>
        </Module>
      </div>
    </div>
  );
}
