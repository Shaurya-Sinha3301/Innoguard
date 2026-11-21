import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "hsl(var(--surface))",
              color: "hsl(var(--ink))",
              border: "1px solid hsl(var(--line))",
              borderRadius: "14px",
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
