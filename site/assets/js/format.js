// Wording and formatting for the map. Prices are worded by the pipeline
// (pipeline/pricing.py) and shown as given; this file never words a price.

export const PLUG_GROUPS = {
  type2: { label: "Type 2", standards: ["IEC_62196_T2"] },
  ccs: { label: "CCS", standards: ["IEC_62196_T2_COMBO", "IEC_62196_T1_COMBO"] },
  chademo: { label: "CHAdeMO", standards: ["CHADEMO"] },
  other: { label: "Other", standards: null },
};

const PLUG_NAMES = {
  IEC_62196_T2: "Type 2",
  IEC_62196_T2_COMBO: "CCS (Combo 2)",
  IEC_62196_T1: "Type 1",
  IEC_62196_T1_COMBO: "CCS (Combo 1)",
  CHADEMO: "CHAdeMO",
  DOMESTIC_G: "UK 3-pin plug",
  TESLA_S: "Tesla",
  unknown: "Connector unknown",
};

// OCPI 2.2.1 EVSE statuses, worded neutrally.
export const STATUS_LABELS = {
  available: "Available",
  charging: "In use",
  blocked: "Blocked",
  inoperative: "Inoperative",
  out_of_order: "Out of order",
  planned: "Planned",
  removed: "Removed",
  reserved: "Reserved",
  unknown: "Status unknown",
};

export function plugName(standard) {
  return PLUG_NAMES[standard] ?? String(standard).replaceAll("_", " ");
}

export function plugGroup(standard) {
  for (const [group, { standards }] of Object.entries(PLUG_GROUPS)) {
    if (standards && standards.includes(standard)) return group;
  }
  return "other";
}

export function formatKw(kw) {
  if (kw === null || kw === undefined || !Number.isFinite(kw)) return "Power unknown";
  const rounded = Math.round(kw * 10) / 10;
  return `${rounded} kW`;
}

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/London",
  timeZoneName: "short",
});

export function formatDateTime(iso) {
  if (!iso) return "date not given";
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "date not given" : DATE_TIME.format(when);
}

export function plugsSummary(plugs) {
  const names = [...new Set((plugs ?? []).map((p) => PLUG_GROUPS[plugGroup(p)].label))];
  return names.length ? names.join(", ") : "Connector unknown";
}

// Map point colours group chargers by their fastest connector. 8 kW is where the Public
// Charge Point Regulations 2023 start requiring contactless payment; 50 kW is where they
// call a charge point rapid. 150 kW matches the ultra-rapid step in the power filter.
export const SPEED_BANDS = [
  { id: "ultra", min: 150, label: "150 kW or more (ultra-rapid)" },
  { id: "rapid", min: 50, label: "50 to 149 kW (rapid)" },
  { id: "fast", min: 8, label: "8 to 49 kW" },
  { id: "slow", min: 0, label: "Under 8 kW" },
];

export function speedBand(kw) {
  if (kw === null || kw === undefined || !Number.isFinite(kw)) return "unknown";
  return SPEED_BANDS.find((band) => kw >= band.min).id;
}

// True when every connector was reported out of service in the last daily fetch.
export function allOut(props) {
  return Boolean(props.cons?.length) && props.cons.every((c) => c.out === true);
}
