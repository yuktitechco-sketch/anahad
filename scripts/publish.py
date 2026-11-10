"""Publish today's approved post or reel to Instagram.

  python3 scripts/publish.py post            # today's picture post
  python3 scripts/publish.py reel            # today's reel
  python3 scripts/publish.py post --dry-run  # show what would happen, publish nothing
  python3 scripts/publish.py check           # test the access token
  python3 scripts/publish.py audio           # list trending Instagram audio (add --query "flute" to search)
  python3 scripts/publish.py refresh         # extend the access token (Instagram Login only)

Needs the environment variable IG_ACCESS_TOKEN. Media is fetched by Instagram from this repository's public files.
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

FACEBOOK = lib.CFG.get("login") == "facebook"  # Facebook Login is what allows Instagram audio to be attached
API = ("https://graph.facebook.com/" if FACEBOOK else "https://graph.instagram.com/") + lib.CFG["graph_api_version"]


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
    if FACEBOOK:  # the Instagram account hangs off the Facebook Page it is linked to
        pages = call("GET", "/me/accounts", fields="name,instagram_business_account{id,username}").get("data", [])
        linked = [p["instagram_business_account"] for p in pages if p.get("instagram_business_account")]
        want = os.environ.get("IG_USER_ID")
        for acc in linked:
            if not want or acc["id"] == want:
                return acc["id"], acc.get("username", "?")
        raise SystemExit("No Instagram professional account is linked to a Facebook Page this token can see.")
    me = call("GET", "/me", fields="user_id,username")
    return os.environ.get("IG_USER_ID") or me.get("user_id") or me["id"], me.get("username", "?")


def find_audio(query=None, count=10):
    """Instagram audio that may be attached to reels. With no search words, Instagram returns what is trending."""
    uid, _ = account()
    params = {"audio_type": lib.CFG["audio"].get("type", "music"), "user_id": uid}
    if query:
        params["search_query"] = query
    out = []
    for t in call("GET", "/ig_audio", **params).get("data", [])[:count]:
        out.append({"audio_id": str(t.get("audio_id") or t.get("id")), "title": t.get("title") or "?",
                    "artist": t.get("display_artist") or t.get("ig_username") or "",
                    "preview": t.get("on_platform_audio_preview_link") or t.get("download_url") or ""})
    return out


def can_pick_audio():
    return FACEBOOK and bool(os.environ.get("IG_ACCESS_TOKEN", "").strip())


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
    ap.add_argument("action", choices=["post", "reel", "check", "refresh", "audio"])
    ap.add_argument("--query")
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.action == "check":
        uid, name = account()
        print(f"Token works for @{name} (account id {uid}).")
        print("Publishing limit usage:", call("GET", f"/{uid}/content_publishing_limit"))
        return
    if a.action == "audio":
        for t in find_audio(a.query, 15):
            print(f"{t['audio_id']}  {t['title']} - {t['artist']}  {t['preview']}")
        return
    if a.action == "refresh":
        if FACEBOOK:
            print("Facebook Login tokens cannot be extended from here; replace the secret before it expires.")
            return
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
        if item.get("audio") and FACEBOOK:
            params["audio_configuration"] = json.dumps({"audio_id": item["audio"]["audio_id"], "video_volume": 0,
                                                        "audio_volume": lib.CFG["audio"].get("audio_volume", 100)})
            print(f"  audio: {item['audio']['title']} - {item['audio']['artist']}")
        else:
            print("  audio: none (silent)")
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
