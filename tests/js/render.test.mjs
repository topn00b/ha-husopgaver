// Røgtest af kortets rendering og klik med en minimal DOM-erstatning (ingen afhængigheder).
import assert from "node:assert/strict";
import { test } from "node:test";

const registry = new Map();
globalThis.window = globalThis;
globalThis.customElements = {
  get: (name) => registry.get(name),
  define: (name, cls) => registry.set(name, cls),
};
globalThis.HTMLElement = class {
  attachShadow() {
    const listeners = { click: [], input: [] };
    this.shadowRoot = {
      innerHTML: "",
      addEventListener: (type, fn) => listeners[type].push(fn),
      click: (target) => listeners.click.forEach((fn) => fn({ target })),
      input: (target) => listeners.input.forEach((fn) => fn({ target })),
      // Til panelet: faste underelementer.
      parts: {},
      querySelector(selector) {
        this.parts[selector] ??= { innerHTML: "", children: [], appendChild(c) { this.children.push(c); } };
        return this.parts[selector];
      },
    };
    return this.shadowRoot;
  }
  get isConnected() {
    return true;
  }
};
globalThis.document = {
  createElement: (name) => new (registry.get(name))(),
};
globalThis.Event = class {
  constructor(type, options) {
    this.type = type;
    Object.assign(this, options);
  }
};
globalThis.localStorage = {
  data: {},
  getItem(k) {
    return k in this.data ? this.data[k] : null;
  },
  setItem(k, v) {
    this.data[k] = String(v);
  },
  removeItem(k) {
    delete this.data[k];
  },
};

await import("../../custom_components/husopgaver/frontend/husopgaver-card.js");

// Kortet bruger det aktuelle tidspunkt, så forfald regnes relativt til nu.
const NOW_ISO = new Date().toISOString();

const PAYLOAD = {
  loaded: true,
  upcoming_days: 2,
  viewer: { person_id: "v1", can_approve: true },
  persons: [
    { id: "v1", name: "Voksen 1", color: null, active: true, week_points: 4, pending_points: 0 },
    { id: "b1", name: "Barn 1", color: "#ff8000", active: true, week_points: 1, pending_points: 2 },
  ],
  chores: [
    { id: "c1", name: "Opvask <b>", description: null, points: 2, assignees: ["v1"], assignment: "fixed", repeat: "interval", every: 1, unit: "day", from: "due", weekdays: [], dates: [], due: null, due_time: "18:00", notify_before: null, approval: "auto", has_condition: false },
  ],
  items: [
    { uid: "c1|_shared|x", group: "today", chore_id: "c1", name: "Opvask <b>", key: "_shared", each: false, person_id: "v1", points: 2, due: NOW_ISO, has_time: true, status: "upcoming", condition_unknown: false, log_id: null },
    { uid: "c2|b1|x", group: "pending", chore_id: "c2", name: "Red seng", key: "b1", each: true, person_id: "b1", points: 2, due: "2026-06-09T22:00:00+00:00", has_time: false, status: "pending_approval", condition_unknown: false, log_id: "p1" },
    { uid: "log:l1", group: "done", chore_id: "c3", name: "Støvsug", key: "_shared", each: false, person_id: "v1", points: 3, due: "2026-06-10T07:00:00+00:00", has_time: true, status: null, condition_unknown: false, log_id: "l1" },
  ],
};

const HISTORY = {
  since: "2026-05-12T22:00:00+00:00",
  days: 30,
  bucket: "week",
  truncated: false,
  entries: [
    { id: "e1", timestamp: NOW_ISO, action: "completed", chore_id: "c1", chore_name: "Opvask", person_id: "b1", points: 2 },
    { id: "e2", timestamp: NOW_ISO, action: "skipped", chore_id: null, chore_name: null, person_id: "v1", points: 0 },
  ],
  totals: { b1: { points: 2, count: 1 } },
  buckets: [{ start: "2026-06-08", points: { b1: 2 } }],
  chores: [{ chore_id: "c1", chore_name: "Opvask", counts: { b1: 1 }, total: 1 }],
};

function makeCard(config = {}) {
  localStorage.data = {};
  const Card = customElements.get("husopgaver-card");
  const card = new Card();
  const calls = [];
  let push;
  card.hass = {
    locale: { language: "da" },
    config: { time_zone: "Europe/Copenhagen" },
    connection: {
      subscribeMessage: async (cb, msg) => {
        push = cb;
        calls.push(["subscribe", msg]);
        return () => calls.push(["unsubscribe"]);
      },
    },
    callService: async (domain, service, data) => calls.push([service, data]),
    callWS: async (msg) => {
      calls.push(["ws", msg]);
      return HISTORY;
    },
  };
  card.setConfig(config);
  return { card, calls, push: (data) => push(data) };
}

const button = (html, action, extra = "") => {
  const m = html.match(new RegExp(`data-action="${action}"[^>]*${extra}`));
  return m !== null;
};

