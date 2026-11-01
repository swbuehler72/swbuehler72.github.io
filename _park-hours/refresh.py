#!/usr/bin/env python3
"""Rebuild /park-hours/ from Disney's Hours & Events Calendar.

Disney's site refuses non-browser clients, so the data is read in a browser:
run extract.js on a disneyworld.disney.go.com/calendars/ page and save the JSON
string it returns to a file. This script then writes hours.json,
park-hours/index.html and the printable PDF.

  python3 _park-hours/refresh.py capture.json          update the files only
  python3 _park-hours/refresh.py capture.json --push   also commit and push to main

Exits non-zero without touching anything if the capture looks incomplete.
"""
import collections
import datetime as dt
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import zoneinfo

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
HOURS = HERE / "hours.json"
PAGE = REPO / "park-hours" / "index.html"
PDF = REPO / "park-hours" / "WDW-Park-Hours-60-Day.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MIN_DAYS = 55        # Disney posts about 60 days ahead; fewer than this means something is wrong

PARK_NAMES = {"mk": "Magic Kingdom", "ep": "EPCOT", "hs": "Hollywood Studios", "ak": "Animal Kingdom"}
EVENT_TAGS = {
    "Mickey's Very Merry Christmas Party": "Christmas Party",
    "Mickey's Not-So-Scary Halloween Party": "Halloween Party",
    "Disney Jollywood Nights": "Jollywood Nights",
}
FIXED_HOLIDAYS = {"01-01": "New Year's Day", "07-04": "Independence Day", "10-31": "Halloween", "11-11": "Veterans Day",
                  "12-24": "Christmas Eve", "12-25": "Christmas", "12-31": "New Year's Eve"}


def spoken(t):
    """7:30p–12a becomes 7:30 PM to midnight."""
    def word(x):
        return "midnight" if x == "12a" else x[:-1] + (" AM" if x[-1] == "a" else " PM")
    return " to ".join(word(x) for x in t.split("–"))


def long_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}"


def short_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def load_capture(path, today):
    """The file saved from extract.js, checked and expanded to one record per day."""
    cap = json.loads(pathlib.Path(path).read_text(encoding="utf8"))
    if len(cap["order"]) < MIN_DAYS:
        raise SystemExit(f"Only {len(cap['order'])} days captured, expected about 60. Nothing changed.")
    if cap["today"] != today.isoformat():
        raise SystemExit(f"Capture starts {cap['today']}, not today ({today}). Nothing changed.")
    names = cap["events"]
    days = {}
    for n, index in enumerate(cap["order"]):
        iso = (today + dt.timedelta(days=n)).isoformat()
        row = cap["rows"][index]
        if set(row) - {"f"} != set(PARK_NAMES):
            raise SystemExit(f"{iso}: expected all four parks, got {sorted(row)}. Nothing changed.")
        parks = {}
        for park in PARK_NAMES:
            hours, eeh, ticketed, event = row[park].split("|")
            parks[park] = {"hours": hours or None, "eeh": eeh or None, "ticketed": ticketed or None,
                           "event": names[int(event)] if event else None}
        days[iso] = {"parks": parks, "festivals": sorted({names[i] for i in row["f"]})}
    return days, cap.get("warnings", [])


def warnings_for(days):
    out = []
    for iso, day in days.items():
        for park, p in day["parks"].items():
            if not p["hours"]:
                out.append(f"{iso} {park}: no park hours listed")
            if p["event"] and p["event"] not in EVENT_TAGS:
                out.append(f"{iso} {park}: new ticketed event, shown by its full name: {p['event']}")
    return out


def page_table(days):
    """What the pages display, keyed by date."""
    table = {}
    for iso, day in days.items():
        row = {}
        for park, p in day["parks"].items():
            row[park] = p["hours"] or "See Disney"
            tags = []
            if p["event"]:
                tags.append(EVENT_TAGS.get(p["event"], p["event"]))
            if p["eeh"]:
                tags.append("EEH " + p["eeh"].replace("p–", "–", 1))
            if tags:
                row[park + "x"] = " · ".join(tags)
        table[iso] = row
    return table


def holidays(start, end):
    found = {}
    d = dt.date.fromisoformat(start)
    while d.isoformat() <= end:
        name = FIXED_HOLIDAYS.get(d.strftime("%m-%d"))
        if d.month == 11 and d.weekday() == 3 and 22 <= d.day <= 28:
            name = "Thanksgiving"
        if name:
            found[d.isoformat()] = name
        d += dt.timedelta(days=1)
    return found


def date_span(dates, last_posted):
    if len(dates) == 1:
        return f"on {long_date(dates[0])}"
    if dates[-1] == last_posted:
        return f"through at least {long_date(dates[-1])}"
    return f"through {long_date(dates[-1])}"


def event_notes(days, start, end, last_posted):
    """Sentences for the ticketed events and festivals inside start..end."""
    ticketed, festivals = collections.defaultdict(list), collections.defaultdict(list)
    for iso, day in days.items():
        for park, p in day["parks"].items():
            if p["event"]:
                ticketed[(p["event"], park, p["ticketed"])].append(iso)
        for name in day["festivals"]:
            festivals[name].append(iso)
    tick, fest = [], []
    for (name, park, times), dates in ticketed.items():
        if any(start <= x <= end for x in dates):
            tick.append(f"<strong>{html.escape(name)}</strong> runs {spoken(times)} at {PARK_NAMES[park]} {date_span(dates, last_posted)}.")
    for name, dates in festivals.items():
        if any(start <= x <= end for x in dates):
            fest.append(f"<strong>{html.escape(name)}</strong> runs {date_span(dates, last_posted)}.")
    return tick, fest


def fill(text, **values):
    for k, v in values.items():
        text = text.replace(f"__{k}__", v)
    return text


