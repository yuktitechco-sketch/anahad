"""Prepare a week of posts and reels for approval.

  python3 scripts/plan_week.py                            # next Monday to Sunday
  python3 scripts/plan_week.py --start 2026-11-12 --days 4
  python3 scripts/plan_week.py --start 2026-11-11 --days 5 --launch 10 --first V039
                                                          # 10 picture posts on the first day, the first being V039
  python3 scripts/plan_week.py --swap 2026-11-18 reel     # replace one verse ('post', 'reel' or 'extra3')
  python3 scripts/plan_week.py --rerender 2026-11-16      # redraw a prepared week after editing the verse bank

Writes queue/<date>/{post.jpg, reel.mp4, reel_cover.jpg, extra_NN.jpg, day.json}, reviews/<start>.{jpg,json}
and data/used/<start>.json.
"""
import argparse, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import publish

MANUAL = lib.CFG.get("publish_mode") == "manual"


def day_dir(date):
    return os.path.join(lib.ROOT, "queue", str(date))


def build(row, kind, date, file=None):
    """Draw one item. kind is 'post' or 'reel'; file names an extra picture post."""
    d = day_dir(date)
    os.makedirs(d, exist_ok=True)
    if kind == "post":
        lib.render_post(row, os.path.join(d, file or "post.jpg"))
    else:
        lib.render_reel(row, os.path.join(d, "reel.mp4"), os.path.join(d, "reel_cover.jpg"))
    item = {"id": row["ID"], "ref": f"{row['Author / Text']} {row['Reference']}", "meaning": row["English meaning"],
            "caption": lib.caption(row), "published": None}
    if file:
        item["file"] = file
    return item


def choose_audio(days_rows):
    """Automatic publishing only: give each reel its own trending Instagram track."""
    cfg = lib.CFG["audio"]
    tracks = []
    if publish.can_pick_audio():
        try:
            tracks = publish.find_audio(None, 30)
        except SystemExit as e:
            print("Could not fetch trending audio:", e)
    for day, row in days_rows:
        if row["Religion / section"] in cfg.get("no_music_sections", []) or not tracks:
            day["reel"]["audio"] = None
        else:
            day["reel"]["audio"] = tracks.pop(0)


def read_day(date):
    return json.load(open(os.path.join(day_dir(date), "day.json"), encoding="utf-8"))