test("renderer grupper, escaper og viser godkendknapper til en voksen", async () => {
  const { card, calls, push } = makeCard({ upcoming_days: 3 });
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls[0], ["subscribe", { type: "husopgaver/subscribe", upcoming_days: 3 }]);
  push(PAYLOAD);
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /Afventer godkendelse/);
  assert.match(html, /I dag \d\d:\d\d/);
  assert.match(html, /Opvask &lt;b&gt;/);
  assert.ok(!html.includes("Opvask <b>"));
  assert.ok(button(html, "approve"));
  assert.ok(button(html, "undo"));
  assert.match(html, /Point denne uge/);
  assert.match(html, /\+2 afventer/);
  // Afventer godkendelse kommer før I dag.
  assert.ok(html.indexOf("Afventer godkendelse") < html.indexOf(">I dag <"));
});

test("klik kalder de rigtige services", async () => {
  const { card, calls, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  push(PAYLOAD);
  const target = (dataset) => ({ closest: () => ({ dataset }) });
  card.shadowRoot.click(target({ action: "complete", uid: "c1|_shared|x" }));
  card.shadowRoot.click(target({ action: "approve", uid: "c2|b1|x" }));
  card.shadowRoot.click(target({ action: "undo", uid: "log:l1" }));
  card.shadowRoot.click(target({ action: "filter", person: "b1" }));
  card.shadowRoot.click(target({ action: "complete", uid: "c1|_shared|x" }));
  card.shadowRoot.click(target({ action: "snooze", uid: "c2|b1|x", hours: "24" }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.slice(1), [
    ["complete", { chore: "c1" }],
    ["approve", { log_id: "p1" }],
    ["undo", { log_id: "l1" }],
    ["complete", { chore: "c1", person: "b1" }],
    ["snooze", { chore: "c2", duration: { hours: 24 }, person: "b1" }],
  ]);
  // Filteret huskes på enheden.
  assert.equal(localStorage.getItem("husopgaver-card:filter:default"), "b1");
});

test("ikke sat op og indlæser", async () => {
  const { card, push } = makeCard();
  assert.match(card.shadowRoot.innerHTML, /Indlæser/);
  await new Promise((r) => setTimeout(r));
  push({ loaded: false, persons: [], items: [], viewer: {} });
  assert.match(card.shadowRoot.innerHTML, /ikke sat op/);
});

test("ny opgave fra kortet: knap, formular og create_chore", async () => {
  const { card, calls, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  push(PAYLOAD);
  assert.match(card.shadowRoot.innerHTML, /data-action="new"/);
  const target = (dataset) => ({ closest: () => ({ dataset }) });
  card.shadowRoot.click(target({ action: "new" }));
  let html = card.shadowRoot.innerHTML;
  assert.match(html, /Hvad skal laves\?/);
  assert.match(html, /Hver 2\. uge/);
  // Gem uden navn giver en fejl i formularen.
  card.shadowRoot.click(target({ action: "save" }));
  assert.match(card.shadowRoot.innerHTML, /Skriv, hvad der skal laves/);
  // Data, der kommer under redigering, tegner ikke formularen om.
  card.shadowRoot.input({ dataset: { field: "name" }, value: "Vand blomster" });
  push(PAYLOAD);
  assert.match(card.shadowRoot.innerHTML, /Hvad skal laves\?/);
  card.shadowRoot.click(target({ action: "toggle-person", person: "b1" }));
  card.shadowRoot.click(target({ action: "toggle-person", person: "v1" }));
  card.shadowRoot.click(target({ action: "set", field: "freq", value: "weekdays" }));
  card.shadowRoot.click(target({ action: "toggle-day", value: "sat" }));
  card.shadowRoot.click(target({ action: "points", delta: "1" }));
  card.shadowRoot.click(target({ action: "save" }));
  await new Promise((r) => setTimeout(r));
  const [service, data] = calls.at(-1);
  assert.equal(service, "create_chore");
  assert.deepEqual(
    [data.name, data.assignees, data.assignment, data.repeat, data.weekdays, data.points],
    ["Vand blomster", ["b1", "v1"], "round_robin", "weekly", ["sat"], 2],
  );
  // Efter gem vises listen igen.
  assert.match(card.shadowRoot.innerHTML, /Point denne uge/);
});

test("ret og slet en opgave", async () => {
  const { card, calls, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  push(PAYLOAD);
  assert.match(card.shadowRoot.innerHTML, /data-action="edit" data-chore="c1"/);
  const target = (dataset) => ({ closest: () => ({ dataset }) });
  card.shadowRoot.click(target({ action: "edit", chore: "c1" }));
  assert.match(card.shadowRoot.innerHTML, /Ret opgave/);
  card.shadowRoot.click(target({ action: "delete" }));
  assert.match(card.shadowRoot.innerHTML, /Tryk igen for at slette/);
  assert.equal(calls.filter(([s]) => s === "delete_chore").length, 0);
  card.shadowRoot.click(target({ action: "delete" }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.at(-1), ["delete_chore", { chore: "c1" }]);
});

test("redigering kan slås fra", async () => {
  const { card, push } = makeCard({ allow_edit: false });
  await new Promise((r) => setTimeout(r));
  push(PAYLOAD);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="add"|data-chore=/);
});

test("siden i sidemenuen viser kortet uden titel og med menuknap på smal skærm", async () => {
  const Panel = customElements.get("husopgaver-panel");
  const panel = new Panel();
  const events = [];
  panel.dispatchEvent = (ev) => events.push(ev.type);
  panel.narrow = true;
  const { card: probe } = makeCard();
  panel.hass = { ...probe._hass };
  const card = panel.shadowRoot.querySelector(".content").children[0];
  assert.equal(card.constructor, customElements.get("husopgaver-card"));
  assert.equal(card._config.title, "");
  assert.match(panel.shadowRoot.querySelector(".toolbar").innerHTML, /menu-toggle/);
  panel.shadowRoot.click({ closest: () => ({}) });
  assert.deepEqual(events, ["hass-toggle-menu"]);
  panel.narrow = false;
  assert.doesNotMatch(panel.shadowRoot.querySelector(".toolbar").innerHTML, /menu-toggle/);
});

test("den, der har tid: spørger hvem på den fælles tablet", async () => {
  const { card, calls, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  const item = { uid: "o|_shared|x", group: "today", chore_id: "o", name: "Tøm opvaskemaskine", key: "_shared", each: false, open: true, assignees: ["v1", "b1"], person_id: null, points: 1, due: NOW_ISO, has_time: false, status: "due", condition_unknown: false, log_id: null };
  push({ ...PAYLOAD, viewer: { person_id: null, can_approve: false }, items: [item] });
  assert.match(card.shadowRoot.innerHTML, /Den, der har tid/);
  const target = (dataset) => ({ closest: () => ({ dataset }) });
  card.shadowRoot.click(target({ action: "complete", uid: item.uid }));
  assert.match(card.shadowRoot.innerHTML, /Hvem gjorde det\?/);
  assert.equal(calls.filter(([s]) => s === "complete").length, 0);
  card.shadowRoot.click(target({ action: "complete", uid: item.uid, person: "b1" }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.at(-1), ["complete", { chore: "o", person: "b1" }]);

  // På en telefon, der er logget ind som en person, krediteres den person direkte.
  push({ ...PAYLOAD, viewer: { person_id: "v1", can_approve: true }, items: [item] });
  card.shadowRoot.click(target({ action: "complete", uid: item.uid }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.at(-1), ["complete", { chore: "o", person: "v1" }]);
});

test("viser Opdatér, når integrationen er nyere end kortet", async () => {
  const { card, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  push({ ...PAYLOAD, version: "99.0.0" });
  assert.match(card.shadowRoot.innerHTML, /data-action="reload"/);
  push({ ...PAYLOAD });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /data-action="reload"/);
});

test("faner: historik og statistik henter data og følger filter og periode", async () => {
  const { card, calls, push } = makeCard();
  await new Promise((r) => setTimeout(r));
  push(PAYLOAD);
  const target = (dataset) => ({ closest: () => ({ dataset }) });
  card.shadowRoot.click(target({ action: "tab", tab: "history" }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.at(-1), ["ws", { type: "husopgaver/history", days: 30 }]);
  let html = card.shadowRoot.innerHTML;
  assert.match(html, /I dag/);
  assert.match(html, /Opvask/);
  assert.match(html, /\+2/);
  assert.match(html, /Sprunget over/);
  assert.match(html, /Slettet opgave/);
  assert.doesNotMatch(html, /class="add"/);

  card.shadowRoot.click(target({ action: "filter", person: "b1" }));
  card.shadowRoot.click(target({ action: "period", days: "all" }));
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls.at(-1), ["ws", { type: "husopgaver/history", person: "b1" }]);

  card.shadowRoot.click(target({ action: "tab", tab: "stats" }));
  await new Promise((r) => setTimeout(r));
  html = card.shadowRoot.innerHTML;
  assert.match(html, /Point per uge/);
  assert.match(html, /Uge 24/);
  assert.match(html, /Hvem laver hvad/);
  assert.match(html, /2 point · 1 opgave/);

  // Nye data, mens fanen er åben, henter historikken igen.
  const before = calls.filter(([s]) => s === "ws").length;
  push(PAYLOAD);
  await new Promise((r) => setTimeout(r));
  assert.equal(calls.filter(([s]) => s === "ws").length, before + 1);

  card.shadowRoot.click(target({ action: "tab", tab: "chores" }));
  assert.match(card.shadowRoot.innerHTML, /class="add"/);
});
