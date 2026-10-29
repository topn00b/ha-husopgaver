// Husopgaver: dashboardkort til familiens opgaver.
// Rent web component uden byggetrin, CDN eller eksterne biblioteker.
// Data kommer fra websocket-abonnementet husopgaver/subscribe, færdiggrupperet.

// Skal svare til manifest.json (testet). Kortet sammenligner med integrationens
// version og beder om en genindlæsning, hvis browseren kører en gammel kopi.
export const VERSION = "0.8.0";

const CARD_TYPE = "husopgaver-card";
const EDITOR_TYPE = "husopgaver-card-editor";
const PANEL_TYPE = "husopgaver-panel";

// Fast palet, når en person ikke har en farve. Læsbar i lyst og mørkt tema.
export const PALETTE = [
  "#1e88e5",
  "#e53935",
  "#43a047",
  "#fb8c00",
  "#8e24aa",
  "#00897b",
  "#d81b60",
  "#6d4c41",
];

export const GROUP_ORDER = ["pending", "overdue", "today", "upcoming", "later", "done"];

const TEXTS = {
  da: {
    title: "Husopgaver",
    all: "Alle",
    outdated: "Der er kommet en ny version af Husopgaver.",
    tabs: { chores: "Opgaver", history: "Historik", stats: "Statistik" },
    periods: { 7: "7 dage", 30: "30 dage", 90: "3 måneder", 365: "1 år", all: "Alt" },
    actions: {
      completed: "Lavet",
      approved: "Lavet (godkendt)",
      pending: "Afventer godkendelse",
      skipped: "Sprunget over",
      not_needed: "Ikke nødvendig",
      rejected: "Afvist",
      settled: "Udbetalt",
    },
    deleted_chore: "Slettet opgave",
    no_history: "Ingen historik i perioden.",
    truncated: "Viser de seneste 500.",
    week: (n) => `Uge ${n}`,
    totals: "I alt",
    per_week: "Point per uge",
    per_month: "Point per måned",
    who_does_what: "Hvem laver hvad",
    tasks: (n) => `${n} ${n === 1 ? "opgave" : "opgaver"}`,
    reload: "Opdatér",
    loading: "Indlæser…",
    not_loaded: "Husopgaver er ikke sat op.",
    empty: "Ingen opgaver lige nu.",
    groups: {
      pending: "Afventer godkendelse",
      overdue: "Overskredet",
      today: "I dag",
      upcoming: "Kommende",
      later: "Senere",
      done: "Udført i dag",
    },
    points: (n) => `${n} point`,
    points_board: "Point denne uge",
    pending_points: (n) => `+${n} afventer`,
    today: "I dag",
    tomorrow: "I morgen",
    yesterday: "I går",
    in_days: (n) => `Om ${n} dage`,
    days_ago: (n) => `For ${n} dage siden`,
    done_at: "Udført",
    complete: "Kryds af",
    approve: "Godkend",
    reject: "Afvis",
    undo: "Fortryd",
    skip: "Spring over",
    snooze_hour: "Udsæt 1 time",
    snooze_day: "Udsæt 1 dag",
    give_to: (name) => `Giv til ${name}`,
    more: "Flere handlinger",
    awaiting: "Afventer godkendelse",
    condition_unknown: "Betingelse ukendt",
    unassigned: "Ingen",
    new_chore: "Ny opgave",
    edit_chore: "Ret opgave",
    f_name: "Hvad skal laves?",
    f_who: "Hvem?",
    f_rotation: "Hvordan fordeles den?",
    rotation: {
      round_robin: "Skiftes",
      least_points: "Færrest point",
      fixed: "Altid den første",
      each: "Alle hver for sig",
      open: "Den, der har tid",
    },
    anyone: "Den, der har tid",
    who_did_it: "Hvem gjorde det?",
    f_freq: "Hvor tit?",
    freq: {
      once: "Én gang",
      daily: "Hver dag",
      weekdays: "Bestemte dage",
      weekly: "Hver uge",
      biweekly: "Hver 2. uge",
      monthly: "Hver måned",
      yearly: "Hvert år",
      after: "Efter en anden opgave",
      custom: "Andet",
    },
    f_after: "Efter hvilken opgave?",
    f_delay: "Hvornår?",
    delays: { 0: "Med det samme", 60: "1 time efter", 180: "3 timer efter", 1440: "Dagen efter" },
    choose: "Vælg…",
    err_after: "Vælg den opgave, den kommer efter.",
    weekdays: ["Ma", "Ti", "On", "To", "Fr", "Lø", "Sø"],
    f_date: "Dato",
    f_time: "Klokkeslæt (valgfrit)",
    f_points: "Point",
    f_every: "Hver",
    units: { day: "dage", week: "uger", month: "måneder" },
    f_from: "Næste gang regnes fra",
    from: { due: "Fast rytme", completion: "Sidst udført" },
    more_options: "Flere valg",
    fewer_options: "Færre valg",
    f_description: "Beskrivelse",
    f_notify: "Påmindelse",
    notify: { 0: "Ingen", 15: "15 min før", 30: "30 min før", 60: "1 time før" },
    f_approval: "Skal godkendes",
    approval: { auto: "Hvis personen skal", always: "Altid", never: "Aldrig" },
    has_condition: "Opgaven har en betingelse (kalender eller entitet). Den bevares.",
    save: "Gem",
    cancel: "Annullér",
    delete: "Slet",
    confirm_delete: "Tryk igen for at slette",
    saving: "Gemmer…",
    err_name: "Skriv, hvad der skal laves.",
    err_who: "Vælg mindst én person.",
    err_days: "Vælg mindst én dag.",
    err_date: "Vælg en dato.",
  },
  en: {
    title: "Chores",
    all: "All",
    outdated: "A new version of Husopgaver is available.",
    tabs: { chores: "Chores", history: "History", stats: "Statistics" },
    periods: { 7: "7 days", 30: "30 days", 90: "3 months", 365: "1 year", all: "All" },
    actions: {
      completed: "Done",
      approved: "Done (approved)",
      pending: "Awaiting approval",
      skipped: "Skipped",
      not_needed: "Not needed",
      rejected: "Rejected",
      settled: "Settled",
    },
    deleted_chore: "Deleted chore",
    no_history: "No history in this period.",
    truncated: "Showing the latest 500.",
    week: (n) => `Week ${n}`,
    totals: "Total",
    per_week: "Points per week",
    per_month: "Points per month",
    who_does_what: "Who does what",
    tasks: (n) => `${n} ${n === 1 ? "chore" : "chores"}`,
    reload: "Update",
    loading: "Loading…",
    not_loaded: "Husopgaver is not set up.",
    empty: "No chores right now.",
    groups: {
      pending: "Awaiting approval",
      overdue: "Overdue",
      today: "Today",
      upcoming: "Upcoming",
      later: "Later",
      done: "Done today",
    },
    points: (n) => `${n} ${n === 1 ? "point" : "points"}`,
    points_board: "Points this week",
    pending_points: (n) => `+${n} pending`,
    today: "Today",
    tomorrow: "Tomorrow",
    yesterday: "Yesterday",
    in_days: (n) => `In ${n} days`,
    days_ago: (n) => `${n} days ago`,
    done_at: "Done",
    complete: "Complete",
    approve: "Approve",
    reject: "Reject",
    undo: "Undo",
    skip: "Skip",
    snooze_hour: "Snooze 1 hour",
    snooze_day: "Snooze 1 day",
    give_to: (name) => `Give to ${name}`,
    more: "More actions",
    awaiting: "Awaiting approval",
    condition_unknown: "Condition unknown",
    unassigned: "Nobody",
    new_chore: "New chore",
    edit_chore: "Edit chore",
    f_name: "What needs doing?",
    f_who: "Who?",
    f_rotation: "How is it shared?",
    rotation: {
      round_robin: "Take turns",
      least_points: "Fewest points",
      fixed: "Always the first",
      each: "Everyone separately",
      open: "Whoever has time",
    },
    anyone: "Whoever has time",
    who_did_it: "Who did it?",
    f_freq: "How often?",
    freq: {
      once: "Once",
      daily: "Every day",
      weekdays: "Certain days",
      weekly: "Every week",
      biweekly: "Every 2 weeks",
      monthly: "Every month",
      yearly: "Every year",
      after: "After another chore",
      custom: "Other",
    },
    f_after: "After which chore?",
    f_delay: "When?",
    delays: { 0: "Right away", 60: "1 hour after", 180: "3 hours after", 1440: "The day after" },
    choose: "Choose…",
    err_after: "Choose the chore it comes after.",
    weekdays: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    f_date: "Date",
    f_time: "Time (optional)",
    f_points: "Points",
    f_every: "Every",
    units: { day: "days", week: "weeks", month: "months" },
    f_from: "Next time counts from",
    from: { due: "Fixed rhythm", completion: "Last done" },
    more_options: "More options",
    fewer_options: "Fewer options",
    f_description: "Description",
    f_notify: "Reminder",
    notify: { 0: "None", 15: "15 min before", 30: "30 min before", 60: "1 hour before" },
    f_approval: "Needs approval",
    approval: { auto: "If the person does", always: "Always", never: "Never" },
    has_condition: "This chore has a condition (calendar or entity). It is kept.",
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    confirm_delete: "Tap again to delete",
    saving: "Saving…",
    err_name: "Write what needs doing.",
    err_who: "Choose at least one person.",
    err_days: "Choose at least one day.",
    err_date: "Choose a date.",
  },
};