def build_web(days, checked):
    keys = sorted(days)
    tick, fest = event_notes(days, keys[0], keys[-1], keys[-1])
    items = tick + (["These events need a separate ticket."] if tick else []) + fest
    li = "\n".join(f"        <li>{x}</li>" for x in items) or "        <li>No ticketed events are posted right now.</li>"
    page = fill((HERE / "template-web.html").read_text(encoding="utf8"),
                DAYS=json.dumps(page_table(days), ensure_ascii=False, indent=2),
                HOLIDAYS=json.dumps(holidays(keys[0], keys[-1]), ensure_ascii=False),
                EVENT_ITEMS=li, CHECKED=checked)
    PAGE.write_text(page, encoding="utf8")


def build_pdf(days, checked):
    keys = sorted(days)
    first, last = dt.date.fromisoformat(keys[0]), dt.date.fromisoformat(keys[-1])
    sunday = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    weeks = (last - sunday).days // 7 + 1
    template = (HERE / "template-print.html").read_text(encoding="utf8")
    block = re.search(r"<!--PAGE-->\n(.*)<!--/PAGE-->\n", template, re.S)
    elig = "Early Entry is for eligible resort guests. EEH is for guests of Disney Deluxe Resorts and other select hotels."
    pages = ""
    for i in range(0, weeks, 5):
        a = sunday + dt.timedelta(weeks=i)
        b = a + dt.timedelta(days=34)
        lo, hi = max(a, first).isoformat(), min(b, last).isoformat()
        tick, fest = event_notes(days, lo, hi, keys[-1])
        note1 = " ".join(tick) + (" Ticketed events need a separate ticket." if tick else "")
        note2 = " ".join(fest + [elig] + ([f"Disney posts hours 60 days ahead, so this calendar ends on {long_date(keys[-1])}."] if hi == keys[-1] else []))
        pages += fill(block.group(1), TITLE=f"{short_date(lo)} – {short_date(hi)}, {hi[:4]}", FROM=a.isoformat(), TO=b.isoformat(),
                      NOTES1=note1, NOTES2=note2)
    out = template[:block.start()] + pages + template[block.end():]
    out = fill(out, DAYS=json.dumps(page_table(days), ensure_ascii=False),
               HOLIDAYS=json.dumps(holidays(keys[0], keys[-1]), ensure_ascii=False), CHECKED=checked)
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "print.html"
        src.write_text(out, encoding="utf8")
        target = pathlib.Path(tmp) / "out.pdf"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000",
                        f"--user-data-dir={tmp}/profile", f"--print-to-pdf={target}", f"file://{src}"],
                       check=True, capture_output=True, timeout=120)
        raw = target.read_bytes()
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000",
                              f"--user-data-dir={tmp}/profile", "--dump-dom", f"file://{src}"],
                             check=True, capture_output=True, text=True, timeout=120).stdout
        crowded = re.search(r'data-overflow="(\d+)"', dom)
        if not crowded or crowded.group(1) != "0":
            print(f"WARNING: PDF has {crowded.group(1) if crowded else 'an unknown number of'} crowded day cells. Check the layout.")
        count = len(re.findall(rb"/Type\s*/Page[^s]", raw))
        if count != 2:
            raise SystemExit(f"PDF came out at {count} pages, expected 2. Nothing changed.")
        PDF.write_bytes(raw)


def describe_changes(old, new):
    lines = []
    old_t, new_t = page_table(old), page_table(new)
    for iso in sorted(new_t):
        if iso not in old_t:
            lines.append(f"new date {iso}")
        elif old_t[iso] != new_t[iso]:
            for k in sorted(set(old_t[iso]) | set(new_t[iso])):
                if old_t[iso].get(k) != new_t[iso].get(k):
                    lines.append(f"{iso} {k}: {old_t[iso].get(k)} -> {new_t[iso].get(k)}")
    return lines


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout


def push(today_iso):
    paths = ["_park-hours", "park-hours"]
    git("add", *paths)
    if not git("diff", "--cached", "--name-only", "--", *paths).strip():
        print("Nothing to commit.")
        return
    git("commit", "-m", f"Refresh park hours for {today_iso}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", "--", *paths)
    git("pull", "--rebase", "--autostash", "origin", "main")
    git("push", "origin", "main")
    print("Pushed to main:", git("rev-parse", "--short", "HEAD").strip())


def main():
    args = [a for a in sys.argv[1:] if a != "--push"]
    pushing = "--push" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    today = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    if pushing:
        if git("rev-parse", "--abbrev-ref", "HEAD").strip() != "main":
            raise SystemExit("Not on main. Nothing changed.")
        if git("status", "--porcelain", "--", "_park-hours", "park-hours").strip():
            raise SystemExit("Uncommitted changes in the park hours files. Nothing changed.")
        git("pull", "--ff-only", "--autostash", "origin", "main")
    days, capture_warnings = load_capture(args[0], today)
    old = json.loads(HOURS.read_text(encoding="utf8"))["days"] if HOURS.exists() else {}
    changes = describe_changes(old, days)
    if not changes and set(old) == set(days):
        print("No changes to posted hours or dates. Nothing to do.")
        return
    checked = f"{today.strftime('%B')} {today.day}, {today.year}"
    build_web(days, checked)
    build_pdf(days, checked)
    HOURS.write_text(json.dumps({"checked": today.isoformat(), "days": days}, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
    keys = sorted(days)
    print(f"Posted {keys[0]} to {keys[-1]} ({len(keys)} days).")
    print("Changes:" if changes else "No changes to posted hours.")
    for line in changes:
        print("  " + line)
    for line in capture_warnings + warnings_for(days):
        print("WARNING:", line)
    if pushing:
        push(today.isoformat())


if __name__ == "__main__":
    main()
