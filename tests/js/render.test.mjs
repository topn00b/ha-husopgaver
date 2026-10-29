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
    const listeners = [];
    this.shadowRoot = {
      innerHTML: "",
      addEventListener: (type, fn) => listeners.push(fn),
      click: (target) => listeners.forEach((fn) => fn({ target })),
    };
    return this.shadowRoot;
  }
  get isConnected() {
    return true;
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
  items: [
    { uid: "c1|_shared|x", group: "today", chore_id: "c1", name: "Opvask <b>", key: "_shared", each: false, person_id: "v1", points: 2, due: NOW_ISO, has_time: true, status: "upcoming", condition_unknown: false, log_id: null },
    { uid: "c2|b1|x", group: "pending", chore_id: "c2", name: "Red seng", key: "b1", each: true, person_id: "b1", points: 2, due: "2026-06-09T22:00:00+00:00", has_time: false, status: "pending_approval", condition_unknown: false, log_id: "p1" },
    { uid: "log:l1", group: "done", chore_id: "c3", name: "Støvsug", key: "_shared", each: false, person_id: "v1", points: 3, due: "2026-06-10T07:00:00+00:00", has_time: true, status: null, condition_unknown: false, log_id: "l1" },
  ],
};

function makeCard(config = {}) {
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
