// "Your own cards" in the filters panel (cards.js, ADR 0035): the visitor names a card,
// ticks the networks it works on (or starts from a card this site lists, with its
// networks ticked for them), types in what it charges on every ticked network and,
// where one network differs, what it charges there, then saves it. Cards are kept in
// memory, and saved only with "Remember my settings", like own rates.

import { h } from "./dom.js";
import { CURRENTS, ratePence } from "./rates.js";
import {
  MAX_CARDS,
  cardSummary,
  cardTextFor,
  cleanCards,
  feePounds,
  figuresText,
  newCardId,
  percentOff,
} from "./cards.js";

const $ = (id) => document.getElementById(id);

function blank(input) {
  return input.value.trim() === "";
}

// networks: [{ op, name }] in the order to list them. known: [{ name, ops }] from
// knownCards. cards: the Map of the visitor's cards, changed in place. onChange is called
// after a card is saved or removed.
export function buildCardForm({ networks, known, cards, onChange }) {
  const nameOf = new Map(networks.map((n) => [n.op, n.name]));
  const networkName = (op) => nameOf.get(op) ?? op;
  const boxes = new Map();
  let editing = null; // the id of the card in the form, or null for a new one
  let nets = {}; // figures for one network, by network id, for the card in the form
  const message = $("card-message");

  const ticked = () => networks.map((n) => n.op).filter((op) => boxes.get(op).checked);
  const showCount = () => {
    const count = ticked().length;
    $("card-ops-count").textContent = count === 1 ? "1 network ticked" : `${count} networks ticked`;
  };

  // Reads a price, percentage or fee box: { value } when blank or valid, otherwise
  // { error } with what to type, and the box to focus.
  const read = (input, parse, error) => {
    if (blank(input)) return { value: null };
    const value = parse(input.value);
    return value === null ? { error, input } : { value };
  };
  const priceError = (cur) => `Type the ${cur.toUpperCase()} price in whole pence from 1 to 300, such as 48, or leave it empty.`;
  const pctError = "Type the percentage off as a number above 0 and up to 90, such as 10, or leave it empty.";
  // The AC, DC and percentage boxes with this prefix ("card" or "card-net") as figures.
  const readFigures = (prefix) => {
    const out = {};
    for (const cur of CURRENTS) {
      const got = read($(`${prefix}-${cur}`), ratePence, priceError(cur));
      if (got.error) return got;
      out[cur] = got.value;
    }
    const pct = read($(`${prefix}-pct`), percentOff, pctError);
    if (pct.error) return pct;
    out.pct = pct.value;
    return { value: out };
  };
  const fail = (got) => {
    message.textContent = got.error;
    got.input.focus();
  };

  // Figures for one network.
  const fillNetForm = () => {
    const f = nets[$("card-net-op").value];
    for (const key of ["ac", "dc", "pct"]) $(`card-net-${key}`).value = f?.[key] == null ? "" : String(f[key]);
  };
  const renderNetPicker = () => {
    const select = $("card-net-op");
    const chosen = select.value;
    const ops = ticked();
    select.replaceChildren(
      h("option", { value: "", text: ops.length ? "Choose a ticked network" : "Tick a network first" }),
      ...ops.map((op) => h("option", { value: op, text: networkName(op) })),
    );
    select.value = ops.includes(chosen) ? chosen : "";
    const items = ops
      .filter((op) => nets[op])
      .map((op) =>
        h(
          "li",
          {},
          h("span", { text: `${networkName(op)}: ${figuresText(nets[op])}` }),
          h("button", {
            type: "button",
            text: "Change",
            "aria-label": `Change the figures for ${networkName(op)}`,
            onClick: () => {
              select.value = op;
              fillNetForm();
              $("card-net-ac").focus();
            },
          }),
          h("button", {
            type: "button",
            text: "Remove",
            "aria-label": `Remove the figures for ${networkName(op)}`,
            onClick: () => {
              delete nets[op];
              if (select.value === op) fillNetForm();
              message.textContent = `The figures for ${networkName(op)} have been removed. Save the card to use the change.`;
              renderNetPicker();
              select.focus();
            },
          }),
        ),
      );
    $("card-net-list").replaceChildren(...items);
  };
  const useNet = () => {
    const op = $("card-net-op").value;
    if (!op) {
      message.textContent = "Choose a ticked network for these figures.";
      $("card-net-op").focus();
      return;
    }
    const got = readFigures("card-net");
    if (got.error) return fail(got);
    const f = got.value;
    if (f.ac === null && f.dc === null && f.pct === null) delete nets[op];
    else nets[op] = f;
    message.textContent = nets[op]
      ? `${networkName(op)}: ${figuresText(f)}. Save the card to use it.`
      : `The figures for ${networkName(op)} have been removed. Save the card to use the change.`;
    renderNetPicker();
  };

  // The card in the form.
  const fill = (card) => {
    editing = card?.id ?? null;
    nets = structuredClone(card?.nets ?? {});
    $("card-start").value = "";
    $("card-name").value = card?.name ?? "";
    for (const [op, box] of boxes) box.checked = Boolean(card?.ops.includes(op));
    for (const key of ["ac", "dc", "pct"]) $(`card-${key}`).value = card?.[key] == null ? "" : String(card[key]);
    $("card-fee").value = card?.fee == null ? "" : String(card.fee);
    $("card-note").value = card?.note ?? "";
    $("card-net-op").value = "";
    $("card-save").textContent = card ? "Save changes to this card" : "Save this card";
    showCount();
    renderNetPicker();
    fillNetForm();
  };

  const save = () => {
    const name = $("card-name").value.trim();
    if (!name) {
      message.textContent = "Type a name for the card, such as the app it is in.";
      $("card-name").focus();
      return;
    }
    // A network the card was saved for that is not on the map today is kept.
    const away = editing ? (cards.get(editing)?.ops ?? []).filter((op) => !boxes.has(op)) : [];
    const ops = [...ticked(), ...away];
    if (!ops.length) {
      message.textContent = "Tick at least one network the card works on.";
      $("card-ops").querySelector("input")?.focus();
      return;
    }
    const all = readFigures("card");
    if (all.error) return fail(all);
    const fee = read($("card-fee"), feePounds, "Type the monthly fee in pounds from 0 to 100, such as 7.99, or leave it empty.");
    if (fee.error) return fail(fee);
    if (!editing && cards.size >= MAX_CARDS) {
      message.textContent = `You can keep up to ${MAX_CARDS} cards. Remove one to add another.`;
      return;
    }
    const id = editing ?? newCardId(cards);
    const card = cleanCards([{ id, name, ops, ...all.value, fee: fee.value, note: $("card-note").value, nets }]).get(id);
    if (!card) {
      message.textContent = "Type a price or a percentage off, for every ticked network or for one of them.";
      $("card-ac").focus();
      return;
    }
    cards.set(id, card);
    editing = id;
    $("card-save").textContent = "Save changes to this card";
    const where = ops.length === 1 ? networkName(ops[0]) : `${ops.length} networks`;
    const summary = ops.length === 1 ? cardTextFor(card, ops[0]) : cardSummary(card);
    message.textContent = `Your card “${card.name}” is now used on ${where}${summary ? `: ${summary}` : ""}.`;
    renderList();
    onChange();
  };

  const renderList = () => {
    const items = [...cards.values()].map((card) => {
      const where = card.ops.length === 1 ? networkName(card.ops[0]) : `${card.ops.length} networks`;
      const summary = card.ops.length === 1 ? cardTextFor(card, card.ops[0]) : cardSummary(card);
      // A card for one network has that network's figures in its summary already.
      const differs = card.ops.length === 1 ? 0 : Object.keys(card.nets).length;
      const parts = [
        summary,
        differs ? `different on ${differs === 1 ? "1 network" : `${differs} networks`}` : "",
        card.note ? `(${card.note})` : "",
      ].filter(Boolean);
      return h(
        "li",
        {},
        h("span", { text: `${card.name}, on ${where}: ${parts.join("; ")}` }),
        h("button", {
          type: "button",
          text: "Change",
          "aria-label": `Change your card “${card.name}”`,
          onClick: () => {
            fill(card);
            message.textContent = "";
            $("card-name").focus();
          },
        }),
        h("button", {
          type: "button",
          text: "Remove",
          "aria-label": `Remove your card “${card.name}”`,
          onClick: () => {
            cards.delete(card.id);
            if (editing === card.id) fill(null);
            message.textContent = `Your card “${card.name}” has been removed.`;
            renderList();
            onChange();
            $("card-name").focus();
          },
        }),
      );
    });
    $("card-list").replaceChildren(...items);
  };

  // Build the form.
  const start = $("card-start");
  start.append(...known.map((entry, i) => h("option", { value: String(i), text: `${entry.name} (${entry.ops.length === 1 ? "1 network" : `${entry.ops.length} networks`})` })));
  start.addEventListener("change", () => {
    const entry = known[Number(start.value)];
    if (!entry || start.value === "") return;
    $("card-name").value = entry.name;
    for (const [op, box] of boxes) box.checked = entry.ops.includes(op);
    showCount();
    renderNetPicker();
    message.textContent = `${entry.name}'s networks on this map are ticked, as this site lists them. Untick any you do not use it on, then type in what it charges.`;
  });
  const list = $("card-ops");
  for (const { op, name } of networks) {
    const box = h("input", { type: "checkbox", value: op });
    boxes.set(op, box);
    box.addEventListener("change", () => {
      showCount();
      renderNetPicker();
    });
    list.append(h("label", {}, box, ` ${name}`));
  }
  const tickAll = (on) => {
    for (const box of boxes.values()) box.checked = on;
    showCount();
    renderNetPicker();
  };
  $("card-all").addEventListener("click", () => tickAll(true));
  $("card-none").addEventListener("click", () => tickAll(false));
  $("card-net-op").addEventListener("change", fillNetForm);
  $("card-net-use").addEventListener("click", useNet);
  $("card-save").addEventListener("click", save);
  $("card-new").addEventListener("click", () => {
    fill(null);
    message.textContent = "The form is clear for a new card.";
    $("card-name").focus();
  });
  // Enter in a box saves the card, or the figures for one network, rather than sending
  // the filters form.
  $("my-cards").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.target.tagName !== "INPUT" || event.target.type === "checkbox") return;
    event.preventDefault();
    if (event.target.closest("#card-nets")) useNet();
    else save();
  });
  fill(null);
  renderList();

  return {
    // From a charger's details: the first card that works on this network goes in the
    // form, or a new card with this network ticked.
    edit(op) {
      const card = [...cards.values()].find((c) => c.ops.includes(op));
      fill(card ?? null);
      if (!card && boxes.has(op)) {
        boxes.get(op).checked = true;
        showCount();
        renderNetPicker();
      }
      message.textContent = "";
      $("card-name").focus();
    },
  };
}
