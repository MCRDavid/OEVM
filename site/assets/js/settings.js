// Saving settings is opt-in (docs/PRIVACY_AND_COOKIES.md, rule 4). Nothing is written
// to the device until the visitor turns on "Remember my settings on this device", and
// forget() deletes everything this site saved. Every access is guarded, because storage
// can be blocked or unavailable.

import { parse, serialise } from "./filters.js";

export const STORAGE_KEY = "oevm.settings.v1";

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
    // Only called after the visitor has opted in. Returns false if saving failed.
    save(state) {
      try {
        storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, filters: serialise(state) }));
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
