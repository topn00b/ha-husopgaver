// Tests af dashboardkortets rene funktioner. Kør med: node --test tests/js/*.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  creditPerson,
  dueText,
  escapeHtml,
  filterItems,
  groupItems,
  localDay,
  personColor,
  PALETTE,
  pointsBoard,
  texts,
} from "../../custom_components/husopgaver/frontend/husopgaver-card.js";

const TZ = "Europe/Copenhagen";
const da = texts("da");
// Onsdag 10. juni 2026 kl. 10:00 lokal tid.
const NOW = new Date("2026-06-10T08:00:00Z");

test("sprog", () => {
  assert.equal(texts("da-DK").today, "I dag");
  assert.equal(texts("de").today, "Today");
  assert.equal(texts(undefined).today, "Today");
});

test("lokal dato i HA's tidszone", () => {
  // 23:30 UTC den 9. er 01:30 den 10. i København.
  assert.equal(localDay(new Date("2026-06-09T23:30:00Z"), TZ), "2026-06-10");
});

test("forfaldstekst", () => {
  const at = (iso, hasTime = false) => dueText(iso, hasTime, NOW, da, "da", TZ);
  assert.equal(at("2026-06-09T22:00:00Z"), "I dag");
  assert.equal(at("2026-06-10T16:00:00Z", true), "I dag 18:00");
  assert.equal(at("2026-06-10T22:30:00Z", true), "I morgen 00:30");
  assert.equal(at("2026-06-10T22:00:00Z"), "I morgen");
  assert.equal(at("2026-06-08T22:00:00Z"), "I går");
  assert.equal(at("2026-06-12T22:00:00Z"), "Om 3 dage");
  assert.equal(at("2026-06-06T22:00:00Z"), "For 3 dage siden");
  // Længere ude vises datoen; formatet følger browserens locale-data.
  assert.match(at("2026-07-01T22:00:00Z"), /2/);
});

test("forfaldstekst ved skift til vintertid", () => {
  // Lørdag 24. oktober kl. 12; søndag 25. har 25 timer.
  const now = new Date("2026-10-24T10:00:00Z");
  assert.equal(dueText("2026-10-25T23:00:00Z", false, now, da, "da", TZ), "Om 2 dage");
  assert.equal(dueText("2026-10-24T22:00:00Z", false, now, da, "da", TZ), "I morgen");
});

test("hvem krediteres", () => {
  assert.equal(creditPerson({ each: false, key: "_shared" }, null), null);
  assert.equal(creditPerson({ each: true, key: "b1" }, null), "b1");
  assert.equal(creditPerson({ each: false, key: "_shared" }, "v2"), "v2");
});

test("filter og grupper", () => {
  const items = [
    { uid: "1", group: "later", person_id: "v1" },
    { uid: "2", group: "overdue", person_id: "v2" },
    { uid: "3", group: "today", person_id: "v1" },
    { uid: "4", group: "pending", person_id: "b1" },
  ];
  assert.deepEqual(
    groupItems(items).map(([g, list]) => [g, list.map((i) => i.uid)]),
    [
      ["pending", ["4"]],
      ["overdue", ["2"]],
      ["today", ["3"]],
      ["later", ["1"]],
    ],
  );
  assert.deepEqual(filterItems(items, "v1").map((i) => i.uid), ["1", "3"]);
  assert.equal(filterItems(items, null).length, 4);
});

test("farver", () => {
  const persons = [{ id: "v1", color: "#123456" }, { id: "v2" }, { id: "b1" }];
  assert.equal(personColor(persons, "v1"), "#123456");
  assert.equal(personColor(persons, "b1"), PALETTE[2]);
  assert.match(personColor(persons, "ukendt"), /disabled/);
});

test("pointtavle", () => {
  const board = pointsBoard([
    { id: "a", name: "Barn 1", week_points: 3, active: true },
    { id: "b", name: "Voksen 1", week_points: 7, active: true },
    { id: "c", name: "Barn 2", week_points: 9, active: false },
    { id: "d", name: "Barn 0", week_points: 3, active: true },
  ]);
  assert.deepEqual(board.map((p) => p.id), ["b", "d", "a"]);
});

test("escape", () => {
  assert.equal(escapeHtml('<b a="1">&\''), "&lt;b a=&quot;1&quot;&gt;&amp;&#39;");
  assert.equal(escapeHtml(null), "");
});
