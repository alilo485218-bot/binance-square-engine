# Binance Square — Content Engine

> Smart Posting Assistant aimed at **Top 10 Binance Square (Write to Earn)**.
> Not an auto-poster. Human-in-the-loop. Optimized for the **first 30–60 minutes** after publish, where Top-10 ranking is decided.
>
> **النسخة الحالية** ع UI بالعربي مع RTL، 6 أنواع بوست (signal / analysis / debate / news / giveaway / wrap_up) مستوحاة من تشريح حسابات Top 10 (CryptoZhiga). الصور بنمط بطاقة Binance Futures (Long/Short + Entry/SL/TP).

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
  (CoinGecko +   (6 Arabic     (scoring 0-100, (Pillow,     Assistant
   RSS news)      prompts: sig.  ranks posts)    PNL card +   (Arabic
                  /analysis/debate                hook style,  replies +
                  /news/giveaway                  red/green)   reminders)
                  /wrap_up)
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
Six Arabic prompt types modeled on the CryptoZhiga DNA (`prompts/*.txt`):

| Prompt | الدور | نسبة الاستخدام |
|---|---|---|
| `signal.txt`   | توصية صفقة (Long/Short + Entry + SL + TP1/2/3 + Leverage)        | 70-75% |
| `analysis.txt` | تعليق سوق قصير (market take)                                       | 5-10%  |
| `debate.txt`   | رأي استقطابي (hot take) لإشعال التعليقات                          | 5-10%  |
| `news.txt`     | رد فعل على خبر                                                     | 3-5%   |
| `wrap_up.txt`  | ملخص أرباح اليوم (Wins of the Day)                                | 3-5%   |
| `giveaway.txt` | بوست توزيع USDT — محرّك التفاعل الحقيقي (~16% engagement)         | 5-10%  |

Every prompt **forces JSON output**. Common schema:
```json
{
  "type": "signal|analysis|debate|news|giveaway|wrap_up",
  "coin": "BTC",
  "cashtag": "$BTC",
  "hook": "≤ 8 words",
  "hook_keywords": ["BTC", "LONG", "20X"],
  "body": "النص الكامل بالعربي",
  "direction": "up|down|flat",
  "cta": "Long ولا Short هنا؟"
}
```
Signal posts add: `side`, `leverage`, `entry`, `sl`, `tp1`, `tp2`, `tp3`, `pnl_pct`.
Giveaway posts add: `keyword`, `prize`. Wrap-up posts add: `wins[]`.

If `GEMINI_API_KEY` is missing, falls back to deterministic Arabic templates so the rest of the pipeline still runs.

### 3.3 Smart Selector — `modules/smart_selector.py`
Score (0–100), updated for the CryptoZhiga style:
- `hook_strength` (0–25) — ≤ 8 words, punchy ending, not a generic intro (Arabic + English weak-starts blacklist).
- `has_trend_coin` (0–15) — BTC/ETH/SOL or a trending symbol.
- `has_question` (0–12) — `?` or `؟` in the **last** line.
- `length_ok` (0–10) — type-aware ranges (signal 15-70, analysis 25-90, …).
- `has_cashtag` (0–8) — `$XYZ` regex.
- `has_number` (0–8) — concrete number in the body.
- `has_directional` (0–4) — clear `up`/`down` stance.
- `signal_format` (0–10) — Entry/SL/TP/leverage actually present (signal posts only).
- `has_emoji` (0–5) — 1–3 emojis (the CryptoZhiga visual signature).
- `bullish_tag` (0–3) — Bullish/Bearish/صعودي/هبوطي/Long/Short tokens.

The UI sorts posts best-first and shows the breakdown so you learn what works.

### 3.4 Hook Extractor — `modules/hook_extractor.py`
Every post automatically gets a 3–5 word punchy **image_hook**:
- Gemini LLM (few-shot prompt with power-word constraints) when `GEMINI_API_KEY` is set.
- Deterministic fallback templates by post type (signal/giveaway/news/debate/analysis/wrap_up).
- Power-word lexicon: BREAKOUT · PUMP · DUMP · TRAP · ALERT · MOON · READY · NOW · DANGER · ZONE · RUG · SURGE · CRASH.
- Post-validates: 3–5 UPPERCASE Latin words, cashtag preserved, junk single letters rejected.
- Bound to the post in `content_generator.generate_post()` — no extra UI clicks needed.

