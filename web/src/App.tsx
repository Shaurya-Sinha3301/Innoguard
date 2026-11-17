import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { getApiKey, setApiKey } from "./api";
import { Button, Card, Input } from "./components/ui";
import FailedJobs from "./pages/FailedJobs";
import InvoiceDetailPage from "./pages/InvoiceDetail";
import InvoiceList from "./pages/InvoiceList";
import Metrics from "./pages/Metrics";
import Upload from "./pages/Upload";

const DEMO_HINT: string | undefined = import.meta.env.VITE_DEMO_HINT;

function SignIn({ onSignIn }: { onSignIn: () => void }) {
  const [key, setKey] = useState("");
  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <Card className="space-y-4 p-6">
        <div>
          <h1 className="text-lg font-semibold">InvoiceGuard</h1>
          <p className="text-sm text-muted-foreground">Enter your reviewer API key.</p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setApiKey(key.trim());
            onSignIn();
          }}
        >
          <Input
            type="password"
            aria-label="API key"
            placeholder="API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoFocus
          />
          <Button type="submit" className="w-full" disabled={!key.trim()}>
            Sign in
          </Button>
        </form>
        {DEMO_HINT && <p className="text-xs text-muted-foreground">{DEMO_HINT}</p>}
      </Card>
    </main>
  );
}

const nav = [
  { to: "/review", label: "Review queue" },
  { to: "/invoices", label: "All invoices" },
  { to: "/failed", label: "Failed jobs" },
  { to: "/metrics", label: "Metrics" },
  { to: "/upload", label: "Upload" },
];

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(getApiKey()));
  const queryClient = useQueryClient();

  if (!signedIn) return <SignIn onSignIn={() => setSignedIn(true)} />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold">InvoiceGuard</span>
          <nav className="flex flex-wrap gap-1">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm ${isActive ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto rounded bg-warning/15 px-2 py-0.5 text-xs text-warning">
            Synthetic demo data
          </span>
          <Button
            variant="ghost"
            onClick={() => {
              setApiKey(null);
              queryClient.clear();
              setSignedIn(false);
            }}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/review" replace />} />
          <Route path="/review" element={<InvoiceList status="NEEDS_REVIEW" title="Review queue" />} />
          <Route path="/invoices" element={<InvoiceList title="All invoices" />} />
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
