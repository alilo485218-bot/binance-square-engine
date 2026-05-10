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
    if (p.image_hook) {
      card.querySelector(".hook-preview").innerHTML =
        `<span class="hook-label">Hook بصري:</span><span class="hook-text">🎯 ${p.image_hook}</span>`;
    }
    card.querySelector(".score-json").textContent =
      JSON.stringify(p.score?.breakdown || {}, null, 2);

    const post = p;
    const renderImageSlot = (r, slot, withUpload) => {
      post.image_hook = r.hook;
      // publish_url = hosted_url لو رفعت، وإلا = public_url محلي
      post.image_url = r.publish_url;
      post.is_hosted = !!r.hosted_url;
      const cacheBust = `${r.url}?t=${Date.now()}`;
      const hookBadge = r.hook ? `<div class="hook-badge">🎯 ${r.hook}</div>` : "";
      let hostStatus = "";
      if (withUpload) {
        if (r.hosted_url) {
          hostStatus = `<div class="image-hint ok">✓ مرفوع لاستضافة عامة — سيُلصق رابطه في البوست.<br><span class="muted">${r.hosted_url}</span></div>`;
        } else {
          hostStatus = `<div class="image-hint warn">⚠️ تعذّر الرفع لاستضافة عامة (${r.host_error || "unknown"}). سيعمل البوست بنص فقط، حمّل الصورة يدويًا.</div>`;
        }
      } else {
        hostStatus = `<div class="image-hint">معاينة محلية فقط. اضغط "رفع للاستضافة" لرفعها كرابط عام يدخل البوست تلقائيًا.</div>`;
      }
      slot.innerHTML = `
        ${hookBadge}
        <img src="${cacheBust}" alt="hook">
        <div class="image-actions">
          <a class="btn-mini" href="${r.url}" download>⬇️ تنزيل PNG</a>
          <button class="btn-mini btn-copy-url">📋 نسخ الرابط</button>
          <button class="btn-mini btn-upload-img">☁️ رفع للاستضافة</button>
        </div>
        ${hostStatus}
      `;
      slot.querySelector(".btn-copy-url").addEventListener("click", () => {
        navigator.clipboard.writeText(post.image_url);
        const btn = slot.querySelector(".btn-copy-url");
        const t = btn.textContent; btn.textContent = "✓ تم النسخ";
        setTimeout(() => btn.textContent = t, 1200);
      });
      slot.querySelector(".btn-upload-img").addEventListener("click", async (ev) => {
        const ub = ev.target; ub.disabled = true; ub.textContent = "جاري الرفع...";
        try {
          post.body = card.querySelector(".body").value;
          const r2 = await api("/api/image", { post, upload: true });
          renderImageSlot(r2, slot, true);
        } catch (err2) {
          alert("فشل الرفع: " + err2.message);
        } finally {
          ub.disabled = false;
        }
      });
    };

    card.querySelector(".btn-image").addEventListener("click", async (e) => {
      const b = e.target; b.disabled = true; b.textContent = "جاري الرسم...";
      try {
        post.body = card.querySelector(".body").value;
        const r = await api("/api/image", { post, upload: false });
        const slot = card.querySelector(".image-slot");
        renderImageSlot(r, slot, false);
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

    const publishHandler = (live) => async (e) => {
      const b = e.target;
      const orig = b.textContent;
      const text = card.querySelector(".body").value;
      if (!text.trim()) { alert("النص فارغ."); return; }
      const hashtags = (post.cashtag ? [post.cashtag] : []).map(t => t.replace(/^\$/, ""));
      if (live && !confirm("سيتم نشر البوست فعليًا على حسابك في Binance Square. متأكد؟")) return;
      b.disabled = true; b.textContent = live ? "جاري النشر..." : "جاري التجربة...";
      try {
        const r = await api("/api/publish/single", {
          text, hashtags, dry_run: !live,
          image_url: post.image_url || null,
        });
        const slot = card.querySelector(".publish-result");
        slot.classList.remove("hidden");
        if (r.success) {
          if (r.dry_run) {
            slot.innerHTML = `<div class="ok">✓ تجربة ناجحة (لم يُرسل فعليًا) — ${text.length} حرف</div>`;
          } else {
            const link = r.post_url
              ? `<a href="${r.post_url}" target="_blank" rel="noopener">${r.post_url}</a>`
              : "(تم النشر، لكن الـ URL غير متوفر)";
            slot.innerHTML = `<div class="ok">✓ نُشر بنجاح — ${link}</div>`;
          }
        } else {
          slot.innerHTML = `<div class="warn">✗ فشل النشر — code=${r.code || "?"} · ${r.error || r.message || ""}</div>`;
        }
      } catch (err) {
        alert("فشل النشر: " + err.message);
      } finally {
        b.disabled = false; b.textContent = orig;
      }
    };
    card.querySelector(".btn-publish-dry").addEventListener("click", publishHandler(false));
    card.querySelector(".btn-publish-live").addEventListener("click", publishHandler(true));

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
