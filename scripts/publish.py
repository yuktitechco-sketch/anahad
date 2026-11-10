"""Publish today's approved post or reel to Instagram.

  python3 scripts/publish.py post            # today's picture post
  python3 scripts/publish.py reel            # today's reel
  python3 scripts/publish.py post --dry-run  # show what would happen, publish nothing
  python3 scripts/publish.py check           # test the access token
  python3 scripts/publish.py refresh         # extend the access token for another 60 days

Needs the environment variable IG_ACCESS_TOKEN. Media is fetched by Instagram from this repository's public files.
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

API = "https://graph.instagram.com/" + lib.CFG["graph_api_version"]


def call(method, path, **params):
    token = os.environ["IG_ACCESS_TOKEN"].strip()
    url = path if path.startswith("http") else API + path
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Instagram refused the request ({e.code}): {e.read().decode(errors='replace')[:600]}")


def account():
    me = call("GET", "/me", fields="user_id,username")
    return os.environ.get("IG_USER_ID") or me.get("user_id") or me["id"], me.get("username", "?")


def wait_for_url(url):
    for _ in range(20):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(15)
    raise SystemExit(f"The file is not publicly reachable: {url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["post", "reel", "check", "refresh"])
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.action == "check":
        uid, name = account()
        print(f"Token works for @{name} (account id {uid}).")
        print("Publishing limit usage:", call("GET", f"/{uid}/content_publishing_limit"))
        return
    if a.action == "refresh":
        r = call("GET", "https://graph.instagram.com/refresh_access_token", grant_type="ig_refresh_token")
        print(f"Token extended; it now expires in {int(r.get('expires_in', 0)) // 86400} days.")
        return

    date = a.date or str(lib.today_local())
    path = os.path.join(lib.ROOT, "queue", date, "day.json")
    if not os.path.exists(path):
        print(f"Nothing approved for {date}; nothing to publish.")
        return
    day = json.load(open(path, encoding="utf-8"))
    item = day[a.action]
    if item["published"]:
        print(f"{date} {a.action} was already published ({item['published']}).")
        return

    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    base = os.environ.get("MEDIA_BASE_URL") or f"https://raw.githubusercontent.com/{repo}/main"
    base = f"{base.rstrip('/')}/queue/{date}"
    if a.action == "post":
        params = {"image_url": f"{base}/post.jpg", "caption": item["caption"]}
        media = params["image_url"]
    else:
        params = {"media_type": "REELS", "video_url": f"{base}/reel.mp4", "cover_url": f"{base}/reel_cover.jpg",
                  "share_to_feed": "true", "caption": item["caption"]}
        media = params["video_url"]
    print(f"{date} {a.action}: {item['id']} {item['ref']}\n  media: {media}")
    if a.dry_run:
        print("Dry run: nothing was published.\n--- caption ---\n" + item["caption"])
        return

    wait_for_url(media)
    uid, name = account()
    container = call("POST", f"/{uid}/media", **params)["id"]
    for _ in range(40):  # Instagram processes the file first; video takes a minute or two
        status = call("GET", f"/{container}", fields="status_code,status")
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Instagram could not process the file: {status}")
        time.sleep(15)
    else:
        raise SystemExit("Instagram was still processing the file after 10 minutes.")
    media_id = call("POST", f"/{uid}/media_publish", creation_id=container)["id"]
    item["published"] = media_id
    with open(path, "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Published to @{name}: media id {media_id}")


if __name__ == "__main__":
    main()
