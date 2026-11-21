import { useQueries, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { getPack, registerManifest, setSelectedPack, type Manifest } from "./pack";

type PackState = {
  /** The workflow the reviewer is working in: "invoices", "expenses". */
  pack: string;
  setPack: (id: string) => void;
  packs: { id: string; name: string }[];
  manifest: Manifest | null;
};

const KEY = "invoiceguard.pack";
const Ctx = createContext<PackState>({ pack: "invoices", setPack: () => {}, packs: [], manifest: null });

function remembered(): string {
  try {
    return localStorage.getItem(KEY) ?? "invoices";
  } catch {
    return "invoices";
  }
}

/** Loads every pack's manifest once and tracks which pack the reviewer has selected. */
export function PackProvider({ children }: { children: ReactNode }) {
  const [pack, setPackState] = useState(remembered);
  const list = useQuery({ queryKey: ["packs"], queryFn: api.packs, staleTime: Infinity });
  const manifests = useQueries({
    queries: (list.data ?? []).map((p) => ({
      queryKey: ["pack", p.id],
      queryFn: async () => {
        const manifest = await api.pack(p.id);
        registerManifest(manifest);
        return manifest;
      },
      staleTime: Infinity,
    })),
  });

  // A remembered pack this key cannot use falls back to the first one it can.
  useEffect(() => {
    if (list.data && list.data.length > 0 && !list.data.some((p) => p.id === pack)) {
      setPackState(list.data[0].id);
    }
  }, [list.data, pack]);
  setSelectedPack(pack);

  const value = useMemo<PackState>(
    () => ({
      pack,
      setPack: (id: string) => {
        try {
          localStorage.setItem(KEY, id);
        } catch {
          /* not remembered; applies for this visit */
        }
        setPackState(id);
      },
      packs: list.data ?? [],
      manifest: getPack(pack),
    }),
    // manifests changing means a manifest arrived, so the memoised manifest must be re-read
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pack, list.data, manifests.map((q) => q.data?.id).join(",")],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePack(): PackState {
  return useContext(Ctx);
}

/** "invoice", "claim": what a case is called in the selected pack. */
export function useNoun(): { one: string; many: string; counterparty: string } {
  const { manifest } = usePack();
  const one = manifest?.case_noun ?? "case";
  return { one, many: `${one}s`, counterparty: manifest?.counterparty ?? "Counterparty" };
}
