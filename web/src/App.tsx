import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, FileStack, Files, LogOut, Moon, Plug, ShieldCheck, Sun, TriangleAlert, Upload as UploadIcon } from "lucide-react";
import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { API_URL, api, ApiError, getApiKey, setApiKey } from "./api";
import { Button, cx, ErrorNote, Module } from "./components/ui";
import { PackProvider, usePack } from "./packContext";
import Connections from "./pages/Connections";
import FailedJobs from "./pages/FailedJobs";
import InvoiceDetailPage from "./pages/InvoiceDetail";
import InvoiceList from "./pages/InvoiceList";
import Metrics from "./pages/Metrics";
import ReviewDesk from "./pages/ReviewDesk";
import Upload from "./pages/Upload";

const DEMO_HINT: string | undefined = import.meta.env.VITE_DEMO_HINT;

function SyntheticLabel() {
  return (
    <span className="whitespace-nowrap rounded-full bg-amber-tint px-2 py-0.5 text-xs font-semibold text-amber">
      Synthetic demo data
    </span>
  );
}

function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"),
  );
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("invoiceguard.theme", next);
    } catch {
      /* not persisted; applies for this visit */
    }
    setTheme(next);
  }
  return { theme, toggle };
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <Button variant="ghost" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
      <Icon aria-hidden className="h-4 w-4" />
    </Button>
  );
}

function Brand() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span aria-hidden className="grid h-9 w-9 place-items-center rounded-full bg-accent text-accent-ink">
        <ShieldCheck className="h-5 w-5" />
      </span>
      <span className="leading-tight">
        <span className="block font-display text-md font-bold tracking-tight">InvoiceGuard</span>
        <span className="label-mono block">Review desk</span>
      </span>
    </span>
  );
}

function AuthScreen({ onSignIn }: { onSignIn: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [key, setKey] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function explain(e: unknown): Error {
    if (e instanceof ApiError) return new Error(e.status === 401 ? "Wrong email or password." : e.message);
    // fetch itself failed: wrong address, the API is asleep or starting, or CORS blocked it.
    return new Error(`Could not reach the server at ${API_URL}. If it was idle it can take up to a minute to wake up; try again.`);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = mode === "login" ? await api.login(email, password) : await api.signup(email, name, password);
      setApiKey(result.token);
      onSignIn();
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  async function useKey() {
    setBusy(true);
    setError(null);
    // A pasted "key:name" pair works too: the name is never part of the key.
    setApiKey(key.trim().split(":")[0]);
    try {
      await api.me();
      onSignIn();
    } catch (e) {
      setApiKey(null);
      setError(e instanceof ApiError && e.status === 401 ? new Error("That key was not recognised.") : explain(e));
    } finally {
      setBusy(false);
    }
  }

  const valid = email.includes("@") && password.length >= (mode === "signup" ? 10 : 1) && (mode === "login" || name.trim().length >= 2);

  return (
    <main className="mx-auto mt-16 max-w-md px-4">
      <div className="mb-6 flex items-center justify-between">
        <Brand />
        <ThemeToggle />
      </div>
      <h1 className="mb-4 font-display text-2xl font-bold tracking-tight">{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <Module title={mode === "login" ? "Welcome back" : "Get started"} bodyClassName="space-y-3 p-4">
        <p className="text-sm text-ink-2">
          {mode === "login"
            ? "Sign in with your email. Every decision is recorded under your name."
            : "Create an account to review cases. The first account on a new deployment becomes its administrator."}
        </p>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {mode === "signup" && (
            <label className="block text-sm font-semibold" htmlFor="name">
              Name
              <input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal" />
            </label>
          )}
          <label className="block text-sm font-semibold" htmlFor="email">
            Email
            <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal" autoFocus />
          </label>
          <label className="block text-sm font-semibold" htmlFor="password">
            Password {mode === "signup" && <span className="font-normal text-ink-2">(at least 10 characters)</span>}
            <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal" />
          </label>
          <Button type="submit" size="lg" className="w-full" disabled={!valid || busy}>
            {busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
          <ErrorNote error={error} />
        </form>
        <p className="text-sm text-ink-2">
          {mode === "login" ? "New here? " : "Already have an account? "}
          <button type="button" className="font-semibold text-accent hover:underline" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}>
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
        {DEMO_HINT && <p className="text-xs text-ink-2">{DEMO_HINT}</p>}
        <SyntheticLabel />
      </Module>

      <details className="mt-4 rounded-xl border border-line bg-surface p-4 text-sm">
        <summary className="cursor-pointer font-semibold">Use an API key instead</summary>
        <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); void useKey(); }}>
          <p className="text-ink-2">For a shared reviewer key your administrator gave you.</p>
          <input aria-label="API key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} className="h-10 w-full rounded-lg border border-line px-3 font-mono text-sm" />
          <Button type="submit" variant="secondary" disabled={!key.trim() || busy}>
            Use this key
          </Button>
        </form>
      </details>
    </main>
  );
}

