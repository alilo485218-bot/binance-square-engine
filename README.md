# Binance Square — Content Engine

> Smart Posting Assistant aimed at **Top 10 Binance Square (Write to Earn)**.
> Not an auto-poster. Human-in-the-loop. Optimized for the **first 30–60 minutes** after publish, where Top-10 ranking is decided.

---

## 1. Philosophy

| Principle | Why it matters |
|---|---|
| **Smart assistant, not auto-poster** | Binance Square has no public posting API for individuals. Auto-posters get throttled or banned. |
| **Human in the loop** | You approve every post and image before publish. Quality > quantity. |
| **First hour > everything** | Engagement velocity in the first 30–60 min is the strongest ranking signal. The Engagement Assistant is built around this. |
| **Cashtag → click → trade** | Every post is engineered around a `$CASHTAG` + a binary CTA question to maximize clicks and replies. |
| **Simple, fast, modular** | Six small modules, one Flask UI. ~1000 LOC. Add an LLM provider, swap the image style, change the prompts — all isolated. |

---

## 2. Architecture

```
                        +------------------------+
                        |     Flask Web UI       |   (single page, vanilla JS)
                        |    (templates/, app.py)|
                        +-----------+------------+
                                    |
        +---------------------------+----------------------------+
        |              |             |          |               |
        v              v             v          v               v
  Trend Engine   Content Gen.   Smart Selector  Image Gen.   Engagement
  (CoinGecko +   (3 prompts:    (scoring 0-100, (Pillow,     Assistant
   RSS news)      analysis,      ranks posts)    1080x1080,   (replies +
                  news, debate)                  red/green)   reminders)
        |              |             |          |               |
        +-------+------+-------------+----------+---------------+
                |                                              ^
                v                                              |
            data/ (snapshot.json, posts.json)         Scheduler (APScheduler,
                                                     UTC, post + ping reminders)
```

**Data flow (one click cycle):**

1. **`POST /api/trends`** → Trend Engine pulls CoinGecko trending + top movers + RSS news → cached to `data/snapshot.json`.
2. **`POST /api/generate`** → Content Generator turns each signal into a post (analysis / debate / news) → Smart Selector scores them → cached to `data/posts.json`.
3. **`POST /api/image`** → Image Hook Generator renders a 1080×1080 hook image using the post's `hook_keywords` and direction-aware palette.
4. You **edit** in the textarea, **copy** to Binance Square, **publish manually**.
5. **`POST /api/schedule`** queues a UTC reminder via APScheduler. After publish you fire **`/api/reply`** for incoming comments and follow the **first-hour reminder plan**.

---

## 3. Modules

### 3.1 Trend Engine — `modules/trend_engine.py`
- `fetch_trending_coins()` → CoinGecko `/search/trending`.
- `fetch_top_movers()` → CoinGecko `/coins/markets` (sorted by |24h change|).
- `fetch_news()` → RSS from CoinTelegraph + CoinDesk.
- `get_full_snapshot()` → deduped union of all signals.
- **No API keys required.**

### 3.2 Content Generator — `modules/content_generator.py`
Three prompt types in `prompts/*.txt`:

| Prompt | Goal | Hook style |
|---|---|---|
| `analysis.txt` | Technical/on-chain take | "BTC is at a decision point." |
| `news.txt`     | React to a headline      | The news in 6 words |
| `debate.txt`   | Polarizing CTA           | "$XYZ at this level is a trap." |

Every prompt **forces JSON output** with this schema:
```json
{
  "type": "analysis|news|debate",
  "coin": "BTC",
  "cashtag": "$BTC",
  "hook": "≤ 8 words",
  "hook_keywords": ["BTC", "DECISION", "POINT"],
  "body": "≤ 120 words, ends with CTA question",
  "direction": "up|down|flat",
  "cta": "Long or short here?"
}
```

If `OPENAI_API_KEY` is missing, falls back to deterministic templates so the rest of the pipeline still runs.

### 3.3 Smart Selector — `modules/smart_selector.py`
Score (0–100):
- `hook_strength` (0–25) — ≤ 8 words, punchy ending, not a generic intro.
- `has_trend_coin` (0–20) — BTC/ETH/SOL or a trending symbol.
- `has_question` (0–15) — `?` in the **last** line.
- `length_ok` (0–15) — 40–120 words.
- `has_cashtag` (0–10) — `$XYZ` regex.
- `has_number` (0–10) — concrete number in the body.
- `has_directional` (0–5) — clear `up`/`down` stance.

The UI sorts posts best-first and shows the breakdown so you learn what works.

### 3.4 Image Hook Generator — `modules/image_generator.py`
- 1080×1080 PNG.
- Direction-aware palette: green gradient for `up`, red for `down`, neutral gold for `flat`.
- Big centered headline using `hook_keywords` (3–5 words, uppercase).
- Cashtag top-left, 24h change top-right with ▲/▼.
- Type tag bottom-left ("ANALYSIS" / "DEBATE" / "NEWS").
- No external assets — uses DejaVu Sans (preinstalled on Linux/CI) with system-font fallback.

