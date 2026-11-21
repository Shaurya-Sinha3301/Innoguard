/** Workflow packs: every manifest the server has, and which one the reviewer is working in.
 * Reason texts, tolerances and thresholds come from the server so the screen never states a
 * number the rules do not use. */

export type ManifestReason = {
  code: string;
  label: string;
  explain: string;
  severity: "hard" | "soft";
};

export type Manifest = {
  id: string;
  name: string;
  description: string;
  document: string;
  case_noun: string;
  counterparty: string;
  how_it_works: { title: string; text: string }[];
  reasons: ManifestReason[];
  reason_prefixes: ManifestReason[];
  thresholds: { min_extraction_confidence: string; min_match_quality: string; max_auto_amount: string | null };
  tolerances: { price_pct: string; qty_pct: string; amount_abs: string; date_window_days: number; max_claim_age_days: number };
  queue_columns: string[];
  detail_sections: string[];
  implied_reason: string | null;
  synthetic_data_notice: string;
};

const manifests = new Map<string, Manifest>();
let selected = "invoices";

export function registerManifest(manifest: Manifest) {
  manifests.set(manifest.id, manifest);
}

export function setSelectedPack(id: string) {
  selected = id;
}

/** The manifest for a pack, or for the selected one. Null until it has loaded. */
export function getPack(id?: string): Manifest | null {
  return manifests.get(id ?? selected) ?? null;
}

export function allManifests(): Manifest[] {
  return [...manifests.values()];
}

/** Fractional price tolerance (0.02 for 2%). Falls back to the Release 1 value until loaded. */
export function priceTolerance(): number {
  const m = getPack("invoices");
  return m ? Number(m.tolerances.price_pct) / 100 : 0.02;
}

/** Fields read with confidence below this are flagged. */
export function lowConfidence(): number {
  const m = getPack();
  return m ? Number(m.thresholds.min_extraction_confidence) : 0.9;
}
