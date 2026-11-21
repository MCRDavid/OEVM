// Saving settings is opt-in (docs/PRIVACY_AND_COOKIES.md, rule 4). Nothing is written
// to the device until the visitor turns on "Remember my settings on this device", and
// forget() deletes everything this site saved. Every access is guarded, because storage
// can be blocked or unavailable.

import { parse, serialise } from "./filters.js";
import { cardList, cleanCards } from "./cards.js";
import { cleanRates, rateList } from "./rates.js";

export const STORAGE_KEY = "oevm.settings.v1";
const THEMES = ["light", "dark"];

export function createSettings(storage) {
  function read() {
    try {
      return storage ? storage.getItem(STORAGE_KEY) : null;
    } catch {
      return null;
    }
  }
  return {
    isRemembered() {
      return read() !== null;
    },
    load() {
      const raw = read();
      if (raw === null) return null;
      try {
        const saved = JSON.parse(raw);
        return saved && saved.version === 1 && typeof saved.filters === "string"
          ? parse(saved.filters)
          : null;
      } catch {
        return null;
      }
    },
    // The light or dark appearance the visitor picked, if they picked one and saved it.
    theme() {
      try {
        const saved = JSON.parse(read());
        return THEMES.includes(saved?.theme) ? saved.theme : null;
      } catch {
        return null;
      }
    },
    // The ids of the charging plans the visitor said they have, if saved.
    plans() {
      try {
        const saved = JSON.parse(read());
        return Array.isArray(saved?.plans) ? saved.plans.filter((id) => typeof id === "string") : [];
      } catch {
        return [];
      }
    },
    // The visitor's own rates (rates.js, ADR 0035), by network id, if saved.
    rates() {
      try {
        return cleanRates(JSON.parse(read())?.rates);
      } catch {
        return new Map();
      }
    },
    // The visitor's own cards (cards.js, ADR 0035), by id, if saved.
    cards() {
      try {
        return cleanCards(JSON.parse(read())?.cards);
      } catch {
        return new Map();
      }
    },
    // Only called after the visitor has opted in. Returns false if saving failed. theme is
    // saved only when the visitor picked one; otherwise the page follows the device. plans,
    // rates and cards are saved only when the visitor ticked or typed in at least one.
    save(state, theme = null, plans = [], rates = new Map(), cards = new Map()) {
      const saved = { version: 1, filters: serialise(state) };
      if (THEMES.includes(theme)) saved.theme = theme;
      if (plans.length) saved.plans = [...plans];
      const own = rateList(rates);
      if (own.length) saved.rates = own;
      const mine = cardList(cards);
      if (mine.length) saved.cards = mine;
      try {
        storage.setItem(STORAGE_KEY, JSON.stringify(saved));
        return true;
      } catch {
        return false;
      }
    },
    forget() {
      try {
        storage?.removeItem(STORAGE_KEY);
        return true;
      } catch {
        return false;
      }
    },
  };
}
