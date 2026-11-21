import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, FileStack, Files, LogOut, Moon, ShieldCheck, Sun, TriangleAlert, Upload as UploadIcon } from "lucide-react";
import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { API_URL, api, ApiError, getApiKey, setApiKey } from "./api";
import { Button, cx, ErrorNote, Module } from "./components/ui";
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
        <span className="label-mono block">Accounts payable</span>
      </span>
    </span>
  );
}

function SignIn({ onSignIn }: { onSignIn: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(false);

  async function submit() {
    setChecking(true);
    setError(null);
    setApiKey(key.trim());
    try {
      await api.me();
      onSignIn();
    } catch (e) {
      setApiKey(null);
      if (e instanceof ApiError && e.status === 401) {
        setError(new Error("That key was not recognised. Type only the part before any colon."));
      } else if (e instanceof ApiError) {
        setError(e);
      } else {
        // fetch itself failed: wrong address, the API is asleep or starting, or CORS blocked it.
        setError(
          new Error(
            `Could not reach the server at ${API_URL}. If it was idle it can take up to a minute to wake up; try again.`,
          ),
        );
      }
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="mx-auto mt-20 max-w-md px-4">
      <div className="mb-6 flex items-center justify-between">
        <Brand />
        <ThemeToggle />
      </div>
      <h1 className="mb-4 font-display text-2xl font-bold tracking-tight">Sign in</h1>
      <Module title="Reviewer access" bodyClassName="space-y-3 p-4">
        <p className="text-sm text-ink-2">
          Reviewers sign in with their API key. Every decision is recorded under the name the key belongs to.
        </p>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="block text-sm font-semibold" htmlFor="api-key">
            API key
          </label>
          <input
            id="api-key"
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="h-10 w-full rounded-lg border border-line px-3 font-mono text-sm"
            autoFocus
          />
          <Button type="submit" size="lg" className="w-full" disabled={!key.trim() || checking}>
            {checking ? "Checking…" : "Sign in"}
          </Button>
          <ErrorNote error={error} />
        </form>
        {DEMO_HINT && <p className="text-xs text-ink-2">{DEMO_HINT}</p>}
        <SyntheticLabel />
      </Module>
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
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 10000 });
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
            <NavTab to="/invoices" icon={Files} label="All invoices" />
            <NavTab to="/failed" icon={FileStack} label="Failed jobs" count={failed} alert />
            <NavTab to="/metrics" icon={BarChart3} label="Metrics" />
            <NavTab to="/upload" icon={UploadIcon} label="Upload" />
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
          <Route path="*" element={<Navigate to="/review" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(getApiKey()));
  const queryClient = useQueryClient();
  if (!signedIn) return <SignIn onSignIn={() => setSignedIn(true)} />;
  return (
    <Shell
      onSignOut={() => {
        setApiKey(null);
        queryClient.clear();
        setSignedIn(false);
      }}
    />
  );
}
