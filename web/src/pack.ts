/** The active workflow pack's manifest, loaded once after sign-in. Reason texts, tolerances and
 * thresholds come from the server so the screen never states a number the rules do not use. */

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
  reasons: ManifestReason[];
  reason_prefixes: ManifestReason[];
  thresholds: { min_extraction_confidence: string; min_match_quality: string; max_auto_amount: string | null };
  tolerances: { price_pct: string; qty_pct: string; amount_abs: string };
  queue_columns: string[];
  detail_sections: string[];
  implied_reason: string | null;
  synthetic_data_notice: string;
};

let current: Manifest | null = null;

export function setPack(manifest: Manifest | null) {
  current = manifest;
}

export function getPack(): Manifest | null {
  return current;
}

/** Fractional price tolerance (0.02 for 2%). Falls back to the Release 1 value until loaded. */
export function priceTolerance(): number {
  return current ? Number(current.tolerances.price_pct) / 100 : 0.02;
}

/** Fields read with confidence below this are flagged. */
export function lowConfidence(): number {
  return current ? Number(current.thresholds.min_extraction_confidence) : 0.9;
}
