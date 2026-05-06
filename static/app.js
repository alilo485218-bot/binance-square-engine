// واجهة JavaScript خفيفة لمحرّك المحتوى — كل النصوص بالعربي.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

// خريطة أسماء أنواع البوستات (إنجليزي → عربي) لعرضها في الواجهة.
const TYPE_LABELS = {
  signal:   "توصية صفقة",
  analysis: "تحليل",
  debate:   "جدل",
  news:     "خبر",
  giveaway: "Giveaway",
  wrap_up:  "ملخص اليوم",
};
const DIR_LABELS = { up: "صعود", down: "هبوط", flat: "محايد" };

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), credentials: "include" }
    : { method: "POST", credentials: "include" };
  if (path.startsWith("/api/pending") || path.startsWith("/api/prime") ||
      path.startsWith("/api/reminder-plan")) opts.method = "GET";
  if (opts.method === "GET") delete opts.body;
  // المتصفح يرفض إنشاء fetch من URL يحتوي بيانات اعتماد basic-auth،
  // فنبني الـ URL من location.origin (يستبعد الـ user:pass) ونعتمد على credentials:include للهيدر.
  const url = new URL(path, location.origin).toString();
  const res = await fetch(url, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

// --- Trends ---
$("#btn-trends").addEventListener("click", async () => {
  const btn = $("#btn-trends");
  btn.disabled = true; btn.textContent = "جاري التحميل...";
  try {
    const snap = await api("/api/trends", {});
    renderTrends(snap);
  } catch (e) {
    alert("فشل جلب الترند: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "١ · جلب الترند";
  }
});

function renderTrends(snap) {
  $("#trends-empty").style.display = "none";
  const root = $("#trends");
  root.innerHTML = "";
  (snap.coins || []).slice(0, 12).forEach(c => {
    const change = c.change_24h !== null && c.change_24h !== undefined
      ? `${c.change_24h >= 0 ? "+" : ""}${c.change_24h.toFixed(2)}%` : "-";
    const dirClass = c.direction || "flat";
    const div = document.createElement("div");
    div.className = "coin";
    div.innerHTML = `
      <div class="sym">${c.cashtag || "$" + c.symbol}</div>
      <div>${c.name || ""}</div>
      <div class="${dirClass}">${change}</div>
      <div style="color:#6c7587;font-size:11px">ترتيب ${c.rank ?? "-"} · ${c.source}</div>
    `;
    root.appendChild(div);
  });
}

// --- Generate ---
$("#btn-generate").addEventListener("click", async () => {
  const btn = $("#btn-generate");
  btn.disabled = true; btn.textContent = "جاري التوليد...";
  try {
    const r = await api("/api/generate", { n_per_type: 1 });
    renderPosts(r.posts || []);
  } catch (e) {
    alert("فشل التوليد: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "٢ · توليد البوستات";
  }
});

function renderPosts(posts) {
  $("#posts-empty").style.display = posts.length ? "none" : "block";
  const root = $("#posts");
  root.innerHTML = "";
  const tpl = $("#post-card-tpl");
  posts.forEach(p => {
    const node = tpl.content.cloneNode(true);
    const card = node.querySelector(".post");
    card.dataset.id = p.id;
    card.querySelector(".type").textContent = TYPE_LABELS[p.type] || p.type;
    const dir = card.querySelector(".dir");
    dir.textContent = DIR_LABELS[p.direction] || (p.direction || "محايد");
    dir.classList.add(p.direction || "flat");
    card.querySelector(".score").textContent = `التقييم ${p.score?.total ?? 0}/100`;
    card.querySelector(".body").value = p.body || "";
    card.querySelector(".word-count").textContent = `${p.word_count || 0} كلمة`;
    card.querySelector(".cashtag").textContent = p.cashtag || "";
    card.querySelector(".score-json").textContent =
      JSON.stringify(p.score?.breakdown || {}, null, 2);

    const post = p;
    card.querySelector(".btn-image").addEventListener("click", async (e) => {
      const b = e.target; b.disabled = true; b.textContent = "جاري الرسم...";
      try {
        post.body = card.querySelector(".body").value;
        const r = await api("/api/image", { post });
        const slot = card.querySelector(".image-slot");
        slot.innerHTML = `<img src="${r.url}?t=${Date.now()}" alt="hook">`;
      } catch (err) { alert("فشل توليد الصورة: " + err.message); }
      finally { b.disabled = false; b.textContent = "🎨 توليد الصورة"; }
    });

    card.querySelector(".btn-copy").addEventListener("click", () => {
      navigator.clipboard.writeText(card.querySelector(".body").value);
      const b = card.querySelector(".btn-copy");
      const t = b.textContent; b.textContent = "✓ تم النسخ";
      setTimeout(() => b.textContent = t, 1200);
    });

    card.querySelector(".btn-schedule").addEventListener("click", async () => {
      const when = prompt("وقت التذكير (UTC ISO، مثال: 2025-12-31T15:00:00):");
      if (!when) return;
      try {
        const r = await api("/api/schedule",
          { post_id: post.id, fire_at_utc: when, label: "حان وقت نشر " + (post.cashtag || "") });
        alert("تم جدولة التذكير في " + r.fire_at_utc);
      } catch (e) { alert("فشل الجدولة: " + e.message); }
    });

    card.querySelector(".btn-reply-tool").addEventListener("click", () => {
      card.querySelector(".reply-slot").classList.toggle("hidden");
    });

    card.querySelector(".btn-make-reply").addEventListener("click", async () => {
      const comment = card.querySelector(".comment-in").value;
      if (!comment) return;
      try {
        const r = await api("/api/reply", { post_body: card.querySelector(".body").value, comment });
        const toneLabels = { agree: "موافق", disagree: "مخالف", neutral: "محايد", curious: "فضولي" };
        const toneAr = toneLabels[r.tone] || r.tone;
        card.querySelector(".reply-out").textContent = `${r.reply}\n\n[نبرة: ${toneAr}]`;
      } catch (e) { alert("فشل توليد الرد: " + e.message); }
    });

    root.appendChild(node);
  });
}

// --- Prime windows ---
$("#btn-windows").addEventListener("click", async () => {
  try {
    const r = await api("/api/prime-windows");
    const block = $("#windows-block");
    block.classList.remove("hidden");
    const root = $("#windows");
    root.innerHTML = "";
    (r.windows || []).forEach(w => {
      const d = document.createElement("div");
      d.className = "slot";
      d.textContent = w;
      root.appendChild(d);
    });
    if (!r.windows || r.windows.length === 0) {
      root.innerHTML = `<div class="empty">لا توجد نوافذ ذهبية متبقية اليوم.
        ساعات الغد (UTC): ${r.all_hours_utc.join(", ")}.</div>`;
    }
  } catch (e) { alert("فشل تحميل النوافذ: " + e.message); }
});

// --- خطة أول ساعة ---
$("#btn-plan").addEventListener("click", async () => {
  try {
    const r = await api("/api/reminder-plan/preview");
    const block = $("#plan-block");
    block.classList.remove("hidden");
    const ol = $("#plan-list");
    ol.innerHTML = "";
    (r.plan || []).forEach(p => {
      const li = document.createElement("li");
      li.innerHTML = `<b>+${p.minute_offset} دقيقة</b> — ${p.action}`;
      ol.appendChild(li);
    });
  } catch (e) { alert("فشل تحميل الخطة: " + e.message); }
});