### 3.5 Image Hook Generator — `modules/image_generator.py`
Two render modes (auto-selected by `post.type`):

**Signal mode** — Binance-Futures-style PNL share card:
- Cashtag + USDT Perpetual line (top-left).
- LONG / SHORT + leverage badge (top-right, accent color).
- Big centered PNL %, with shadow.
- Entry / SL / TP1 / TP2 / TP3 rows (label left, value right).
- Centered `SIGNAL · Binance Square` footer.

**Punchy hook mode** (analysis / debate / news / wrap_up / giveaway):
- **3–5 word** Hook center-stage, biggest font that fits, heavy 8-direction outline for max contrast (CTR-optimized).
- Side color bars (left + right edge) act as the visual identifier.
- Cashtag top-left, post-type badge bottom-left, `BINANCE SQUARE` brand bottom-right.

Smart palette mapping:
- **Up / Long** → green (`14,203,129`).
- **Down / Short** → red (`246,70,93`).
- **News** → yellow (`252,213,53`).
- **Giveaway** → bright yellow background + black text (maximum scroll-stop).
- **Flat / other** → Binance gold (`240,185,11`).

Both modes:
- 1080×1080 PNG, contrast-aware outline (white outline on dark text, black outline on light text).
- No external assets — uses DejaVu Sans (preinstalled on Linux/CI) with system-font fallback.

### 3.5.1 Image Host — `modules/image_host.py`
Because Binance Square OpenAPI is **text-only**, the image needs a public URL to be embedded in the post body:
- `IMGBB_API_KEY` (recommended): free, fast, durable URL.
- `0x0.st` fallback: no signup, ~30-day URL expiry.
- If both fail, the engine keeps a local `output/<id>.png` and the UI shows a "Download PNG" button so you can upload manually on the Binance Square mobile app (still 5 seconds).

### 3.6 Scheduler — `modules/scheduler.py`
- APScheduler `BackgroundScheduler` in UTC.
- `schedule_post_reminder(post_id, fire_at_utc)` queues a reminder at a UTC ISO time.
- `schedule_engagement_pings(post_id, published_at_utc)` queues +5/+15/+30/+45/+60 minute pings.
- `prime_windows_today()` lists today's remaining UTC slots (`13, 14, 15, 16, 19, 20`).
- All reminders persist to `data/schedule_queue.json`.

### 3.7 Engagement Assistant — `modules/engagement_assistant.py`
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

Mix per CryptoZhiga's playbook: **mostly signals, anchored by 1 giveaway/day**.

| Time (UTC) | Action | Type |
|---|---|---|
| 12:45 | **Get Trends → Generate Posts**, edit the top signal | UI |
| 13:00 | Publish **signal #1** | signal |
| 13:00 → 14:00 | First-hour playbook (reply / pin / reshare / follow-up) | reply tool |
| 14:30 | Publish **giveaway** (community engine, biggest engagement boost) | giveaway |
| 15:45 | Regenerate, pick a hot take | UI |
| 16:00 | Publish **debate** (hot take) | debate |
| 19:00 | Publish **signal #2** | signal |
| 21:30 | Publish **wrap_up** (Wins of the Day) | wrap_up |
| Anytime | New comment → paste into Reply tool → copy → post | reply |

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
| **D2** | Content Generator + 3 prompts | Click **Generate Posts**, see 4–6 ranked posts (works with or without Gemini). ✅ shipped |
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
# edit .env and set GEMINI_API_KEY (https://aistudio.google.com/app/apikey)
# (optional, لتفعيل النشر التلقائي) X_SQUARE_OPENAPI_KEY=your-binance-square-key

