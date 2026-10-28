(() => {
  "use strict";

  const TZ = "America/Chicago";
  const PAGE = 150;
  const RANGES = [
    ["all", "Anytime"], ["today", "Today"], ["weekend", "This weekend"],
    ["7", "Next 7 days"], ["30", "Next 30 days"], ["90", "Next 3 months"],
  ];
  const SOURCE_LABELS = {
    sports: "Team schedules (MLB, NHL, NFL, NBA, WNBA, MLS, NWSL, college)",
    curated: "Festivals & seasonal calendar",
    ticketmaster: "Ticketmaster",
    venues: "Venue websites",
    seatgeek: "SeatGeek",
  };

  const $ = (id) => document.getElementById(id);
  const state = { cats: new Set(), subs: {}, q: "", range: "all", from: "", to: "", free: false, confirmed: false, shown: PAGE };
  let data = null;
  let today = "";

  // ------------------------------------------------------------------ dates

  function chicagoToday() {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    return parts; // en-CA formats as YYYY-MM-DD
  }
  const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
  const fmt = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => { const d = parse(s); d.setUTCDate(d.getUTCDate() + n); return fmt(d); };
  const dow = (s) => parse(s).getUTCDay();
  const dayDiff = (a, b) => Math.round((parse(b) - parse(a)) / 86400000);
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const short = (s) => `${MON[parse(s).getUTCMonth()]} ${parse(s).getUTCDate()}`;

  function rangeBounds() {
    if (state.from || state.to) return [state.from || today, state.to || "9999-12-31"];
    switch (state.range) {
      case "today": return [today, today];
      case "weekend": {
        const wd = dow(today); // Fri=5 Sat=6 Sun=0
        if (wd === 0) return [today, today];
        if (wd >= 5) return [today, addDays(today, 7 - wd)];
        return [addDays(today, 5 - wd), addDays(today, 7 - wd)];
      }
      case "7": return [today, addDays(today, 6)];
      case "30": return [today, addDays(today, 29)];
      case "90": return [today, addDays(today, 89)];
      default: return [today, "9999-12-31"];
    }
  }

  function time12(t) {
    if (!t) return "";
    let [h, m] = t.split(":").map(Number);
    const ap = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${String(m).padStart(2, "0")} ${ap}`;
  }

  // -------------------------------------------------------------- filtering

  const isFree = (e) => /free/i.test(e.price || "");
  const lastDay = (e) => e.end_date || e.date;

  function matchesBase(e) {
    const [lo, hi] = rangeBounds();
    if (lastDay(e) < lo || e.date > hi) return false;
    if (state.free && !isFree(e)) return false;
    if (state.confirmed && e.confirmed === false) return false;
    if (state.q) {
      const hay = `${e.title} ${e.venue || ""} ${e.neighborhood || ""} ${e.city || ""} ${e.subcategory || ""}`.toLowerCase();
      if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }
  function matchesCat(e) {
    if (state.cats.size && !state.cats.has(e.category)) return false;
    const subs = state.subs[e.category];
    if (subs && subs.size && !subs.has(e.subcategory || "Other")) return false;
    return true;
  }

  // -------------------------------------------------------------- rendering

  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "style") n.style.cssText = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid);
    return n;
  };
  const catVar = (c) => `--cat: var(--c-${c})`;

  function chip(label, pressed, onclick, { cat, count } = {}) {
    return el("button", { type: "button", class: "chip", "aria-pressed": String(pressed), style: cat ? catVar(cat) : null, onclick },
      cat ? el("span", { class: "dot" }) : null, label, count != null ? el("span", { class: "n" }, String(count)) : null);
  }

  function renderFilters(base) {
    const counts = {};
    const subCounts = {};
    for (const e of base) {
      counts[e.category] = (counts[e.category] || 0) + 1;
      const s = (subCounts[e.category] ||= {});
      const k = e.subcategory || "Other";
      s[k] = (s[k] || 0) + 1;
    }

    $("cat-chips").replaceChildren(
      chip("All", state.cats.size === 0, () => { state.cats.clear(); state.subs = {}; update(); }, { count: base.length }),
      ...Object.entries(data.categories).map(([key, label]) =>
        chip(label, state.cats.has(key), () => {
          state.cats.has(key) ? (state.cats.delete(key), delete state.subs[key]) : state.cats.add(key);
          update();
        }, { cat: key, count: counts[key] || 0 }))
    );

    // Sub-filters appear for each selected category; Sports is the main one.
    const groups = [...state.cats].filter((c) => subCounts[c] && Object.keys(subCounts[c]).length > 1);
    $("sub-section").hidden = groups.length === 0;
    $("sub-groups").replaceChildren(...groups.map((c) => {
      const chosen = state.subs[c] || new Set();
      const entries = Object.entries(subCounts[c]).sort((a, b) => (a[0] === "Other") - (b[0] === "Other") || b[1] - a[1]);
      return el("div", { class: "sub-group", style: catVar(c) },
        el("h3", {}, c === "sports" ? "Sport" : data.categories[c]),
        el("div", { class: "chips" },
          chip("All", chosen.size === 0, () => { delete state.subs[c]; update(); }),
          ...entries.map(([s, n]) => chip(s, chosen.has(s), () => {
            const set = (state.subs[c] ||= new Set());
            set.has(s) ? set.delete(s) : set.add(s);
            update();
          }, { count: n }))));
    }));

    $("range-chips").replaceChildren(...RANGES.map(([k, label]) =>
      chip(label, !state.from && !state.to && state.range === k, () => { state.range = k; state.from = state.to = ""; $("from").value = $("to").value = ""; update(); })));

    const active = state.cats.size + Object.values(state.subs).reduce((a, s) => a + s.size, 0)
      + (state.range !== "all" || state.from || state.to ? 1 : 0) + state.free + state.confirmed + (state.q ? 1 : 0);
    $("active-count").hidden = !active;
    $("active-count").textContent = active;
  }

  function eventCard(e) {
    const where = [e.venue, e.neighborhood || (e.city && e.city !== "Chicago" ? e.city : null)].filter(Boolean).join(" · ");
    let when = time12(e.time);
    if (e.end_date) when = when || "All day";
    const tags = [
      el("span", { class: "tag cat", style: catVar(e.category) }, e.subcategory || data.categories[e.category]),
    ];
    if (e.end_date) {
      tags.push(el("span", { class: "tag" }, e.performances
        ? `${e.performances} shows through ${short(e.end_date)}`
        : `${short(e.date)} – ${short(e.end_date)}`));
    }
    if (e.confirmed === false) tags.push(el("span", { class: "tag est", title: e.date_note || "Date not yet announced" }, "Estimated date"));
    if (e.price) tags.push(el("span", { class: `tag${isFree(e) ? " free" : ""}` }, e.price));

    const link = e.ticket_url || e.url;
    return el("article", { class: "ev" },
      el("div", { class: "ev-time" }, when || "TBA"),
      el("div", { class: "ev-main" },
        el("h3", { class: "ev-title" }, link ? el("a", { href: link, target: "_blank", rel: "noopener" }, e.title) : e.title),
        where ? el("div", { class: "ev-meta" }, where) : null,
        el("div", { class: "tags" }, tags)),
      el("div", { class: "ev-cta" }, link
        ? el("a", { href: link, target: "_blank", rel: "noopener", class: e.ticket_url ? null : "info" }, e.ticket_url ? "Tickets" : "Details")
        : null));
  }

  function dayLabel(key) {
    if (key === "now") return el("div", { class: "day-label now" }, el("div", { class: "num" }, "On now"), el("div", { class: "rel" }, "Already started"));
    const d = parse(key);
    const diff = dayDiff(today, key);
    const rel = diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : diff < 7 ? `In ${diff} days` : null;
    return el("div", { class: "day-label" },
      el("div", { class: "dow" }, DOW[d.getUTCDay()]),
      el("div", { class: "num" }, String(d.getUTCDate())),
      el("div", { class: "mon" }, `${MON[d.getUTCMonth()]}${d.getUTCFullYear() !== parse(today).getUTCFullYear() ? " " + d.getUTCFullYear() : ""}`),
      rel ? el("div", { class: "rel" }, rel) : null);
  }

  function renderList(list) {
    const [lo] = rangeBounds();
    const groups = new Map();
    for (const e of list.slice(0, state.shown)) {
      const key = e.date < lo ? "now" : e.date;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    }
    if (!list.length) {
      $("list").replaceChildren(el("div", { class: "empty" }, el("strong", {}, "Nothing matches"), "Try a wider date range or fewer filters."));
    } else {
      $("list").replaceChildren(...[...groups].map(([key, evs]) =>
        el("section", { class: "day", "aria-label": key === "now" ? "Happening now" : key }, dayLabel(key), el("div", { class: "events" }, evs.map(eventCard)))));
    }
    $("more").hidden = list.length <= state.shown;
    $("more").textContent = `Show more (${(list.length - state.shown).toLocaleString()} left)`;
  }

  function update({ keepPage = false } = {}) {
    if (!keepPage) state.shown = PAGE;
    const base = data.events.filter(matchesBase);
    const list = base.filter(matchesCat);
    // "On now" items (started before the window) first, then chronological.
    const [lo] = rangeBounds();
    list.sort((a, b) => (a.date < lo) === (b.date < lo) ? 0 : a.date < lo ? -1 : 1);
    renderFilters(base);
    renderList(list);
    const n = list.length;
    $("summary").textContent = `${n.toLocaleString()} event${n === 1 ? "" : "s"}${n !== data.events.length ? ` of ${data.events.length.toLocaleString()}` : ""}`;
    saveHash();
  }

  function renderFooter() {
    const updated = new Date(data.generated_at).toLocaleString("en-US", { timeZone: TZ, dateStyle: "medium", timeStyle: "short" });
    const items = Object.entries(data.sources || {}).map(([k, s]) =>
      el("li", {}, `${SOURCE_LABELS[k] || k}: ${s.status === "disabled" ? "not configured" : `${s.count.toLocaleString()} events${s.status !== "ok" ? ` (${s.status})` : ""}`}`));
    $("foot").replaceChildren(
      el("div", {}, `Updated ${updated} Central. Dates marked “Estimated” follow the event's usual schedule and haven't been announced yet. Confirm with the organizer before you go.`),
      el("ul", {}, items));
  }

  // ------------------------------------------------------------- URL state

  function saveHash() {
    const p = new URLSearchParams();
    if (state.cats.size) p.set("cat", [...state.cats].join(","));
    for (const [c, s] of Object.entries(state.subs)) if (s.size) p.set(`sub_${c}`, [...s].join(","));
    if (state.q) p.set("q", state.q);
    if (state.range !== "all") p.set("when", state.range);
    if (state.from) p.set("from", state.from);
    if (state.to) p.set("to", state.to);
    if (state.free) p.set("free", "1");
    if (state.confirmed) p.set("confirmed", "1");
    const s = p.toString();
    try { history.replaceState(null, "", s ? `#${s}` : location.pathname + location.search); } catch { /* sandboxed */ }
  }
  function loadHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    (p.get("cat") || "").split(",").filter((c) => c in data.categories).forEach((c) => state.cats.add(c));
    for (const [k, v] of p) if (k.startsWith("sub_")) state.subs[k.slice(4)] = new Set(v.split(","));
    state.q = (p.get("q") || "").toLowerCase();
    state.range = RANGES.some(([k]) => k === p.get("when")) ? p.get("when") : "all";
    state.from = p.get("from") || "";
    state.to = p.get("to") || "";
    state.free = p.get("free") === "1";
    state.confirmed = p.get("confirmed") === "1";
    $("q").value = state.q; $("from").value = state.from; $("to").value = state.to;
    $("free").checked = state.free; $("confirmed").checked = state.confirmed;
  }

  // ------------------------------------------------------------------ boot

  function wire() {
    let t;
    $("q").addEventListener("input", (ev) => { clearTimeout(t); t = setTimeout(() => { state.q = ev.target.value.trim().toLowerCase(); update(); }, 150); });
    $("from").addEventListener("change", (ev) => { state.from = ev.target.value; update(); });
    $("to").addEventListener("change", (ev) => { state.to = ev.target.value; update(); });
    $("free").addEventListener("change", (ev) => { state.free = ev.target.checked; update(); });
    $("confirmed").addEventListener("change", (ev) => { state.confirmed = ev.target.checked; update(); });
    $("more").addEventListener("click", () => { state.shown += PAGE; update({ keepPage: true }); });
    $("reset").addEventListener("click", () => {
      Object.assign(state, { cats: new Set(), subs: {}, q: "", range: "all", from: "", to: "", free: false, confirmed: false });
      $("q").value = $("from").value = $("to").value = ""; $("free").checked = $("confirmed").checked = false;
      update();
    });
    $("filters-toggle").addEventListener("click", () => {
      const open = $("filters").classList.toggle("open");
      $("filters-toggle").setAttribute("aria-expanded", String(open));
    });
  }

  async function boot() {
    today = chicagoToday();
    try {
      data = window.__EVENTS__ || await (await fetch("data/events.json", { cache: "no-cache" })).json();
    } catch (err) {
      $("summary").textContent = "Couldn't load the event list. Refresh the page to try again.";
      return;
    }
    data.events = data.events.filter((e) => lastDay(e) >= today);
    wire();
    loadHash();
    renderFooter();
    update();
  }

  boot();
})();