def write_day(day):
    with open(os.path.join(day_dir(day["date"]), "day.json"), "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=1)
        f.write("\n")


def week_of(date):
    """The prepared week (start, list of dates) that this date belongs to."""
    for name in sorted(os.listdir(os.path.join(lib.ROOT, "reviews"))):
        if name.endswith(".json"):
            dates = json.load(open(os.path.join(lib.ROOT, "reviews", name)))
            if str(date) in dates:
                return name[:-5], dates
    raise SystemExit(f"{date} is not part of a prepared week.")


def items_of(day):
    """(label, item) for everything in a day, in posting order."""
    out = [("post", day["post"])]
    out += [(f"extra{n}", x) for n, x in enumerate(day.get("extras", []), start=1)]
    return out + [("reel", day["reel"])]


def finish(start, dates):
    days = [read_day(d) for d in dates]
    with open(os.path.join(lib.ROOT, "reviews", f"{start}.json"), "w") as f:
        json.dump(dates, f)
    lib.render_review(days, os.path.join(lib.ROOT, "reviews", f"{start}.jpg"))
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    lines = [f"## Anahad: posts for {dates[0]} to {dates[-1]}", "",
             f"![review sheet](https://raw.githubusercontent.com/{repo}/week-{start}/reviews/{start}.jpg)", ""]
    if MANUAL:
        lines += [f"**To approve:** press **Merge pull request**. Each day's pictures, reel and captions then appear on the "
                  f"[posting page]({lib.CFG.get('posting_page', '')}) for you to post by hand with trending audio.", ""]
    else:
        lines += ["**To approve:** press **Merge pull request**. Each day's post then goes out by itself.", ""]
    lines += ["**To change something**, add a comment on this pull request:",
              "- `/swap 2026-11-18 reel` replaces that verse with a different one (use `post`, `reel`, or `extra3` for the third extra post)",
              "- `/render` redraws everything after you edit a meaning in `data/verse_bank.csv` on this branch"]
    if not MANUAL:
        lines += ["- `/audio 2026-11-18 flute` puts different music on that day's reel, found by those search words",
                  "- `/audio 2026-11-18 none` makes that day's reel silent"]
    lines += ["", "| Date | Type | Verse | Reference | English meaning |" + ("" if MANUAL else " Music |"),
              "|---|---|---|---|---|" + ("" if MANUAL else "---|")]
    for d in days:
        for label, x in items_of(d):
            au = x.get("audio")
            music = "" if label != "reel" else "silent" if not au else f"{au['title']} - {au['artist']}"
            lines.append(f"| {d['date']} | {label} | {x['id']} | {x['ref']} | {x['meaning']} |" + ("" if MANUAL else f" {music} |"))
    out = os.environ.get("PR_BODY_FILE", os.path.join(lib.ROOT, ".pr_body.md"))
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"start={start}\nend={dates[-1]}\n")
    print(f"Prepared {len(days)} days from {dates[0]} to {dates[-1]}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--launch", type=int, default=1, help="number of picture posts on the first day")
    ap.add_argument("--first", help="verse ID to use for the very first post")
    ap.add_argument("--swap", nargs=2, metavar=("DATE", "WHICH"))
    ap.add_argument("--rerender", metavar="DATE")
    ap.add_argument("--audio", nargs="+", metavar=("DATE", "WORDS"))
    a = ap.parse_args()
    bank = lib.load_bank()

    if a.audio:
        date, words = a.audio[0], " ".join(a.audio[1:]).strip()
        start, dates = week_of(date)
        day = read_day(date)
        if not words or words.lower() == "none":
            day["reel"]["audio"] = None
        else:
            found = publish.find_audio(words, 1)
            if not found:
                raise SystemExit(f"Instagram returned no audio for '{words}'.")
            day["reel"]["audio"] = found[0]
        write_day(day)
        return finish(start, dates)

    if a.swap:
        date, which = datetime.date.fromisoformat(a.swap[0]), a.swap[1].lower()
        start, dates = week_of(date)
        rec = lib.load_week(start)
        day = read_day(date)
        m = re.fullmatch(r"extra(\d+)", which)
        if m:
            n = int(m.group(1)) - 1
            if not 0 <= n < len(day.get("extras", [])):
                raise SystemExit("There is no such extra post on that day.")
            old = day["extras"][n]
        elif which in ("post", "reel"):
            old = day[which]
        else:
            raise SystemExit("Say 'post', 'reel' or 'extra3'.")
        if old["published"]:
            raise SystemExit("That one is already published.")
        section = bank[old["id"]]["Religion / section"]
        rec["used"].pop(old["id"], None)
        rec["skipped"].append(old["id"])
        lib.save_week(start, rec)
        row = lib.pick(bank, lib.blocked_ids(), "reel" if which == "reel" else "post", date, section)
        if m:
            day["extras"][n] = build(row, "post", date, old["file"])
        else:
            audio = old.get("audio")
            day[which] = build(row, which, date)
            if which == "reel":
                day[which]["audio"] = audio
        rec["used"][row["ID"]] = f"{date} {which}"
        lib.save_week(start, rec)
        write_day(day)
        print(f"Swapped {old['id']} for {row['ID']}.")
        return finish(start, dates)

    if a.rerender:
        start, dates = week_of(a.rerender)
        for d in dates:
            day = read_day(d)
            for kind in ("post", "reel"):
                if not day[kind]["published"]:
                    audio = day[kind].get("audio")
                    day[kind] = build(bank[day[kind]["id"]], kind, d)
                    if kind == "reel":
                        day[kind]["audio"] = audio
            day_extras = day.get("extras", [])
            for n, x in enumerate(day_extras):
                if not x["published"]:
                    day_extras[n] = build(bank[x["id"]], "post", d, x["file"])
            write_day(day)
        return finish(start, dates)

    if a.start:
        start = datetime.date.fromisoformat(a.start)
    else:
        t = lib.today_local()
        start = t + datetime.timedelta(days=(7 - t.weekday()) % 7 or 7)  # next Monday
        if os.path.exists(os.path.join(day_dir(start), "day.json")):
            print(f"The week of {start} is already prepared; nothing to do.")
            return
    rec = {"used": {}, "skipped": []}
    blocked = lib.blocked_ids()

    def take(kind, date, label, section=None, forced=None):
        row = bank[forced] if forced else lib.pick(bank, blocked, kind, date, section)
        blocked.add(row["ID"])
        rec["used"][row["ID"]] = f"{date} {label}"
        print(date, label, row["ID"], row["Author / Text"], row["Reference"])
        return row

    dates, reels = [], []
    launch = lib.CFG.get("launch_sections", [])
    for n in range(a.days):
        date = start + datetime.timedelta(days=n)
        if os.path.exists(os.path.join(day_dir(date), "day.json")):
            raise SystemExit(f"{date} is already prepared.")
        first_day = n == 0 and (a.launch > 1 or a.first)
        day = {"date": str(date)}
        row = take("post", date, "post", launch[0] if first_day and launch else None, a.first if n == 0 else None)
        day["post"] = build(row, "post", date)
        if n == 0 and a.launch > 1:
            day["extras"] = []
            for k in range(1, a.launch):
                row = take("post", date, f"extra{k}", launch[k % len(launch)] if launch else None)
                day["extras"].append(build(row, "post", date, f"extra_{k:02d}.jpg"))
        row = take("reel", date, "reel")
        day["reel"] = build(row, "reel", date)
        day["reel"]["audio"] = None
        reels.append((day, row))
        dates.append(str(date))
    if not MANUAL:
        choose_audio(reels)
    for day, _ in reels:
        write_day(day)
    lib.save_week(str(start), rec)
    finish(str(start), dates)


if __name__ == "__main__":
    main()