/** Om browseren kører en ældre kopi af kortet end integrationen. */
export function isOutdated(serverVersion, cardVersion = VERSION) {
  return Boolean(serverVersion) && serverVersion !== cardVersion;
}

/** Tekster på brugerens sprog. Andre sprog end dansk får engelsk. */
export function texts(language) {
  return String(language || "").toLowerCase().startsWith("da") ? TEXTS.da : TEXTS.en;
}

/** Personens farve, ellers en fast farve efter rækkefølge. */
export function personColor(persons, personId) {
  const index = persons.findIndex((p) => p.id === personId);
  if (index < 0) return "var(--disabled-text-color, #9e9e9e)";
  return persons[index].color || PALETTE[index % PALETTE.length];
}

/** Lokal dato (YYYY-MM-DD) i HA's tidszone. */
export function localDay(date, timeZone) {
  // Bygget af dele, så resultatet ikke afhænger af, hvilke locales browseren har.
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function dayNumber(isoDay) {
  const [y, m, d] = isoDay.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86400000;
}

/** "I dag 18:00", "I morgen", "Om 3 dage", "I går" osv. */
export function dueText(dueIso, hasTime, now, t, locale, timeZone) {
  const due = new Date(dueIso);
  const diff = dayNumber(localDay(due, timeZone)) - dayNumber(localDay(now, timeZone));
  let day;
  if (diff === 0) day = t.today;
  else if (diff === 1) day = t.tomorrow;
  else if (diff === -1) day = t.yesterday;
  else if (diff > 1 && diff <= 6) day = t.in_days(diff);
  else if (diff < -1 && diff >= -6) day = t.days_ago(-diff);
  else
    day = new Intl.DateTimeFormat(locale, { timeZone, day: "numeric", month: "short" }).format(due);
  if (!hasTime) return day;
  return `${day} ${clockTime(due, timeZone)}`;
}

/** Klokkeslæt som 24-timers HH:MM i HA's tidszone, uanset browserens locale-data. */
export function clockTime(date, timeZone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get("hour")}:${get("minute")}`;
}

/**
 * Hvem en afkrydsning fra kortet krediteres: den valgte person i filteret,
 * ellers forekomstens person ved "alle hver for sig", ellers den tildelte (null).
 * Ved "den, der har tid" er der ingen tildelt: så den, der er logget ind, og
 * er det fx den fælles tablet, må der spørges (undefined).
 */
export function creditPerson(item, filterId, viewerId = null) {
  if (filterId) return filterId;
  if (item.each) return item.key;
  if (item.open) return viewerId || undefined;
  return null;
}

/** Opgaverne for den valgte person, eller alle. Åbne opgaver står hos alle de valgte. */
export function filterItems(items, filterId) {
  if (!filterId) return items;
  return items.filter((item) =>
    item.open && item.group !== "done"
      ? (item.assignees || []).includes(filterId)
      : item.person_id === filterId,
  );
}

/** Grupper i fast rækkefølge; tomme grupper udelades. */
export function groupItems(items) {
  const groups = new Map(GROUP_ORDER.map((g) => [g, []]));
  for (const item of items) {
    if (groups.has(item.group)) groups.get(item.group).push(item);
  }
  return GROUP_ORDER.filter((g) => groups.get(g).length).map((g) => [g, groups.get(g)]);
}

/** ISO-ugenummer for en dato (YYYY-MM-DD). */
export function isoWeek(isoDay) {
  const [y, m, d] = isoDay.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
}

/** "Uge 24" eller "jun. 2026". */
export function bucketLabel(startIso, kind, t, locale) {
  if (kind === "week") return t.week(isoWeek(startIso));
  const [y, m] = startIso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, 1)),
  );
}

/** "I dag", "I går" eller datoen. */
export function dayLabel(dayIso, todayIso, t, locale) {
  const diff = dayNumber(todayIso) - dayNumber(dayIso);
  if (diff === 0) return t.today;
  if (diff === 1) return t.yesterday;
  const [y, m, d] = dayIso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** Historikkens poster grupperet per lokal dag, nyeste først. */
export function groupByDay(entries, timeZone) {
  const days = new Map();
  for (const entry of entries) {
    const day = localDay(new Date(entry.timestamp), timeZone);
    if (!days.has(day)) days.set(day, []);
    days.get(day).push(entry);
  }
  return [...days.entries()];
}

/** Pointtavlen: aktive personer med flest point først. */
export function pointsBoard(persons) {
  return persons
    .filter((p) => p.active)
    .slice()
    .sort((a, b) => b.week_points - a.week_points || a.name.localeCompare(b.name));
}

export const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export const FREQUENCIES = [
  "once",
  "daily",
  "weekdays",
  "weekly",
  "biweekly",
  "monthly",
  "yearly",
  "after",
  "custom",
];

// Faste valg i dialogen, og hvordan de svarer til en interval-gentagelse.
const INTERVAL_PRESETS = {
  daily: [1, "day"],
  weekly: [1, "week"],
  biweekly: [2, "week"],
  monthly: [1, "month"],
};

/** En tom formular til en ny opgave. */
export function newForm(todayIso, personId) {
  return {
    id: null,
    name: "",
    description: "",
    assignees: personId ? [personId] : [],
    assignment: "round_robin",
    freq: "weekly",
    weekdays: [],
    date: todayIso,
    extraDates: [],
    time: "",
    points: 1,
    every: 1,
    unit: "week",
    from: "due",
    notify: 0,
    approval: "auto",
    hasCondition: false,
    after: "",
    delay: 0,
  };
}

/** En eksisterende opgaves indstillinger som formular. */
export function choreToForm(chore, todayIso) {
  const form = {
    ...newForm(todayIso, null),
    id: chore.id,
    name: chore.name,
    description: chore.description || "",
    assignees: [...chore.assignees],
    assignment: chore.assignment === "fixed" && chore.assignees.length === 1 ? "round_robin" : chore.assignment,
    time: chore.due_time || "",
    points: chore.points,
    notify: chore.notify_before || 0,
    approval: chore.approval,
    hasCondition: chore.has_condition,
  };
  switch (chore.repeat) {
    case "none":
      form.freq = "once";
      form.date = (chore.due || todayIso).slice(0, 10);
      break;
    case "weekly":
      form.freq = "weekdays";
      form.weekdays = [...chore.weekdays];
      break;
    case "yearly":
      form.freq = "yearly";
      form.date = `${todayIso.slice(0, 4)}-${chore.dates[0]}`;
      form.extraDates = chore.dates.slice(1);
      break;
    case "after":
      form.freq = "after";
      form.after = chore.after || "";
      form.delay = chore.delay || 0;
      break;
    case "interval": {
      const preset = Object.entries(INTERVAL_PRESETS).find(
        ([, [every, unit]]) => every === chore.every && unit === chore.unit,
      );
      form.freq = preset && chore.from === "due" ? preset[0] : "custom";
      form.every = chore.every;
      form.unit = chore.unit;
      form.from = chore.from;
      break;
    }
  }
  return form;
}

/**
 * Formularen som et service-kald: { service, data } eller { error }.
 * Kun det, formularen viser, sendes; fx bevares en betingelse ved rettelse.
 */
export function formToService(form) {
  const name = (form.name || "").trim();
  if (!name) return { error: "err_name" };
  if (!form.assignees.length) return { error: "err_who" };
  const data = {
    name,
    assignees: [...form.assignees],
    points: Math.max(0, Number(form.points) || 0),
    assignment: form.assignees.length === 1 ? "fixed" : form.assignment,
    description: (form.description || "").trim() || null,
    due_time: form.time ? `${form.time}:00` : null,
    notify_before: Number(form.notify) ? { minutes: Number(form.notify) } : null,
    approval: form.approval,
  };
  switch (form.freq) {
    case "once":
      if (!form.date) return { error: "err_date" };
      Object.assign(data, { repeat: "none", due: `${form.date} ${form.time || "00:00"}:00` });
      break;
    case "weekdays":
      if (!form.weekdays.length) return { error: "err_days" };
      Object.assign(data, {
        repeat: "weekly",
        weekdays: WEEKDAY_KEYS.filter((d) => form.weekdays.includes(d)),
      });
      break;
    case "yearly":
      if (!form.date) return { error: "err_date" };
      Object.assign(data, { repeat: "yearly", dates: [form.date.slice(5), ...form.extraDates] });
      break;
    case "after":
      if (!form.after) return { error: "err_after" };
      Object.assign(data, {
        repeat: "after",
        after: form.after,
        delay: { minutes: Number(form.delay) || 0 },
      });
      break;
    case "custom":
      Object.assign(data, {
        repeat: "interval",
        every: Math.max(1, Math.round(Number(form.every) || 1)),
        unit: form.unit,
        from: form.from,
      });
      break;
    default: {
      const [every, unit] = INTERVAL_PRESETS[form.freq];
      Object.assign(data, { repeat: "interval", every, unit, from: "due" });
    }
  }
  return form.id
    ? { service: "update_chore", data: { chore: form.id, ...data } }
    : { service: "create_chore", data };
}

export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function storageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Privat vindue eller blokeret lager: valget huskes bare ikke.
  }
}

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 16px; }
  .header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
  .title { font-size: 1.25em; font-weight: 500; margin-right: auto; color: var(--primary-text-color); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    min-height: 36px; padding: 0 14px; border-radius: 18px; cursor: pointer;
    border: 1px solid var(--divider-color); background: none;
    color: var(--primary-text-color); font: inherit; display: inline-flex; align-items: center; gap: 6px;
  }
  .chip[aria-pressed="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .groups { display: grid; gap: 12px 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
  section, details { min-width: 0; }
  h3, summary {
    margin: 8px 0 4px; font-size: 0.95em; font-weight: 500; color: var(--secondary-text-color);
    text-transform: uppercase; letter-spacing: 0.04em; cursor: default; list-style: none;
  }
  summary { cursor: pointer; }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "▸ "; }
  details[open] summary::before { content: "▾ "; }
  .count { opacity: 0.7; }
  .overdue h3 { color: var(--error-color, #db4437); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  li {
    display: grid; grid-template-columns: 6px 1fr auto; align-items: stretch;
    border-radius: 10px; background: var(--secondary-background-color, rgba(127,127,127,0.08));
    overflow: hidden;
  }
  .bar { background: var(--person-color); }
  .main { padding: 8px 10px; min-width: 0; }
  .name { font-weight: 500; color: var(--primary-text-color); overflow-wrap: anywhere; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 0.85em; color: var(--secondary-text-color); margin-top: 2px; }
  .person { display: inline-flex; align-items: center; gap: 4px; }
  .flag { color: var(--warning-color, #ffa600); }
  .overdue .due { color: var(--error-color, #db4437); }
  .buttons { display: flex; align-items: center; gap: 4px; padding: 4px 6px 4px 0; }
  button.action {
    min-width: 48px; min-height: 48px; border-radius: 24px; border: none; cursor: pointer;
    background: none; color: var(--primary-text-color); font: inherit; padding: 0 10px;
  }
  button.check { font-size: 1.4em; border: 2px solid var(--person-color); color: var(--person-color); width: 48px; padding: 0; }
  button.check:active, button.action:active { background: var(--divider-color); }
  button.approve { background: var(--success-color, #43a047); color: #fff; }
  button.reject { background: var(--error-color, #db4437); color: #fff; }
  .menu { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 6px; padding: 0 10px 10px 16px; }
  .menu button { min-height: 40px; border-radius: 20px; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); padding: 0 12px; cursor: pointer; font: inherit; }
  .done .name { text-decoration: line-through; opacity: 0.7; }
  .board { margin-top: 12px; }
  .board ol { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; }
  .board li { grid-template-columns: 6px 1fr auto; padding: 0; }
  .board .score { padding: 8px 12px; font-weight: 500; color: var(--primary-text-color); }
  .board .pending { font-weight: 400; color: var(--secondary-text-color); font-size: 0.85em; margin-left: 6px; }
  .message { padding: 16px 0; color: var(--secondary-text-color); }
  .add {
    min-height: 40px; padding: 0 16px; border-radius: 20px; border: none; cursor: pointer;
    background: var(--primary-color); color: var(--text-primary-color, #fff); font: inherit; font-weight: 500;
  }
  .main[data-action="edit"] { cursor: pointer; }
  .form { display: grid; gap: 12px; max-width: 640px; }
  .form h2 { margin: 0; font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
  .field { display: grid; gap: 6px; }
  .label { font-size: 0.9em; color: var(--secondary-text-color); }
  .form input, .form textarea, .form select {
    box-sizing: border-box; width: 100%; min-height: 44px; padding: 8px 12px; border-radius: 8px;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent);
    color: var(--primary-text-color); font: inherit;
  }
  .form input.short { width: 80px; }
  .inline { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: var(--primary-text-color); }
  .form .chip { min-height: 44px; }
  .stepper { display: flex; align-items: center; gap: 12px; }
  .stepper .chip { width: 44px; justify-content: center; font-size: 1.2em; padding: 0; }
  .stepper .value { min-width: 2ch; text-align: center; font-size: 1.1em; color: var(--primary-text-color); }
  .link { justify-self: start; border: none; background: none; color: var(--primary-color); font: inherit; cursor: pointer; padding: 8px 0; min-height: 44px; }
  .note { font-size: 0.9em; color: var(--secondary-text-color); }
  .form-buttons { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 4px; }
  .form-buttons .spacer { flex: 1; }
  .form-buttons button { min-height: 48px; padding: 0 20px; border-radius: 24px; font: inherit; cursor: pointer; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); }
  .form-buttons .primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; font-weight: 500; }
  .form-buttons .danger { color: var(--error-color, #db4437); border-color: var(--error-color, #db4437); }
  .form-buttons button[disabled] { opacity: 0.6; cursor: default; }
  .outdated {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-bottom: 12px;
    padding: 8px 8px 8px 14px; border-radius: 10px; background: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }
  .outdated span { flex: 1; }
  .outdated button {
    min-height: 40px; padding: 0 16px; border-radius: 20px; border: none; cursor: pointer; font: inherit;
    font-weight: 500; background: var(--card-background-color, #fff); color: var(--primary-color);
  }
  .tabs { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 20px; overflow: hidden; }
  .tabs button {
    min-height: 40px; padding: 0 14px; border: none; background: none; cursor: pointer; font: inherit;
    color: var(--primary-text-color);
  }
  .tabs button[aria-selected="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .filters { margin-bottom: 8px; }
  .periods { margin-bottom: 8px; }
  .history { display: grid; gap: 8px; }
  .history-row .score, li .score { padding: 8px 12px; font-weight: 500; color: var(--primary-text-color); align-self: center; }
  .stats { display: grid; gap: 12px 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
  .stat-row { display: grid; grid-template-columns: minmax(80px, 140px) 1fr auto; align-items: center; gap: 10px; min-height: 36px; }
  .stat-name { color: var(--primary-text-color); overflow-wrap: anywhere; }
  .stat-bar { display: flex; height: 14px; border-radius: 7px; background: var(--secondary-background-color, rgba(127,127,127,0.12)); overflow: hidden; }
  .stat-bar span { display: block; height: 100%; }
  .stat-value { font-size: 0.9em; color: var(--secondary-text-color); white-space: nowrap; }
  .chore-row { grid-template-columns: minmax(80px, 160px) 1fr; }
  .count-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.85em; color: var(--primary-text-color); padding: 2px 8px; border-radius: 12px; border: 1px solid var(--divider-color); }
  .error { margin-top: 8px; padding: 8px 12px; border-radius: 8px; background: var(--error-color, #db4437); color: #fff; }
`;

if (typeof customElements !== "undefined" && !customElements.get(CARD_TYPE)) {
  class HusopgaverCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._data = null;
      this._openMenu = null;
      this._error = null;
      this._unsub = null;
      this._edit = null; // formularen, når en opgave oprettes eller rettes
      this._tab = "chores";
      this._period = 30;
      this._history = null;
      this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
      this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    }

    static getConfigElement() {
      return document.createElement(EDITOR_TYPE);
    }

    static getStubConfig() {
      return {};
    }

    setConfig(config) {
      if (!config || typeof config !== "object") throw new Error("Ugyldig konfiguration");
      const upcomingChanged = this._config && this._config.upcoming_days !== config.upcoming_days;
      this._config = {
        show_later: true,
        show_points: true,
        show_done: true,
        allow_edit: true,
        ...config,
      };
      const stored = storageGet(this._storageKey());
      this._filter = stored !== null ? stored || null : config.default_person || null;
      if (upcomingChanged) this._resubscribe();
      else if (this._hass && !this._unsub && this.isConnected) this._subscribe();
      this._render();
    }

    set hass(hass) {
      const languageChanged = !this._hass || this._hass.locale?.language !== hass.locale?.language;
      this._hass = hass;
      if (!this._unsub && this.isConnected) this._subscribe();
      if (languageChanged) this._render();
    }

    connectedCallback() {
      if (this._hass && !this._unsub) this._subscribe();
    }

    disconnectedCallback() {
      this._unsubscribe();
    }

    getCardSize() {
      return 6;
    }

    getGridOptions() {
      return { columns: 12, min_columns: 6, rows: "auto" };
    }

    _storageKey() {
      return `${CARD_TYPE}:filter:${this._config?.title || "default"}`;
    }

    async _subscribe() {
      // Kræver både hass og konfiguration; rækkefølgen, de sættes i, er ikke fast.
      if (!this._hass || !this._config || this._unsub) return;
      const message = { type: "husopgaver/subscribe" };
      if (this._config?.upcoming_days != null) message.upcoming_days = Number(this._config.upcoming_days);
      this._unsub = "pending";
      try {
        this._unsub = await this._hass.connection.subscribeMessage((data) => {
          this._data = data;
          // Under redigering tegnes kortet først om, når formularen lukkes,
          // så det, der skrives, ikke forsvinder.
          if (this._tab !== "chores") this._loadHistory();
          else if (!this._edit) this._render();
        }, message);
      } catch (err) {
        this._unsub = null;
        this._error = err?.message || String(err);
        this._render();
      }
    }

    _unsubscribe() {
      if (typeof this._unsub === "function") this._unsub();
      this._unsub = null;
    }

    _resubscribe() {
      this._unsubscribe();
      this._subscribe();
    }

    get _t() {
      return texts(this._hass?.locale?.language || this._hass?.language);
    }

    async _call(service, data) {
      this._error = null;
      this._openMenu = null;
      try {
        await this._hass.callService("husopgaver", service, data);
      } catch (err) {
        this._error = err?.message || String(err);
        this._render();
      }
    }

    _item(uid) {
      return this._data?.items.find((i) => i.uid === uid);
    }

    _onClick(ev) {
      const el = ev.target.closest("[data-action]");
      if (!el) return;
      const { action, uid, person } = el.dataset;
      const item = uid ? this._item(uid) : null;
      switch (action) {
        case "filter":
          this._filter = person || null;
          storageSet(this._storageKey(), this._filter ?? "");
          if (this._tab !== "chores") this._loadHistory();
          this._render();
          return;
        case "tab":
          this._tab = el.dataset.tab;
          this._edit = null;
          if (this._tab !== "chores") this._loadHistory();
          this._render();
          return;
        case "period":
          this._period = el.dataset.days === "all" ? null : Number(el.dataset.days);
          this._loadHistory();
          this._render();
          return;
        case "menu":
          this._openMenu = this._openMenu === uid ? null : uid;
          this._render();
          return;
        case "complete": {
          const credit = person || creditPerson(item, this._filter, this._data?.viewer?.person_id);
          if (credit === undefined) {
            // Ingen navn på og ingen at kreditere: spørg, hvem der gjorde det.
            this._pick = this._pick === uid ? null : uid;
            this._render();
            return;
          }
          this._pick = null;
          this._call("complete", { chore: item.chore_id, ...(credit ? { person: credit } : {}) });
          return;
        }
        case "approve":
          this._call("approve", { log_id: item.log_id });
          return;
        case "reject":
          this._call("reject", { log_id: item.log_id });
          return;
        case "undo":
          this._call("undo", item.log_id ? { log_id: item.log_id } : { chore: item.chore_id });
          return;
        case "skip":
          this._call("skip", { chore: item.chore_id, ...(item.each ? { person: item.key } : {}) });
          return;
        case "snooze":
          this._call("snooze", {
            chore: item.chore_id,
            duration: { hours: Number(el.dataset.hours) },
            ...(item.each ? { person: item.key } : {}),
          });
          return;
        case "reassign":
          this._call("reassign", { chore: item.chore_id, person });
          return;
        case "reload":
          window.location.reload();
          return;
        case "new":
          this._edit = newForm(this._today(), this._filter);
          this._render();
          return;
        case "edit": {
          const chore = this._data?.chores?.find((c) => c.id === el.dataset.chore);
          if (!chore || !this._config.allow_edit) return;
          this._edit = choreToForm(chore, this._today());
          this._openMenu = null;
          this._render();
          return;
        }
        default:
          if (this._edit) this._onFormClick(action, el.dataset);
      }
    }

    async _loadHistory() {
      const request = { type: "husopgaver/history" };
      if (this._period) request.days = this._period;
      if (this._filter) request.person = this._filter;
      const key = JSON.stringify(request);
      this._historyKey = key;
      try {
        const result = await this._hass.callWS(request);
        // Kun det seneste svar vises, hvis der er skiftet periode imens.
        if (this._historyKey === key) this._history = result;
      } catch (err) {
        this._error = err?.message || String(err);
      }
      this._render();
    }

    _today() {
      return localDay(new Date(), this._hass?.config?.time_zone);
    }

    _onInput(ev) {
      const field = ev.target?.dataset?.field;
      if (!this._edit || !field) return;
      this._edit[field] = ev.target.value;
    }

    _onFormClick(action, data) {
      const form = this._edit;
      switch (action) {
        case "toggle-person": {
          const list = form.assignees;
          form.assignees = list.includes(data.person)
            ? list.filter((p) => p !== data.person)
            : [...list, data.person];
          break;
        }
        case "toggle-day":
          form.weekdays = form.weekdays.includes(data.value)
            ? form.weekdays.filter((d) => d !== data.value)
            : [...form.weekdays, data.value];
          break;
        case "set":
          form[data.field] = data.value;
          break;
        case "points":
          form.points = Math.max(0, (Number(form.points) || 0) + Number(data.delta));
          break;
        case "more":
          form.more = !form.more;
          break;
        case "cancel":
          this._edit = null;
          break;
        case "save":
          this._save();
          return;
        case "delete":
          if (!form.confirmDelete) {
            form.confirmDelete = true;
            break;
          }
          this._delete();
          return;
        default:
          return;
      }
      if (action !== "delete") form.confirmDelete = false;
      this._render();
    }

    async _save() {
      const form = this._edit;
      const result = formToService(form);
      if (result.error) {
        form.error = this._t[result.error];
        this._render();
        return;
      }
      form.error = null;
      form.saving = true;
      this._render();
      try {
        await this._hass.callService("husopgaver", result.service, result.data);
        this._edit = null;
      } catch (err) {
        form.saving = false;
        form.error = err?.message || String(err);
      }
      this._render();
    }

    async _delete() {
      const form = this._edit;
      form.saving = true;
      this._render();
      try {
        await this._hass.callService("husopgaver", "delete_chore", { chore: form.id });
        this._edit = null;
      } catch (err) {
        form.saving = false;
        form.error = err?.message || String(err);
      }
      this._render();
    }

    _render() {
      if (!this._config) return;
      const t = this._t;
      const title = this._config.title ?? t.title;
      let body;
      if (!this._data) body = `<div class="message">${t.loading}</div>`;
      else if (this._data.loaded === false) body = `<div class="message">${t.not_loaded}</div>`;
      else if (this._edit) body = this._renderForm(t);
      else if (this._tab === "history") body = this._renderHistory(t);
      else if (this._tab === "stats") body = this._renderStats(t);
      else body = this._renderContent(t);
      const canAdd =
        this._config.allow_edit && this._data?.loaded && !this._edit && this._tab === "chores";
      const tabs =
        this._data?.loaded && !this._edit
          ? `<div class="tabs" role="tablist">${Object.entries(t.tabs)
              .map(
                ([tab, label]) =>
                  `<button role="tab" data-action="tab" data-tab="${tab}" aria-selected="${this._tab === tab}">${label}</button>`,
              )
              .join("")}</div>`
          : "";
      const addButton = canAdd
        ? `<button class="add" data-action="new">＋ ${t.new_chore}</button>`
        : "";
      const error = this._error ? `<div class="error" role="alert">${escapeHtml(this._error)}</div>` : "";
      const outdated = isOutdated(this._data?.version)
        ? `<div class="outdated" role="status"><span>${t.outdated}</span><button data-action="reload">${t.reload}</button></div>`
        : "";
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <ha-card>
          <div class="header">
            ${title ? `<div class="title">${escapeHtml(title)}</div>` : ""}
            ${tabs}
            ${addButton}
          </div>
          ${this._data?.persons && !this._edit ? `<div class="filters">${this._renderChips(t)}</div>` : ""}
          ${outdated}
          ${body}
          ${error}
        </ha-card>`;
    }

    _renderChips(t) {
      const persons = this._data.persons;
      const chip = (id, label, color) => `
        <button class="chip" data-action="filter" data-person="${escapeHtml(id)}"
          aria-pressed="${(this._filter || "") === id}">
          ${color ? `<span class="dot" style="background:${escapeHtml(color)}"></span>` : ""}
          ${escapeHtml(label)}
        </button>`;
      return `<div class="chips" role="group">${chip("", t.all)}${persons
        .filter((p) => p.active)
        .map((p) => chip(p.id, p.name, personColor(persons, p.id)))
        .join("")}</div>`;
    }

    _renderContent(t) {
      const { persons, items, viewer } = this._data;
      const visible = filterItems(items, this._filter).filter(
        (i) =>
          (this._config.show_later || i.group !== "later") &&
          (this._config.show_done || i.group !== "done"),
      );
      const groups = groupItems(visible);
      const sections = groups
        .map(([group, list]) => {
          const heading = `${t.groups[group]} <span class="count">${list.length}</span>`;
          const rows = `<ul>${list.map((i) => this._renderItem(i, t, persons, viewer)).join("")}</ul>`;
          if (group === "later" || group === "done") {
            return `<details class="${group}"><summary>${heading}</summary>${rows}</details>`;
          }
          return `<section class="${group}"><h3>${heading}</h3>${rows}</section>`;
        })
        .join("");
      const content = sections
        ? `<div class="groups">${sections}</div>`
        : `<div class="message">${t.empty}</div>`;
      return content + (this._config.show_points ? this._renderBoard(t, persons) : "");
    }

    _renderItem(item, t, persons, viewer) {
      const person = persons.find((p) => p.id === item.person_id);
      const color = personColor(persons, item.person_id);
      const tz = this._hass?.config?.time_zone;
      const locale = this._hass?.locale?.language || "da";
      const when =
        item.group === "done"
          ? `${t.done_at} ${dueText(item.due, true, new Date(), t, locale, tz)}`
          : dueText(item.due, item.has_time, new Date(), t, locale, tz);
      const flags = [
        item.group === "pending" ? `<span class="flag">${t.awaiting}</span>` : "",
        item.condition_unknown ? `<span class="flag">${t.condition_unknown}</span>` : "",
      ].join("");
      const uid = escapeHtml(item.uid);
      let buttons;
      if (item.group === "pending") {
        buttons = viewer?.can_approve
          ? `<button class="action approve" data-action="approve" data-uid="${uid}">${t.approve}</button>
             <button class="action reject" data-action="reject" data-uid="${uid}">${t.reject}</button>`
          : `<button class="action" data-action="undo" data-uid="${uid}" title="${t.undo}">↶</button>`;
      } else if (item.group === "done") {
        buttons = `<button class="action" data-action="undo" data-uid="${uid}" title="${t.undo}" aria-label="${t.undo}">↶</button>`;
      } else {
        buttons = `
          <button class="action" data-action="menu" data-uid="${uid}" aria-label="${t.more}" aria-expanded="${this._openMenu === item.uid}">⋮</button>
          <button class="action check" data-action="complete" data-uid="${uid}" aria-label="${t.complete}">✓</button>`;
      }
      let menu = this._openMenu === item.uid ? this._renderMenu(item, t, persons) : "";
      if (this._pick === item.uid) {
        const pool = persons.filter((p) => p.active && (item.assignees || []).includes(p.id));
        menu += `<div class="menu"><span class="label">${t.who_did_it}</span>${pool
          .map(
            (p) =>
              `<button data-action="complete" data-uid="${uid}" data-person="${escapeHtml(p.id)}"><span class="dot" style="background:${escapeHtml(personColor(persons, p.id))}"></span> ${escapeHtml(p.name)}</button>`,
          )
          .join("")}</div>`;
      }
      return `
        <li class="${item.group}" style="--person-color:${escapeHtml(color)}">
          <div class="bar"></div>
          <div class="main"${
            this._config.allow_edit ? ` data-action="edit" data-chore="${escapeHtml(item.chore_id)}"` : ""
          }>
            <div class="name">${escapeHtml(item.name)}</div>
            <div class="meta">
              <span class="person"><span class="dot" style="background:${escapeHtml(color)}"></span>${escapeHtml(
                person?.name ?? (item.open ? t.anyone : t.unassigned),
              )}</span>
              <span class="due">${escapeHtml(when)}</span>
              <span>${t.points(item.points)}</span>
              ${flags}
            </div>
          </div>
          <div class="buttons">${buttons}</div>
          ${menu}
        </li>`;
    }

    _renderMenu(item, t, persons) {
      const uid = escapeHtml(item.uid);
      const others = item.each || item.open
        ? []
        : persons.filter((p) => p.active && p.id !== item.person_id);
      return `<div class="menu">
        <button data-action="skip" data-uid="${uid}">${t.skip}</button>
        <button data-action="snooze" data-uid="${uid}" data-hours="1">${t.snooze_hour}</button>
        <button data-action="snooze" data-uid="${uid}" data-hours="24">${t.snooze_day}</button>
        ${others
          .map(
            (p) =>
              `<button data-action="reassign" data-uid="${uid}" data-person="${escapeHtml(p.id)}">${escapeHtml(t.give_to(p.name))}</button>`,
          )
          .join("")}
      </div>`;
    }

    _renderForm(t) {
      const form = this._edit;
      const persons = this._data.persons.filter((p) => p.active || form.assignees.includes(p.id));
      const chip = (action, label, pressed, extra = "") =>
        `<button type="button" class="chip" data-action="${action}" ${extra} aria-pressed="${pressed}">${label}</button>`;
      const set = (field, value, label) =>
        chip("set", escapeHtml(label), String(form[field]) === String(value), `data-field="${field}" data-value="${escapeHtml(value)}"`);
      const field = (label, content) => `<div class="field"><div class="label">${label}</div>${content}</div>`;

      const who = persons
        .map((p) =>
          chip(
            "toggle-person",
            `<span class="dot" style="background:${escapeHtml(personColor(this._data.persons, p.id))}"></span>${escapeHtml(p.name)}`,
            form.assignees.includes(p.id),
            `data-person="${escapeHtml(p.id)}"`,
          ),
        )
        .join("");
      const rotation =
        form.assignees.length > 1
          ? field(
              t.f_rotation,
              `<div class="chips">${Object.entries(t.rotation)
                .map(([value, label]) => set("assignment", value, label))
                .join("")}</div>`,
            )
          : "";
      const freq = `<div class="chips">${FREQUENCIES.map((f) => set("freq", f, t.freq[f])).join("")}</div>`;
      let freqDetails = "";
      if (form.freq === "weekdays") {
        freqDetails = `<div class="chips">${WEEKDAY_KEYS.map((d, i) =>
          chip("toggle-day", t.weekdays[i], form.weekdays.includes(d), `data-value="${d}"`),
        ).join("")}</div>`;
      } else if (form.freq === "once" || form.freq === "yearly") {
        freqDetails = field(t.f_date, `<input type="date" data-field="date" value="${escapeHtml(form.date)}">`);
      } else if (form.freq === "after") {
        const others = (this._data.chores || []).filter((c) => c.id !== form.id);
        freqDetails = `
          ${field(
            t.f_after,
            `<select data-field="after">
              <option value="">${t.choose}</option>
              ${others
                .map(
                  (c) =>
                    `<option value="${escapeHtml(c.id)}" ${c.id === form.after ? "selected" : ""}>${escapeHtml(c.name)}</option>`,
                )
                .join("")}
            </select>`,
          )}
          ${field(t.f_delay, `<div class="chips">${Object.entries(t.delays).map(([v, label]) => set("delay", v, label)).join("")}</div>`)}`;
      } else if (form.freq === "custom") {
        freqDetails = `
          <div class="inline">
            <span>${t.f_every}</span>
            <input type="number" min="1" max="365" data-field="every" value="${escapeHtml(form.every)}" class="short">
            <div class="chips">${Object.entries(t.units).map(([u, label]) => set("unit", u, label)).join("")}</div>
          </div>
          ${field(t.f_from, `<div class="chips">${Object.entries(t.from).map(([v, label]) => set("from", v, label)).join("")}</div>`)}`;
      }

      const more = form.more
        ? `
          ${field(t.f_description, `<textarea data-field="description" rows="2">${escapeHtml(form.description)}</textarea>`)}
          ${field(t.f_notify, `<div class="chips">${Object.entries(t.notify).map(([v, label]) => set("notify", v, label)).join("")}</div>`)}
          ${field(t.f_approval, `<div class="chips">${Object.entries(t.approval).map(([v, label]) => set("approval", v, label)).join("")}</div>`)}`
        : "";

      return `
        <form class="form" onsubmit="return false">
          <h2>${form.id ? t.edit_chore : t.new_chore}</h2>
          ${field(t.f_name, `<input type="text" data-field="name" value="${escapeHtml(form.name)}" autocomplete="off" enterkeyhint="done">`)}
          ${field(t.f_who, `<div class="chips">${who}</div>`)}
          ${rotation}
          ${field(t.f_freq, freq)}
          ${freqDetails}
          ${field(t.f_time, `<input type="time" data-field="time" value="${escapeHtml(form.time)}">`)}
          ${field(
            t.f_points,
            `<div class="stepper">
              <button type="button" class="chip" data-action="points" data-delta="-1" aria-label="-">−</button>
              <span class="value">${escapeHtml(form.points)}</span>
              <button type="button" class="chip" data-action="points" data-delta="1" aria-label="+">+</button>
            </div>`,
          )}
          <button type="button" class="link" data-action="more">${form.more ? t.fewer_options : t.more_options}</button>
          ${more}
          ${form.hasCondition ? `<div class="note">${t.has_condition}</div>` : ""}
          ${form.error ? `<div class="error" role="alert">${escapeHtml(form.error)}</div>` : ""}
          <div class="form-buttons">
            ${form.id ? `<button type="button" class="danger" data-action="delete" ${form.saving ? "disabled" : ""}>${form.confirmDelete ? t.confirm_delete : t.delete}</button>` : ""}
            <span class="spacer"></span>
            <button type="button" class="secondary" data-action="cancel">${t.cancel}</button>
            <button type="button" class="primary" data-action="save" ${form.saving ? "disabled" : ""}>${form.saving ? t.saving : t.save}</button>
          </div>
        </form>`;
    }

    _renderPeriods(t) {
      return `<div class="chips periods">${Object.entries(t.periods)
        .map(([days, label]) => {
          const value = days === "all" ? null : Number(days);
          return `<button class="chip" data-action="period" data-days="${days}" aria-pressed="${this._period === value}">${label}</button>`;
        })
        .join("")}</div>`;
    }

    _renderHistory(t) {
      const history = this._history;
      if (!history) return `${this._renderPeriods(t)}<div class="message">${t.loading}</div>`;
      const persons = this._data.persons;
      const tz = this._hass?.config?.time_zone;
      const locale = this._hass?.locale?.language || "da";
      if (!history.entries.length) {
        return `${this._renderPeriods(t)}<div class="message">${t.no_history}</div>`;
      }
      const today = this._today();
      const days = groupByDay(history.entries, tz)
        .map(([day, entries]) => {
          const rows = entries
            .map((e) => {
              const person = persons.find((p) => p.id === e.person_id);
              const color = personColor(persons, e.person_id);
              const time = clockTime(new Date(e.timestamp), tz);
              const name = e.action === "settled" ? t.actions.settled : e.chore_name ?? t.deleted_chore;
              const action = e.action === "settled" ? "" : t.actions[e.action];
              const credited = e.action === "completed" || e.action === "approved";
              return `<li class="history-row" style="--person-color:${escapeHtml(color)}">
                <div class="bar"></div>
                <div class="main">
                  <div class="name">${escapeHtml(name)}</div>
                  <div class="meta">
                    <span class="person"><span class="dot" style="background:${escapeHtml(color)}"></span>${escapeHtml(person?.name ?? t.unassigned)}</span>
                    <span>${escapeHtml(time)}</span>
                    ${action ? `<span class="${credited ? "" : "flag"}">${action}</span>` : ""}
                  </div>
                </div>
                <div class="score">${credited ? `+${e.points}` : ""}</div>
              </li>`;
            })
            .join("");
          return `<section><h3>${escapeHtml(dayLabel(day, today, t, locale))}</h3><ul>${rows}</ul></section>`;
        })
        .join("");
      return `${this._renderPeriods(t)}<div class="history">${days}</div>${
        history.truncated ? `<div class="message">${t.truncated}</div>` : ""
      }`;
    }

    _renderStats(t) {
      const history = this._history;
      if (!history) return `${this._renderPeriods(t)}<div class="message">${t.loading}</div>`;
      const persons = this._data.persons.filter(
        (p) => p.active || history.totals[p.id],
      );
      const shown = this._filter ? persons.filter((p) => p.id === this._filter) : persons;
      const locale = this._hass?.locale?.language || "da";
      const maxTotal = Math.max(1, ...shown.map((p) => history.totals[p.id]?.points || 0));
      const totals = shown
        .map((p) => {
          const total = history.totals[p.id] || { points: 0, count: 0 };
          const color = personColor(this._data.persons, p.id);
          return `<div class="stat-row">
            <span class="stat-name">${escapeHtml(p.name)}</span>
            <span class="stat-bar"><span style="width:${(total.points / maxTotal) * 100}%;background:${escapeHtml(color)}"></span></span>
            <span class="stat-value">${t.points(total.points)} · ${t.tasks(total.count)}</span>
          </div>`;
        })
        .join("");
      const maxBucket = Math.max(
        1,
        ...history.buckets.map((b) => Object.values(b.points).reduce((a, n) => a + n, 0)),
      );
      const buckets = history.buckets
        .slice()
        .reverse()
        .map((b) => {
          const sum = Object.values(b.points).reduce((a, n) => a + n, 0);
          const segments = shown
            .filter((p) => b.points[p.id])
            .map(
              (p) =>
                `<span title="${escapeHtml(p.name)}: ${b.points[p.id]}" style="width:${(b.points[p.id] / maxBucket) * 100}%;background:${escapeHtml(personColor(this._data.persons, p.id))}"></span>`,
            )
            .join("");
          return `<div class="stat-row">
            <span class="stat-name">${escapeHtml(bucketLabel(b.start, history.bucket, t, locale))}</span>
            <span class="stat-bar stacked">${segments}</span>
            <span class="stat-value">${sum}</span>
          </div>`;
        })
        .join("");
      const chores = history.chores
        .map(
          (c) => `<div class="stat-row chore-row">
            <span class="stat-name">${escapeHtml(c.chore_name ?? t.deleted_chore)}</span>
            <span class="chips">${shown
              .filter((p) => c.counts[p.id])
              .map(
                (p) =>
                  `<span class="count-chip"><span class="dot" style="background:${escapeHtml(personColor(this._data.persons, p.id))}"></span>${escapeHtml(p.name)} ${c.counts[p.id]}</span>`,
              )
              .join("")}</span>
          </div>`,
        )
        .join("");
      return `${this._renderPeriods(t)}
        <div class="stats">
          <section><h3>${t.totals}</h3>${totals}</section>
          <section><h3>${history.bucket === "week" ? t.per_week : t.per_month}</h3>${buckets}</section>
          ${chores ? `<section><h3>${t.who_does_what}</h3>${chores}</section>` : ""}
        </div>`;
    }

    _renderBoard(t, persons) {
      const board = pointsBoard(persons);
      if (!board.length) return "";
      return `<div class="board"><h3>${t.points_board}</h3><ol>${board
        .map(
          (p) => `<li style="--person-color:${escapeHtml(personColor(persons, p.id))}">
            <div class="bar"></div>
            <div class="main"><span class="name">${escapeHtml(p.name)}</span></div>
            <div class="score">${p.week_points}${
              p.pending_points ? `<span class="pending">${t.pending_points(p.pending_points)}</span>` : ""
            }</div>
          </li>`,
        )
        .join("")}</ol></div>`;
    }
  }

  class HusopgaverCardEditor extends HTMLElement {
    setConfig(config) {
      this._config = { ...config };
      this._render();
    }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) {
        hass
          .callWS({ type: "husopgaver/occurrences" })
          .then((data) => {
            this._persons = data.persons || [];
            this._render();
          })
          .catch(() => {
            this._persons = [];
            this._render();
          });
      }
      if (this._form) this._form.hass = hass;
    }

    _schema() {
      const da = texts(this._hass?.locale?.language) === TEXTS.da;
      return [
        { name: "title", selector: { text: {} } },
        {
          name: "default_person",
          selector: {
            select: {
              mode: "dropdown",
              options: [
                { value: "", label: da ? "Alle" : "All" },
                ...(this._persons || []).map((p) => ({ value: p.id, label: p.name })),
              ],
            },
          },
        },
        { name: "upcoming_days", selector: { number: { min: 0, max: 60, mode: "box" } } },
        { name: "show_later", selector: { boolean: {} } },
        { name: "show_done", selector: { boolean: {} } },
        { name: "show_points", selector: { boolean: {} } },
        { name: "allow_edit", selector: { boolean: {} } },
      ];
    }

    _label(name) {
      const da = String(this._hass?.locale?.language || "").startsWith("da");
      const labels = {
        title: da ? "Titel" : "Title",
        default_person: da ? "Standardfilter" : "Default filter",
        upcoming_days: da ? "Dage i Kommende (tom: integrationens indstilling)" : "Days in Upcoming (empty: integration setting)",
        show_later: da ? "Vis Senere" : "Show Later",
        show_done: da ? "Vis Udført i dag" : "Show Done today",
        show_points: da ? "Vis pointtavle" : "Show points board",
        allow_edit: da ? "Opret og ret opgaver fra kortet" : "Create and edit chores from the card",
      };
      return labels[name] || name;
    }

    _render() {
      if (!this._hass || !this._config) return;
      if (!this._form) {
        this._form = document.createElement("ha-form");
        this._form.computeLabel = (schema) => this._label(schema.name);
        this._form.addEventListener("value-changed", (ev) => {
          const config = { ...ev.detail.value };
          for (const key of ["default_person", "title"]) if (!config[key]) delete config[key];
          if (config.upcoming_days === "" || config.upcoming_days == null) delete config.upcoming_days;
          this._config = config;
          this.dispatchEvent(
            new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }),
          );
        });
        this.appendChild(this._form);
      }
      this._form.hass = this._hass;
      this._form.schema = this._schema();
      this._form.data = {
        show_later: true,
        show_done: true,
        show_points: true,
        allow_edit: true,
        ...this._config,
      };
    }
  }

  // Siden "Husopgaver" i sidemenuen: kortet på hele siden, uden dashboard-opsætning.
  class HusopgaverPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => {
        if (ev.target.closest?.("[data-action='menu-toggle']")) {
          this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
        }
      });
    }

    set hass(hass) {
      this._hass = hass;
      this._ensure();
      this._card.hass = hass;
    }

    set narrow(narrow) {
      this._narrow = narrow;
      if (this._card) this._renderToolbar();
    }

    set panel(panel) {
      this._panel = panel;
    }

    _ensure() {
      if (this._card) return;
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; min-height: 100vh; background: var(--primary-background-color); }
          .toolbar {
            display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px;
            background: var(--app-header-background-color, var(--primary-color));
            color: var(--app-header-text-color, var(--text-primary-color, #fff));
            font-size: 20px; position: sticky; top: 0; z-index: 2;
          }
          .toolbar button {
            width: 48px; height: 48px; border: none; border-radius: 24px; background: none;
            color: inherit; font-size: 22px; cursor: pointer;
          }
          .content { padding: 16px; max-width: 1400px; margin: 0 auto; box-sizing: border-box; }
        </style>
        <div class="toolbar"></div>
        <div class="content"></div>`;
      this._card = document.createElement(CARD_TYPE);
      // Titlen står i værktøjslinjen, så kortet viser den ikke igen.
      this._card.setConfig({ title: "" });
      this.shadowRoot.querySelector(".content").appendChild(this._card);
      this._renderToolbar();
    }

    _renderToolbar() {
      const toolbar = this.shadowRoot.querySelector(".toolbar");
      toolbar.innerHTML = `${
        this._narrow ? `<button data-action="menu-toggle" aria-label="Menu">☰</button>` : ""
      }<span>Husopgaver</span>`;
    }
  }

  customElements.define(PANEL_TYPE, HusopgaverPanel);
  customElements.define(CARD_TYPE, HusopgaverCard);
  customElements.define(EDITOR_TYPE, HusopgaverCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TYPE,
    name: "Husopgaver",
    description: "Familiens opgaver grupperet efter forfald, med point og godkendelse.",
    preview: true,
  });
}
