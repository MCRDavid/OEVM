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
  // Not an OCPI status: shown only by the owner's decision in an operator file.
  working: "Working (free or in use, not stated)",
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

// Map point colours. A location with a DC connector takes the colour of its fastest DC
// connector; one with only AC connectors takes the colour of its fastest AC connector.
// AC and DC are kept apart because many cars take 7 or 11 kW at most on AC, whatever the
// post offers, but can use far more on DC. Whether a connector is AC or DC comes from the
// feed's power_type (cur in schema/published.py), never from its plug. The DC steps match
// the rapid (50 kW) and ultra-rapid (150 kW) bands in the Department for Transport's
// statistics; the AC steps split lamp posts (mostly 3 to 5 kW) from 7 kW posts and from
// 11 to 22 kW ones. Ordered fastest first within each kind.
export const POWER_BANDS = [
  { id: "dc150", cur: "dc", min: 150, label: "DC 150 kW or more" },
  { id: "dc100", cur: "dc", min: 100, label: "DC 100 to 149 kW" },
  { id: "dc50", cur: "dc", min: 50, label: "DC 50 to 99 kW" },
  { id: "dc", cur: "dc", min: 0, label: "DC under 50 kW" },
  { id: "ac11", cur: "ac", min: 11, label: "AC 11 kW or more" },
  { id: "ac7", cur: "ac", min: 6, label: "AC 6 to 10 kW" },
  { id: "ac", cur: "ac", min: 0, label: "AC under 6 kW" },
];

function fastest(cons, cur) {
  const powers = (cons ?? []).filter((c) => c.cur === cur && Number.isFinite(c.kw)).map((c) => c.kw);
  return powers.length ? Math.max(...powers) : null;
}

// "unknown" when no connector has both a power and an AC or DC type.
export function powerBand(cons) {
  for (const cur of ["dc", "ac"]) {
    const kw = fastest(cons, cur);
    if (kw !== null) return POWER_BANDS.find((band) => band.cur === cur && kw >= band.min).id;
  }
  return "unknown";
}

// True when every connector was reported out of service in the last daily fetch.
export function allOut(props) {
  return Boolean(props.cons?.length) && props.cons.every((c) => c.out === true);
}
