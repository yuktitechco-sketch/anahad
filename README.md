# Anahad (अनहद)

Prepares a week of Instagram picture posts and reels from the verse bank, waits for your approval, then puts each day's files on a phone-friendly page so you can post them by hand with trending audio.

## How it runs

| When | What happens |
|---|---|
| Friday 09:00 (India time) | Next week's 7 posts and 7 reels are prepared and an approval request (a "pull request") is opened with one review picture of the whole week. |
| When you press **Merge pull request** | That week is approved and its days appear on the posting page. |
| Every day 07:00 | A reminder comment is added to the "Daily posting reminders" issue; GitHub emails it to you with a link to the day's page. |
| When you post | On the posting page: copy the caption, share or save the picture and the reel, add trending audio in Instagram, paste the caption, post. |

Posting page: https://yuktitechco-sketch.github.io/anahad/

To change a prepared week, comment on the approval request:

- `/swap 2026-11-18 reel` (or `post`) replaces that verse with another and never offers the rejected one again.
- `/render` redraws the week after you edit a meaning in `data/verse_bank.csv` on that week's branch.

## One-time setup

1. **Let the automation open approval requests.** Settings → Actions → General → Workflow permissions: "Read and write permissions", and tick "Allow GitHub Actions to create and approve pull requests".
2. **Turn on the posting page.** Settings → Pages → Source "Deploy from a branch" → branch `main`, folder `/ (root)` → Save.
3. **First week.** Actions → "1. Plan next week" → Run workflow. To start mid-week, fill in a start date and a number of days.

No Meta app or access token is needed while posting is done by hand.

## What is in here

- `data/verse_bank.csv`: the verse bank. Only rows whose Status is "Matched to source text" are used. Hindi and Sanskrit verses are used only when their "Meaning style" is "Essence" (the message of the verse, not a word-for-word translation).
- `data/state.json`: which verses have been used or rejected.
- `config.json`: which tradition is used on which weekday, hashtags, labels, timezone, and `publish_mode`.
- `index.html`: the posting page.
- `scripts/plan_week.py`: picks verses and draws the posts and reels. Reels are silent; the audio is added in Instagram.
- `queue/<date>/`: the prepared files for each day; `reviews/`: the weekly review pictures.
- `.github/workflows/`: the timers described above.

## Running it on your own computer

Needs Python 3, Node.js, Google Chrome and ffmpeg.

```
npm ci
python3 scripts/plan_week.py --start 2026-11-16 --days 7
```

## Going back to automatic publishing

`scripts/publish.py` and the workflow "4. Automatic publishing (not in use)" can publish through Meta's API. To use them: set `publish_mode` to `"auto"` in `config.json`, store a Meta access token as the repository secret `IG_ACCESS_TOKEN`, and add a schedule to `.github/workflows/publish.yml`. With `"login": "facebook"` (needs a Facebook Page linked to the Instagram account) the system can attach trending Instagram audio to reels itself; with `"login": "instagram"` no Page is needed but reels go out silent.

## Notes

- Verse texts come from open sources listed in the "Text source" column. The Hindi and English meanings are written for this page; read them before approving.
- GitHub can start scheduled runs some minutes late.
