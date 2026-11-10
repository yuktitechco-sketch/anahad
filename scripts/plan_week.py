"""Prepare a week of posts and reels for approval.

  python3 scripts/plan_week.py                       # next Monday to Sunday
  python3 scripts/plan_week.py --start 2026-11-12 --days 4
  python3 scripts/plan_week.py --swap 2026-11-18 reel   # replace one verse in a prepared week
  python3 scripts/plan_week.py --rerender 2026-11-16    # redraw a prepared week after editing the verse bank

Writes queue/<date>/{post.jpg, reel.mp4, reel_cover.jpg, day.json}, reviews/<start>.jpg and data/state.json.
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


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
    lines = [f"## Anahad: posts for {dates[0]} to {dates[-1]}", "",
             f"![review sheet](https://raw.githubusercontent.com/{repo}/week-{start}/reviews/{start}.jpg)", "",
             "**To approve:** press **Merge pull request**. Each day's post then goes out by itself.", "",
             "**To change something**, add a comment on this pull request:",
             "- `/swap 2026-11-18 reel` (or `post`) replaces that verse with a different one",
             "- `/render` redraws everything after you edit a meaning in `data/verse_bank.csv` on this branch", "",
             "| Date | Type | Verse | Reference | English meaning |", "|---|---|---|---|---|"]
    for d in days:
        for kind in ("post", "reel"):
            x = d[kind]
            lines.append(f"| {d['date']} | {kind} | {x['id']} | {x['ref']} | {x['meaning']} |")
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
    a = ap.parse_args()
    bank, state = lib.load_bank(), lib.load_state()

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
        day[kind] = build(row, kind, date)
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
                    day[kind] = build(bank[day[kind]["id"]], kind, d)
            write_day(day)
        return finish(start, dates)

    if a.start:
        start = datetime.date.fromisoformat(a.start)
    else:
        t = lib.today_local()
        start = t + datetime.timedelta(days=(7 - t.weekday()) % 7 or 7)  # next Monday
    dates = []
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
        write_day(day)
        dates.append(str(date))
    lib.save_state(state)
    finish(str(start), dates)


if __name__ == "__main__":
    main()
