// Run in the browser on a disneyworld.disney.go.com/calendars/ page.
// Reads each posted date the way the calendar itself does and returns a small JSON string.
// Each park is "hours|extended evening|ticketed event time|event number".
// Repeated days are listed once in rows; order gives each date's row, starting from today.
(async () => {
  const PARKS = { "Magic Kingdom": "mk", "EPCOT": "ep", "Disney's Hollywood Studios": "hs", "Disney's Animal Kingdom": "ak" };
  const short = t => t ? t.replace(/:00/g, "").replace(/ AM/g, "a").replace(/ PM/g, "p").replace(" to ", "–") : "";
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
  const addDays = (s, n) => new Date(new Date(s + "T00:00:00Z").getTime() + n * 864e5).toISOString().slice(0, 10);
  const events = [], rows = [], order = [], warnings = [];
  const eventId = n => { if (!events.includes(n)) events.push(n); return events.indexOf(n); };
  for (let i = 0; i <= 60; i++) {
    const iso = addDays(today, i);
    const r = await fetch(`/finder/api/v1/explorer-service/calendar/wdw/80007798;entityType=destination/${iso}/day/`, { credentials: "include" });
    if (!r.ok) { if (r.status !== 403 || i < 50) warnings.push(`${iso}: HTTP ${r.status}`); break; }
    const j = await r.json();
    const row = { f: [] };
    for (const l of Array.isArray(j.locations) ? j.locations : Object.values(j.locations)) {
      const p = PARKS[l.title];
      if (!p) continue;
      const g = {};
      for (const s of l.schedules || []) { const it = s.schedules && s.schedules[iso]; if (it && it.length) g[s.name] = it[0].time; }
      const ticketed = g["Special Ticketed Event"];
      const block = (l.events || []).find(x => (x.title || x.name) === "Events");
      let ev = "";
      for (const it of (block && block.data) || []) {
        const t = ((it.schedules || {})[iso] || [{}])[0].time;
        if (ticketed && t === ticketed && ev === "") ev = eventId(it.name);
        else row.f.push(eventId(it.name));
      }
      if (ticketed && ev === "") ev = eventId("Special ticketed event");
      const hours = short(g["Park Hours"]);
      if (g["Early Entry"] && short(g["Early Entry"]).split("–")[1] !== hours.split("–")[0]) warnings.push(`${iso} ${p}: Early Entry ${g["Early Entry"]} is not just before opening`);
      row[p] = [hours, short(g["Extended Evening Hours"]), short(ticketed), ev].join("|");
    }
    const key = JSON.stringify(row);
    let n = rows.findIndex(x => JSON.stringify(x) === key);
    if (n < 0) n = rows.push(row) - 1;
    order.push(n);
    await new Promise(res => setTimeout(res, 120));
  }
  return JSON.stringify({ today, events, rows, order, warnings });
})()