### 3.5 Scheduler — `modules/scheduler.py`
- APScheduler `BackgroundScheduler` in UTC.
- `schedule_post_reminder(post_id, fire_at_utc)` queues a reminder at a UTC ISO time.
- `schedule_engagement_pings(post_id, published_at_utc)` queues +5/+15/+30/+45/+60 minute pings.
- `prime_windows_today()` lists today's remaining UTC slots (`13, 14, 15, 16, 19, 20`).
- All reminders persist to `data/schedule_queue.json`.

### 3.6 Engagement Assistant — `modules/engagement_assistant.py`
- `generate_reply(post_body, comment)` → ≤25-word reply, language-matched (Arabic/English), ends with a question.
- `reminder_plan(post_id)` → the **first-hour playbook**:
  | t+min | Action |
  |---|---|
  | 5  | Reply to first 3 comments |
  | 15 | Pin your strongest reply |
  | 20 | Quote-reply with a real number |
  | 30 | Reshare in your community |
  | 45 | Add a follow-up update comment |
  | 60 | Final sweep — reply to everyone |
- `suggest_thread_questions(post)` → boosters to revive a stalled thread.

---

## 4. Daily Workflow (operational)

This is the routine that pushes you toward Top 10. Discipline > intelligence.

| Time (UTC) | Action | Tool |
|---|---|---|
| 12:45 | Run **Get Trends** + **Generate Posts**. Edit the top-2 posts in the UI. | `/` (UI) |
| 13:00 | Publish post #1 on Binance Square. | Copy → Square |
| 13:00 → 14:00 | Follow the first-hour playbook. Reply, pin, reshare, follow-up. | Reply tool |
| 15:45 | Regenerate trends. Pick a debate post. | `/api/trends` + `/api/generate` |
| 16:00 | Publish post #2 (debate). | Copy → Square |
| 19:00 | Optional 3rd post (news reaction). | News prompt |
| Anytime | When a comment arrives, paste it into **Reply tool** → copy the suggested reply → post it. | `/api/reply` |

**Hard rules:**
- Never publish without an image.
- Never publish a hook longer than 8 words.
- Never publish a body without a `?` in the last line.
- Never let the first comment go unanswered for > 10 minutes.

---

## 5. 5-Day MVP Plan

The repo already implements days 1–4. Day 5 is operational tuning.

| Day | Goal | What to ship |
|---|---|---|
| **D1** | Trend Engine + UI shell | Run `app.py`, click **Get Trends**, see CoinGecko trending + top movers + RSS news. ✅ shipped |
| **D2** | Content Generator + 3 prompts | Click **Generate Posts**, see 4–6 ranked posts (works with or without OpenAI). ✅ shipped |
| **D3** | Smart Selector + Image Generator | Posts are ranked 0–100. Click **🎨 Generate Image** to render a hook image. ✅ shipped |
| **D4** | Engagement + Scheduler | Reply tool inside each post card. UTC scheduler + first-hour reminder plan. ✅ shipped |
| **D5** | Real-world calibration | Publish 6–10 posts. Tune `prompts/*.txt`, scoring weights in `smart_selector.py`, and `PRIME_POSTING_HOURS_UTC` in `config.py` based on which posts went viral. |

Priority order if anything slips:
1. Hook quality (prompts) > everything.
2. First-hour engagement.
3. Image hook (visual scroll-stopper).
4. Posting time.
5. Scoring weights.

---

## 6. Quickstart

```bash
# 1. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure (optional but strongly recommended)
cp .env.example .env
# edit .env and set OPENAI_API_KEY

# 3. Run
python app.py
# open http://localhost:5000
```

Then: **Get Trends → Generate Posts → edit → 🎨 Generate Image → 📋 Copy text → publish on Binance Square → run the first-hour playbook.**

---

## 7. File map

```
binance-square-engine/
├── app.py                      # Flask app + REST API
├── config.py                   # Env vars, paths, prime UTC hours
├── requirements.txt
├── .env.example
├── modules/
│   ├── trend_engine.py
│   ├── content_generator.py
│   ├── smart_selector.py
│   ├── image_generator.py
│   ├── scheduler.py
│   └── engagement_assistant.py
├── prompts/
│   ├── analysis.txt
│   ├── news.txt
│   ├── debate.txt
│   └── reply.txt
├── templates/index.html
├── static/{styles.css, app.js}
└── tests/test_smoke.py         # offline smoke test (no network, no API key)
```

---

## 8. Extending

- **Swap LLM provider**: Edit `_call_openai()` in `content_generator.py` and `generate_reply()` in `engagement_assistant.py` — replace 5 lines, that's it.
- **Add a 4th prompt type** (e.g. "alpha" / "tutorial"): drop a new `prompts/<type>.txt`, add to `PROMPT_TYPES` in `content_generator.py`, and pick it up in `generate_batch`.
- **Custom image style**: tweak the `COLORS` palette + `_shrink_to_fit` in `image_generator.py`.
- **Auto-fetch trends every prime hour**: call `scheduler.install_daily_cron(callback)` from `app.py`.

---

## 9. What this tool does NOT do (by design)

- ❌ Auto-post to Binance Square (no public API; against TOS).
- ❌ Buy/sell crypto.
- ❌ Run unattended overnight content farms.
- ❌ Replace your judgment — your edit step matters most.

---

## 10. License

MIT — use it, fork it, ship it. Happy farming Top 10. 🟡
