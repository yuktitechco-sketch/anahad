# Anahad (अनहद)

Prepares a week of Instagram picture posts and reels from the verse bank, waits for your approval, then publishes one post and one reel every day.

## How it runs

| When | What happens |
|---|---|
| Friday 09:00 (India time) | Next week's 7 posts and 7 reels are prepared and an approval request (a "pull request") is opened with one review picture of the whole week. |
| When you press **Merge pull request** | That week is approved. |
| Every day 07:30 | The day's picture post is published. |
| Every day 19:00 | The day's reel is published. |

Nothing is published unless its week was merged. If you don't approve a week, the page simply stays quiet.

To change a prepared week, comment on the approval request (see also "Music on reels"):

- `/swap 2026-11-18 reel` (or `post`) replaces that verse with another and never offers the rejected one again.
- `/render` redraws the week after you edit a meaning in `data/verse_bank.csv` on that week's branch.

## One-time setup

1. **Repository.** Create a **public** repository and put these files in it. It must be public because Instagram downloads each picture and video from a public address. The access token is stored as a secret and is never in the files.
2. **Let the automation open approval requests.** Settings → Actions → General → Workflow permissions: choose "Read and write permissions" and tick "Allow GitHub Actions to create and approve pull requests".
3. **Facebook Page.** Link the Anahad Instagram account to a Facebook Page (Instagram → Settings → Accounts Centre, or the Page's settings). This is needed because only Meta's "Facebook Login" route can attach Instagram audio to a reel.
4. **Meta app and token.** At developers.facebook.com create an app (type Business) and add the Instagram product with Facebook Login. Generate a user access token with the permissions `instagram_basic`, `instagram_content_publish`, `pages_show_list` and `pages_read_engagement` (the Graph API Explorer can do this), then extend it to a long-lived token in the Access Token Debugger.
5. **Store the token.** Settings → Secrets and variables → Actions → New repository secret, named `IG_ACCESS_TOKEN`.
6. **Test.** Actions → "2. Publish to Instagram" → Run workflow → `check`. It should print the account name. Run it with `audio` to see what Instagram currently returns as trending.
7. **First week.** Actions → "1. Plan next week" → Run workflow. To start mid-week, fill in a start date and a number of days.

The long-lived token lasts about 60 days and cannot be extended automatically on this route. When publishing fails with a token error (GitHub emails you about failed runs), repeat step 4 and replace the secret.

## Music on reels

The reel video itself is silent. When a week is prepared, each reel is given one of the tracks Instagram returns as trending at that moment, a different track for each day, and the approval request lists the track next to each reel. Instagram adds the track when the reel is published.

- `/audio 2026-11-18 flute` replaces that day's track with the first result for those search words; `/audio 2026-11-18 none` makes it silent.
- Quran reels are silent by default (`no_music_sections` in `config.json`).
- Instagram only offers tracks cleared for use by outside tools, so the list can differ from the one in the Instagram app.
- If no track can be fetched, the reel goes out silent.

## What is in here

- `data/verse_bank.csv`: the verse bank. Only rows whose Status is "Matched to source text" are used. Hindi and Sanskrit verses are used only when their "Meaning style" is "Essence" (the message of the verse, not a word-for-word translation).
- `data/state.json`: which verses have been used or rejected.
- `config.json`: which tradition is used on which weekday, hashtags, labels, posting timezone.
- `scripts/plan_week.py`: picks verses and draws the posts and reels.
- `scripts/publish.py`: sends an approved post or reel to Instagram.
- `queue/<date>/`: the prepared files for each day; `reviews/`: the weekly review pictures.
- `.github/workflows/`: the three timers described above.

## Running it on your own computer

Needs Python 3, Node.js, Google Chrome and ffmpeg.

```
npm ci
python3 scripts/plan_week.py --start 2026-11-16 --days 7
python3 scripts/publish.py post --date 2026-11-16 --dry-run
```

## Notes

- Posting times are in `.github/workflows/publish.yml` (in UTC). GitHub can start scheduled runs some minutes late.
- If Instagram cannot fetch a file from `raw.githubusercontent.com`, turn on GitHub Pages for the main branch and set a repository variable `MEDIA_BASE_URL` to the Pages address (for example `https://yourname.github.io/anahad`).
- Verse texts come from open sources listed in the "Text source" column. The Hindi and English meanings are plain renderings written for this page; read them before approving.
