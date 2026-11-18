import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, FileStack, Files, LogOut, ShieldCheck, TriangleAlert, Upload as UploadIcon } from "lucide-react";
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
    <span className="whitespace-nowrap rounded-sm bg-amber-tint px-1.5 py-px text-xs font-semibold text-amber">
      Synthetic demo data
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
    <main className="mx-auto mt-24 max-w-sm px-4">
      <Module title="Sign in to InvoiceGuard" bodyClassName="space-y-3 p-4">
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
            className="h-9 w-full rounded border border-line px-2.5 font-mono text-sm"
            autoFocus
          />
          <Button type="submit" className="w-full" disabled={!key.trim() || checking}>
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
          "-mb-px inline-flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-sm font-semibold",
          isActive ? "border-red text-red" : "border-transparent text-ink-2 hover:text-ink",
        )
      }
    >
      <Icon aria-hidden className="h-4 w-4" />
      {label}
      {count !== undefined && count > 0 && (
        <span className={cx("rounded-sm px-1.5 font-mono text-xs", alert ? "bg-red text-bg" : "bg-fill text-ink-2")}>
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
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
          <span className="inline-flex items-center gap-1.5 text-md font-bold tracking-tight">
            <ShieldCheck aria-hidden className="h-5 w-5 text-ink" />
            InvoiceGuard
          </span>
          <span className="hidden text-xs text-ink-2 sm:inline">Accounts payable · three-way match</span>
          <div className="ml-auto flex items-center gap-3">
            <SyntheticLabel />
            {me.data && <span className="text-sm text-ink-2">Signed in as <b className="text-ink">{me.data.name}</b></span>}
            <Button variant="ghost" onClick={onSignOut} aria-label="Sign out">
              <LogOut aria-hidden className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
        <nav aria-label="Main" className="mx-auto flex max-w-[1600px] overflow-x-auto px-2">
          <NavTab to="/review" icon={TriangleAlert} label="Review queue" count={review} alert />
          <NavTab to="/invoices" icon={Files} label="All invoices" />
          <NavTab to="/failed" icon={FileStack} label="Failed jobs" count={failed} alert />
          <NavTab to="/metrics" icon={BarChart3} label="Metrics" />
          <NavTab to="/upload" icon={UploadIcon} label="Upload" />
        </nav>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-3">
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
