// Tiny vanilla-JS frontend for the Content Engine.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "POST" };
  if (path.startsWith("/api/pending") || path.startsWith("/api/prime")) opts.method = "GET";
  if (opts.method === "GET") delete opts.body;
  const res = await fetch(path, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

// --- Trends ---
$("#btn-trends").addEventListener("click", async () => {
  const btn = $("#btn-trends");
  btn.disabled = true; btn.textContent = "Loading...";
  try {
    const snap = await api("/api/trends", {});
    renderTrends(snap);
  } catch (e) {
    alert("Trends failed: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "1 · Get Trends";
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
      <div style="color:#6c7587;font-size:11px">rank ${c.rank ?? "-"} · ${c.source}</div>
    `;
    root.appendChild(div);
  });
}

// --- Generate ---
$("#btn-generate").addEventListener("click", async () => {
  const btn = $("#btn-generate");
  btn.disabled = true; btn.textContent = "Generating...";
  try {
    const r = await api("/api/generate", { n_per_type: 2 });
    renderPosts(r.posts || []);
  } catch (e) {
    alert("Generate failed: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "2 · Generate Posts";
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
    card.querySelector(".type").textContent = p.type;
    const dir = card.querySelector(".dir");
    dir.textContent = p.direction || "flat";
    dir.classList.add(p.direction || "flat");
    card.querySelector(".score").textContent = `score ${p.score?.total ?? 0}/100`;
    card.querySelector(".body").value = p.body || "";
    card.querySelector(".word-count").textContent = `${p.word_count || 0} words`;
    card.querySelector(".cashtag").textContent = p.cashtag || "";
    card.querySelector(".score-json").textContent =
      JSON.stringify(p.score?.breakdown || {}, null, 2);

    const post = p;
    card.querySelector(".btn-image").addEventListener("click", async (e) => {
      const b = e.target; b.disabled = true; b.textContent = "Rendering...";
      try {
        post.body = card.querySelector(".body").value;
        const r = await api("/api/image", { post });
        const slot = card.querySelector(".image-slot");
        slot.innerHTML = `<img src="${r.url}?t=${Date.now()}" alt="hook">`;
      } catch (err) { alert("Image failed: " + err.message); }
      finally { b.disabled = false; b.textContent = "🎨 Generate Image"; }
    });

    card.querySelector(".btn-copy").addEventListener("click", () => {
      navigator.clipboard.writeText(card.querySelector(".body").value);
      const b = card.querySelector(".btn-copy");
      const t = b.textContent; b.textContent = "✓ Copied"; setTimeout(() => b.textContent = t, 1200);
    });

    card.querySelector(".btn-schedule").addEventListener("click", async () => {
      const when = prompt("Fire reminder at (UTC ISO, e.g. 2025-12-31T15:00:00):");
      if (!when) return;
      try {
        const r = await api("/api/schedule",
          { post_id: post.id, fire_at_utc: when, label: "Publish " + (post.cashtag || "") });
        alert("Reminder scheduled for " + r.fire_at_utc);
      } catch (e) { alert("Schedule failed: " + e.message); }
    });

    card.querySelector(".btn-reply-tool").addEventListener("click", () => {
      card.querySelector(".reply-slot").classList.toggle("hidden");
    });

    card.querySelector(".btn-make-reply").addEventListener("click", async () => {
      const comment = card.querySelector(".comment-in").value;
      if (!comment) return;
      try {
        const r = await api("/api/reply", { post_body: card.querySelector(".body").value, comment });
        card.querySelector(".reply-out").textContent = `${r.reply}\n\n[tone: ${r.tone}]`;
      } catch (e) { alert("Reply failed: " + e.message); }
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
      root.innerHTML = `<div class="empty">No prime windows left today.
        Tomorrow's hours (UTC): ${r.all_hours_utc.join(", ")}.</div>`;
    }
  } catch (e) { alert("Windows failed: " + e.message); }
});
