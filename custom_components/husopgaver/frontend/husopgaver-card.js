// Husopgaver: dashboardkort til familiens opgaver.
// Rent web component uden byggetrin, CDN eller eksterne biblioteker.
// Data kommer fra websocket-abonnementet husopgaver/subscribe, færdiggrupperet.

const CARD_TYPE = "husopgaver-card";
const EDITOR_TYPE = "husopgaver-card-editor";

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
  },
  en: {
    title: "Chores",
    all: "All",
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
  },
};

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
  // Altid 24-timers HH:MM, uanset hvilke locale-data browseren har.
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(due);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${day} ${get("hour")}:${get("minute")}`;
}

/**
 * Hvem en afkrydsning fra kortet krediteres: den valgte person i filteret,
 * ellers forekomstens person ved "alle", ellers den tildelte (null).
 */
export function creditPerson(item, filterId) {
  if (filterId) return filterId;
  if (item.each) return item.key;
  return null;
}

/** Opgaverne for den valgte person, eller alle. */
export function filterItems(items, filterId) {
  if (!filterId) return items;
  return items.filter((item) => item.person_id === filterId);
}

/** Grupper i fast rækkefølge; tomme grupper udelades. */
export function groupItems(items) {
  const groups = new Map(GROUP_ORDER.map((g) => [g, []]));
  for (const item of items) {
    if (groups.has(item.group)) groups.get(item.group).push(item);
  }
  return GROUP_ORDER.filter((g) => groups.get(g).length).map((g) => [g, groups.get(g)]);
}

/** Pointtavlen: aktive personer med flest point først. */
export function pointsBoard(persons) {
  return persons
    .filter((p) => p.active)
    .slice()
    .sort((a, b) => b.week_points - a.week_points || a.name.localeCompare(b.name));
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
      this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
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
      this._config = { show_later: true, show_points: true, show_done: true, ...config };
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
          this._render();
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
          this._render();
          return;
        case "menu":
          this._openMenu = this._openMenu === uid ? null : uid;
          this._render();
          return;
        case "complete": {
          const credit = creditPerson(item, this._filter);
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
      }
    }

    _render() {
      if (!this._config) return;
      const t = this._t;
      const title = this._config.title ?? t.title;
      let body;
      if (!this._data) body = `<div class="message">${t.loading}</div>`;
      else if (this._data.loaded === false) body = `<div class="message">${t.not_loaded}</div>`;
      else body = this._renderContent(t);
      const error = this._error ? `<div class="error" role="alert">${escapeHtml(this._error)}</div>` : "";
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <ha-card>
          <div class="header">
            ${title ? `<div class="title">${escapeHtml(title)}</div>` : ""}
            ${this._data?.persons ? this._renderChips(t) : ""}
          </div>
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
      const menu = this._openMenu === item.uid ? this._renderMenu(item, t, persons) : "";
      return `
        <li class="${item.group}" style="--person-color:${escapeHtml(color)}">
          <div class="bar"></div>
          <div class="main">
            <div class="name">${escapeHtml(item.name)}</div>
            <div class="meta">
              <span class="person"><span class="dot" style="background:${escapeHtml(color)}"></span>${escapeHtml(person?.name ?? t.unassigned)}</span>
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
      const others = item.each
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
      this._form.data = { show_later: true, show_done: true, show_points: true, ...this._config };
    }
  }

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