function NavTab({ to, icon: Icon, label, count, alert }: { to: string; icon: typeof Files; label: string; count?: number; alert?: boolean }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cx(
          "-mb-px inline-flex h-12 shrink-0 items-center gap-1.5 border-b-2 px-3.5 text-sm font-medium",
          isActive ? "border-accent text-ink" : "border-transparent text-ink-2 hover:text-ink",
        )
      }
    >
      <Icon aria-hidden className="h-4 w-4" />
      {label}
      {count !== undefined && count > 0 && (
        <span className={cx("rounded-full px-1.5 font-mono text-xs", alert ? "bg-red text-bg" : "bg-fill text-ink-2")}>
          {count}
        </span>
      )}
    </NavLink>
  );
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  const { pack, setPack, packs } = usePack();
  const metrics = useQuery({ queryKey: ["metrics", pack], queryFn: () => api.metrics(pack), refetchInterval: 10000 });
  const review = metrics.data?.invoices_by_status.NEEDS_REVIEW ?? 0;
  const failed = metrics.data?.operations.open_failed_jobs ?? 0;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-1 px-5">
          <div className="py-3">
            <Brand />
          </div>
          <nav aria-label="Main" className="order-last -mx-2 flex w-full overflow-x-auto md:order-none md:mx-0 md:w-auto">
            <NavTab to="/review" icon={TriangleAlert} label="Review queue" count={review} alert />
            <NavTab to="/invoices" icon={Files} label="All cases" />
            <NavTab to="/failed" icon={FileStack} label="Failed jobs" count={failed} alert />
            <NavTab to="/metrics" icon={BarChart3} label="Metrics" />
            <NavTab to="/upload" icon={UploadIcon} label="Upload" />
            {(me.data?.account || me.data?.scopes.includes("admin")) && <NavTab to="/connections" icon={Plug} label="API keys" />}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden lg:inline">
              <SyntheticLabel />
            </span>
            {me.data && (
              <span className="hidden text-sm text-ink-2 sm:inline">
                <b className="font-semibold text-ink">{me.data.name}</b>
              </span>
            )}
            {packs.length > 1 && (
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <span className="label-mono hidden md:inline">Workflow</span>
                <select
                  aria-label="Workflow"
                  value={pack}
                  onChange={(e) => setPack(e.target.value)}
                  className="h-9 rounded-lg border border-line px-2 text-sm font-medium text-ink"
                >
                  {packs.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <ThemeToggle />
            <Button variant="ghost" onClick={onSignOut} aria-label="Sign out">
              <LogOut aria-hidden className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-5 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/review" replace />} />
          <Route path="/review" element={<ReviewDesk />} />
          <Route path="/invoices" element={<InvoiceList />} />
          <Route path="/invoices/:id" element={<InvoiceDetailPage />} />
          <Route path="/failed" element={<FailedJobs />} />
          <Route path="/metrics" element={<Metrics />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="*" element={<Navigate to="/review" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(getApiKey()));
  const queryClient = useQueryClient();
  if (!signedIn) return <AuthScreen onSignIn={() => setSignedIn(true)} />;
  return (
    <PackProvider>
      <Shell
        onSignOut={() => {
          // End the session on the server too, so the token cannot be reused.
          void api.logout().catch(() => undefined);
          setApiKey(null);
          queryClient.clear();
          setSignedIn(false);
        }}
      />
    </PackProvider>
  );
}