# 3. Run
python app.py
# open http://localhost:5000
```

Then: **Get Trends → Generate Posts → edit → 🎨 Generate Image → 📋 Copy text → publish on Binance Square → run the first-hour playbook.**

---

## 6.5 Auto-Publish عبر Binance Square OpenAPI

النظام الآن يدعم النشر التلقائي عبر الـ API الرسمي لـ Binance Square — مع تأخير عشوائي بين كل بوست (5-30 دقيقة) وحد أقصى يومي وقابلية الـ retry على أخطاء الشبكة فقط.

**القيود (مهم):**
- الـ API يدعم نصًا فقط. الصور لا تُرفع تلقائيًا — تُسجَّل في log كتذكير لرفعها يدويًا.
- الـ default mode هو `dry-run` (لا يرسل شيء فعليًا) لحماية الحساب.
- إذا حدث خطأ نهائي (KYC، كلمات حساسة، حظر حساب) يتوقف الطابور تلقائيًا.
- الحد اليومي الافتراضي 12 بوست (قابل للتعديل).

**استخدام CLI:**

```bash
# 1) أنشئ ملف queue
cp data/posts.queue.example.json data/posts.queue.json
# عدّل المحتوى حسب احتياجك

# 2) جرّب dry-run (لا يرسل شيء)
python auto_publish.py data/posts.queue.json

# 3) للنشر الفعلي
export X_SQUARE_OPENAPI_KEY='your-key-here'
python auto_publish.py data/posts.queue.json --live

# 4) خيارات
python auto_publish.py data/posts.queue.json --live --min 5 --max 30 --cap 12
python auto_publish.py data/posts.queue.json --live --no-shuffle
```

**استخدام من الواجهة (UI):**
زر `🧪 تجربة نشر` على كل بوست = dry-run سريع.
زر `🚀 نشر الآن` = نشر فعلي (يطلب تأكيدًا قبل الإرسال).

**Endpoints:**
- `GET  /api/publish/status` — حالة المفتاح + الحد اليومي + كم نُشر اليوم.
- `POST /api/publish/single` — `{text, hashtags?, dry_run?}` ينشر بوست واحد.
- `POST /api/publish/queue/preview` — `{posts, shuffle?, min_delay_min?, max_delay_min?}` يحاكي الطابور بدون انتظار.

**Endpoint رسمي مستخدَم:**
```
POST https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add
Headers:
  X-Square-OpenAPI-Key: <key>
  Content-Type: application/json
  clienttype: binanceSkill
Body:
  {"bodyTextOnly": "<text + hashtags>"}
```

الـ log في `data/publish_log.jsonl` (سطر JSON لكل محاولة، نجاحًا أو فشلًا).

---

## 7. File map

```
binance-square-engine/
├── app.py                      # Flask app + REST API
├── config.py                   # Env vars, paths, prime UTC hours
├── requirements.txt
├── .env.example
├── auto_publish.py             # CLI: قائمة JSON → نشر تلقائي مع تأخير عشوائي
├── modules/
│   ├── trend_engine.py
│   ├── content_generator.py
│   ├── smart_selector.py
│   ├── image_generator.py
│   ├── scheduler.py
│   ├── engagement_assistant.py
│   └── binance_publisher.py    # OpenAPI client + retry + queue logic
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

- **Swap LLM provider**: Edit `_call_gemini()` in `content_generator.py` and `generate_reply()` in `engagement_assistant.py` — replace 5 lines, that's it.
- **Add a 4th prompt type** (e.g. "alpha" / "tutorial"): drop a new `prompts/<type>.txt`, add to `PROMPT_TYPES` in `content_generator.py`, and pick it up in `generate_batch`.
- **Custom image style**: tweak the `COLORS` palette + `_shrink_to_fit` in `image_generator.py`.
- **Auto-fetch trends every prime hour**: call `scheduler.install_daily_cron(callback)` from `app.py`.

---

## 9. What this tool does NOT do (by design)

- ❌ Auto-upload images via API (Binance Square OpenAPI is text-only — صور تُرفع يدويًا).
- ❌ Survivorship-bias (نشر الصفقات الرابحة فقط) — يخالف ToS ويحرق الحساب.
- ❌ Buy/sell crypto.
- ❌ Replace your judgment — your edit step matters most.
- ⚠️ Auto-publish موجود لكنه dry-run افتراضيًا — لازم تفعّله صراحة.

---

## 10. License

MIT — use it, fork it, ship it. Happy farming Top 10. 🟡
