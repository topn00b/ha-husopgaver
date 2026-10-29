// Tests af kortets formular: fra formular til service-kald og tilbage.
import assert from "node:assert/strict";
import { test } from "node:test";

import { choreToForm, formToService, newForm } from "../../custom_components/husopgaver/frontend/husopgaver-card.js";

const TODAY = "2026-06-10";
const base = (overrides) => ({ ...newForm(TODAY, null), name: "Støvsug", assignees: ["v1", "v2"], ...overrides });

test("ny opgave: standard er hver uge, på skift, 1 point", () => {
  const form = newForm(TODAY, "b1");
  assert.deepEqual([form.freq, form.assignment, form.points, form.assignees], ["weekly", "round_robin", 1, ["b1"]]);
});

test("valideringsfejl", () => {
  assert.deepEqual(formToService(base({ name: "  " })), { error: "err_name" });
  assert.deepEqual(formToService(base({ assignees: [] })), { error: "err_who" });
  assert.deepEqual(formToService(base({ freq: "weekdays", weekdays: [] })), { error: "err_days" });
  assert.deepEqual(formToService(base({ freq: "once", date: "" })), { error: "err_date" });
});

test("hver uge på skift", () => {
  assert.deepEqual(formToService(base({})), {
    service: "create_chore",
    data: {
      name: "Støvsug",
      assignees: ["v1", "v2"],
      points: 1,
      assignment: "round_robin",
      description: null,
      due_time: null,
      notify_before: null,
      approval: "auto",
      repeat: "interval",
      every: 1,
      unit: "week",
      from: "due",
    },
  });
});

test("én person er altid fast", () => {
  assert.equal(formToService(base({ assignees: ["v1"], assignment: "least_points" })).data.assignment, "fixed");
});

test("bestemte dage, klokkeslæt og påmindelse", () => {
  const { data } = formToService(
    base({ freq: "weekdays", weekdays: ["thu", "mon"], time: "18:00", notify: "30", description: " Også glas " }),
  );
  assert.deepEqual(
    [data.repeat, data.weekdays, data.due_time, data.notify_before, data.description],
    ["weekly", ["mon", "thu"], "18:00:00", { minutes: 30 }, "Også glas"],
  );
});

test("én gang og hvert år", () => {
  const once = formToService(base({ freq: "once", date: "2026-06-12", time: "09:30" })).data;
  assert.deepEqual([once.repeat, once.due, once.due_time], ["none", "2026-06-12 09:30:00", "09:30:00"]);
  const yearly = formToService(base({ freq: "yearly", date: "2026-10-01", extraDates: ["04-01"] })).data;
  assert.deepEqual([yearly.repeat, yearly.dates], ["yearly", ["10-01", "04-01"]]);
});

test("andet: hver 3. dag fra sidst udført", () => {
  const { data } = formToService(base({ freq: "custom", every: "3", unit: "day", from: "completion" }));
  assert.deepEqual([data.every, data.unit, data.from], [3, "day", "completion"]);
});

test("ret: update_chore med opgavens id", () => {
  const result = formToService(base({ id: "c1" }));
  assert.equal(result.service, "update_chore");
  assert.equal(result.data.chore, "c1");
});

const chore = (overrides) => ({
  id: "c1",
  name: "Aftensmad",
  description: null,
  points: 2,
  assignees: ["v1", "v2"],
  assignment: "least_points",
  repeat: "interval",
  every: 1,
  unit: "day",
  from: "due",
  weekdays: [],
  dates: [],
  due: null,
  due_time: "18:00",
  notify_before: 30,
  approval: "auto",
  has_condition: true,
  ...overrides,
});

test("fra opgave til formular og tilbage", () => {
  for (const [overrides, freq] of [
    [{}, "daily"],
    [{ unit: "week" }, "weekly"],
    [{ every: 2, unit: "week" }, "biweekly"],
    [{ unit: "month" }, "monthly"],
    [{ every: 3, unit: "day" }, "custom"],
    [{ from: "completion", unit: "week" }, "custom"],
    [{ repeat: "weekly", weekdays: ["mon", "fri"] }, "weekdays"],
    [{ repeat: "none", due: "2026-06-12 18:00" }, "once"],
    [{ repeat: "yearly", dates: ["10-01", "04-01"] }, "yearly"],
  ]) {
    const c = chore(overrides);
    const form = choreToForm(c, TODAY);
    assert.equal(form.freq, freq, JSON.stringify(overrides));
    const { data } = formToService(form);
    assert.equal(data.repeat, c.repeat);
    if (c.repeat === "interval") assert.deepEqual([data.every, data.unit, data.from], [c.every, c.unit, c.from]);
    if (c.repeat === "weekly") assert.deepEqual(data.weekdays, c.weekdays);
    if (c.repeat === "yearly") assert.deepEqual(data.dates, c.dates);
    if (c.repeat === "none") assert.equal(data.due, "2026-06-12 18:00:00");
    assert.deepEqual(
      [data.assignment, data.due_time, data.notify_before, data.points],
      ["least_points", "18:00:00", { minutes: 30 }, 2],
    );
  }
  assert.equal(choreToForm(chore({}), TODAY).hasCondition, true);
});

test("efter en anden opgave", () => {
  assert.deepEqual(formToService(base({ freq: "after", after: "" })), { error: "err_after" });
  const { data } = formToService(base({ freq: "after", after: "vask", delay: "1440" }));
  assert.deepEqual([data.repeat, data.after, data.delay], ["after", "vask", { minutes: 1440 }]);
  const form = choreToForm(chore({ repeat: "after", after: "vask", delay: 60 }), TODAY);
  assert.deepEqual([form.freq, form.after, form.delay], ["after", "vask", 60]);
  assert.deepEqual(formToService(form).data.delay, { minutes: 60 });
});
