// Saving settings is opt-in (docs/PRIVACY_AND_COOKIES.md, rule 4). Nothing is written
// to the device until the visitor turns on "Remember my settings on this device", and
// forget() deletes everything this site saved. Every access is guarded, because storage
// can be blocked or unavailable.

import { parse, serialise } from "./filters.js";

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
    // Only called after the visitor has opted in. Returns false if saving failed. theme is
    // saved only when the visitor picked one; otherwise the page follows the device.
    save(state, theme = null) {
      const saved = { version: 1, filters: serialise(state) };
      if (THEMES.includes(theme)) saved.theme = theme;
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
