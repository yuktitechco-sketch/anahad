"""Prepare a week of posts and reels for approval.

  python3 scripts/plan_week.py                       # next Monday to Sunday
  python3 scripts/plan_week.py --start 2026-11-12 --days 4
  python3 scripts/plan_week.py --swap 2026-11-18 reel   # replace one verse in a prepared week
  python3 scripts/plan_week.py --rerender 2026-11-16    # redraw a prepared week after editing the verse bank
  python3 scripts/plan_week.py --audio 2026-11-18 flute # different music for that day's reel ('none' for silent)

Writes queue/<date>/{post.jpg, reel.mp4, reel_cover.jpg, day.json}, reviews/<start>.jpg and data/state.json.
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import publish


def day_dir(date):
    return os.path.join(lib.ROOT, "queue", str(date))


def build(row, kind, date):
    d = day_dir(date)
    os.makedirs(d, exist_ok=True)
    if kind == "post":
        lib.render_post(row, os.path.join(d, "post.jpg"))
    else:
        lib.render_reel(row, os.path.join(d, "reel.mp4"), os.path.join(d, "reel_cover.jpg"))
    return {"id": row["ID"], "ref": f"{row['Author / Text']} {row['Reference']}", "meaning": row["English meaning"],
            "caption": lib.caption(row), "published": None}


def choose_audio(days_rows):
    """Give each reel its own trending Instagram track. days_rows: list of (day dict, verse row)."""
    cfg = lib.CFG["audio"]
    tracks = []
    if publish.can_pick_audio():
        try:
            tracks = publish.find_audio(None, 30)
        except SystemExit as e:
            print("Could not fetch trending audio:", e)
    else:
        print("No Facebook Login token here, so no audio was chosen; reels will go out silent.")
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
    """All prepared days that share a review sheet with this date."""
    for name in sorted(os.listdir(os.path.join(lib.ROOT, "reviews"))):
        if name.endswith(".json"):
            dates = json.load(open(os.path.join(lib.ROOT, "reviews", name)))
            if str(date) in dates:
                return name[:-5], dates
    raise SystemExit(f"{date} is not part of a prepared week.")


def finish(start, dates):
    days = [read_day(d) for d in dates]
    with open(os.path.join(lib.ROOT, "reviews", f"{start}.json"), "w") as f:
        json.dump(dates, f)
    lib.render_review(days, os.path.join(lib.ROOT, "reviews", f"{start}.jpg"))
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    manual = lib.CFG.get("publish_mode") == "manual"
    lines = [f"## Anahad: posts for {dates[0]} to {dates[-1]}", "",
             f"![review sheet](https://raw.githubusercontent.com/{repo}/week-{start}/reviews/{start}.jpg)", ""]
    if manual:
        lines += [f"**To approve:** press **Merge pull request**. Each day's picture, reel and caption then appear on the "
                  f"[posting page]({lib.CFG.get('posting_page', '')}) for you to post by hand with trending audio.", ""]
    else:
        lines += ["**To approve:** press **Merge pull request**. Each day's post then goes out by itself.", ""]
    lines += ["**To change something**, add a comment on this pull request:",
              "- `/swap 2026-11-18 reel` (or `post`) replaces that verse with a different one",
              "- `/render` redraws everything after you edit a meaning in `data/verse_bank.csv` on this branch"]
    if not manual:
        lines += ["- `/audio 2026-11-18 flute` puts different music on that day's reel, found by those search words",
                  "- `/audio 2026-11-18 none` makes that day's reel silent"]
    head = "| Date | Type | Verse | Reference | English meaning |" + ("" if manual else " Music |")
    lines += ["", head, "|---|---|---|---|---|" + ("" if manual else "---|")]
    for d in days:
        for kind in ("post", "reel"):
            x = d[kind]
            au = x.get("audio")
            music = "" if kind == "post" else "silent" if not au else (
                f"[{au['title']} - {au['artist']}]({au['preview']})" if au["preview"] else f"{au['title']} - {au['artist']}")
            lines.append(f"| {d['date']} | {kind} | {x['id']} | {x['ref']} | {x['meaning']} |" + ("" if manual else f" {music} |"))
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
    ap.add_argument("--swap", nargs=2, metavar=("DATE", "KIND"))
    ap.add_argument("--rerender", metavar="DATE")
    ap.add_argument("--audio", nargs="+", metavar=("DATE", "WORDS"))
    a = ap.parse_args()
    bank, state = lib.load_bank(), lib.load_state()

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
        print("Audio for", date, "is now", day["reel"]["audio"])
        return finish(start, dates)

    if a.swap:
        date, kind = datetime.date.fromisoformat(a.swap[0]), a.swap[1].lower()
        if kind not in ("post", "reel"):
            raise SystemExit("Say 'post' or 'reel'.")
        start, dates = week_of(date)
        day = read_day(date)
        if day[kind]["published"]:
            raise SystemExit("That one is already published.")
        old = day[kind]["id"]
        state["used"].pop(old, None)
        state["skipped"].append(old)
        row = lib.pick(bank, state, kind, date, [])
        audio = day[kind].get("audio")
        day[kind] = build(row, kind, date)
        if kind == "reel":
            day[kind]["audio"] = None if row["Religion / section"] in lib.CFG["audio"].get("no_music_sections", []) else audio
        state["used"][row["ID"]] = f"{date} {kind}"
        write_day(day)
        lib.save_state(state)
        print(f"Swapped {old} for {row['ID']}.")
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
    dates, reels = [], []
    for n in range(a.days):
        date = start + datetime.timedelta(days=n)
        if os.path.exists(os.path.join(day_dir(date), "day.json")):
            raise SystemExit(f"{date} is already prepared.")
        day = {"date": str(date)}
        for kind in ("post", "reel"):
            row = lib.pick(bank, state, kind, date, [])
            day[kind] = build(row, kind, date)
            state["used"][row["ID"]] = f"{date} {kind}"
            print(date, kind, row["ID"], day[kind]["ref"])
            if kind == "reel":
                reels.append((day, row))
        dates.append(str(date))
    if lib.CFG.get("publish_mode") == "manual":
        for day, _ in reels:
            day["reel"]["audio"] = None  # audio is added by hand in the Instagram app
    else:
        choose_audio(reels)
    for day, _ in reels:
        write_day(day)
    lib.save_state(state)
    finish(str(start), dates)


if __name__ == "__main__":
    main()
