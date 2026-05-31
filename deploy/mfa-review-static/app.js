const API = "/mfa/api";
const LABELS = [
  ["keep", "Keep"],
  ["minor", "Minor"],
  ["background_audio", "BG audio"],
  ["text_bad", "Text bad"],
  ["audio_bad", "Audio bad"],
  ["unsure", "Unsure"],
];

const rows = window.REVIEW_ROWS || [];
const meta = window.REVIEW_META || {dataset: "mfa_source_review"};
const localKey = `mfa-public-review:${meta.dataset}:decisions`;
let decisions = {};
let filtered = [];
let current = 0;
let statusFilter = "all";
let reviewer = {name: "", email: ""};

const $ = (id) => document.getElementById(id);

function loadLocal() {
  try {
    decisions = JSON.parse(localStorage.getItem(localKey) || "{}");
  } catch {
    decisions = {};
  }
  reviewer.name = localStorage.getItem(`${localKey}:name`) || "";
  reviewer.email = localStorage.getItem(`${localKey}:email`) || "";
  $("reviewerName").value = reviewer.name;
  $("reviewerEmail").value = reviewer.email;
}

function saveLocal() {
  localStorage.setItem(localKey, JSON.stringify(decisions));
  localStorage.setItem(`${localKey}:name`, reviewer.name);
  localStorage.setItem(`${localKey}:email`, reviewer.email);
}

function mergeServerDecision(entryId, label, reviewedAt) {
  const current = decisions[entryId] || {};
  if (current.label && !current.server) return;
  decisions[entryId] = {
    ...current,
    label,
    server: true,
    reviewed_at: reviewedAt || "",
  };
}

function escapeHtml(text) {
  return String(text || "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function fmt(value, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "";
}

function badLabel(label) {
  return ["background_audio", "text_bad", "audio_bad"].includes(label);
}

function setStatusFilter(value) {
  statusFilter = value;
  document.querySelectorAll(".status").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === value);
  });
}

function setCurrentById(entryId) {
  setStatusFilter("all");
  filtered = rows;
  const idx = rows.findIndex((row) => row.id === entryId);
  current = idx >= 0 ? idx : 0;
  renderList();
  renderCurrent();
}

function applyFilters() {
  filtered = rows.filter((row) => {
    const label = (decisions[row.id] || {}).label || "";
    if (statusFilter === "open") return !label;
    if (statusFilter === "done") return Boolean(label);
    if (statusFilter === "bad") return badLabel(label);
    return true;
  });
  current = Math.min(current, Math.max(filtered.length - 1, 0));
  renderList();
  renderCurrent();
}

function renderSummary(extra = "") {
  const labels = rows.map((row) => (decisions[row.id] || {}).label || "");
  const done = labels.filter(Boolean).length;
  const bad = labels.filter(badLabel).length;
  const hours = rows.reduce((acc, row) => acc + (Number(row.duration_sec) || 0), 0) / 3600;
  $("summary").textContent = `${done}/${rows.length} local, ${bad} bad, ${fmt(hours, 2)}h${extra ? " | " + extra : ""}`;
}

function renderList() {
  renderSummary();
  $("list").innerHTML = filtered.map((row, idx) => {
    const label = (decisions[row.id] || {}).label || "open";
    const active = idx === current ? " active" : "";
    const bad = badLabel(label) ? " bad" : "";
    return `<button class="sample${active}" data-index="${idx}">
      <span class="sample-title">${escapeHtml(row.id)}</span>
      <span class="sample-text">${escapeHtml(row.transcript)}</span>
      <span class="sample-meta">
        <span>${fmt(row.duration_sec, 1)}s</span>
        <span class="pill${label !== "open" ? " done" : ""}${bad}">${escapeHtml(label)}</span>
      </span>
    </button>`;
  }).join("");
  document.querySelectorAll(".sample").forEach((button) => {
    button.addEventListener("click", () => {
      openSample(Number(button.dataset.index));
    });
  });
}

function renderCurrent() {
  if (!reviewer.name) return;
  if (!filtered.length) {
    $("title").textContent = "No samples";
    $("eyebrow").textContent = "";
    $("audio").removeAttribute("src");
    $("metrics").innerHTML = "";
    $("transcript").textContent = "";
    $("labels").innerHTML = "";
    $("notes").value = "";
    return;
  }
  const row = filtered[current];
  const decision = decisions[row.id] || {};
  $("title").textContent = row.id;
  $("eyebrow").textContent = `${current + 1}/${filtered.length} | ${meta.dataset}`;
  $("audio").src = row.audio;
  $("audio").playbackRate = Number($("speed").value);
  $("metrics").innerHTML = [
    `<div class="metric"><span>Duration</span><strong>${fmt(row.duration_sec, 2)}s</strong></div>`,
    `<div class="metric"><span>Reviewer</span><strong>${escapeHtml(reviewer.name)}</strong></div>`,
  ].join("");
  $("transcript").textContent = row.transcript || "";
  $("notes").value = decision.notes || "";
  if (decision.server) {
    $("labels").innerHTML = `<div class="server-reviewed">Already reviewed on server: ${escapeHtml(decision.label)}</div>`;
    return;
  }
  $("labels").innerHTML = LABELS.map(([value, label], index) =>
    `<button class="label${decision.label === value ? " active" : ""}" data-label="${value}">${index + 1}. ${label}</button>`
  ).join("");
  document.querySelectorAll(".label").forEach((button) => {
    button.addEventListener("click", () => submitDecision(row, button.dataset.label));
  });
}

async function submitDecision(row, label) {
  const notes = $("notes").value || "";
  decisions[row.id] = {label, notes, updated_at: new Date().toISOString()};
  saveLocal();
  renderList();
  renderCurrent();
  $("saveStatus").textContent = "Saving...";
  $("saveStatus").className = "save-status";
  try {
    const response = await fetch(`${API}/decisions`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        dataset: meta.dataset,
        entry_id: row.id,
        label,
        notes,
        transcript: row.transcript || "",
        duration_sec: row.duration_sec || null,
        reviewer_name: reviewer.name,
        reviewer_email: reviewer.email,
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    $("saveStatus").textContent = "Saved";
    $("saveStatus").className = "save-status ok";
    await assignNext();
  } catch (error) {
    $("saveStatus").textContent = "Saved locally, server save failed";
    $("saveStatus").className = "save-status err";
    console.error(error);
  }
}

async function assignNext(skipCurrent = false) {
  const currentId = filtered[current]?.id || "";
  const candidateIds = rows
    .filter((row) => !((decisions[row.id] || {}).label))
    .filter((row) => !(skipCurrent && row.id === currentId))
    .map((row) => row.id);
  if (!candidateIds.length) {
    applyFilters();
    $("saveStatus").textContent = "No local open samples";
    $("saveStatus").className = "save-status ok";
    return;
  }

  $("saveStatus").textContent = "Finding next unclaimed sample...";
  $("saveStatus").className = "save-status";
  try {
    const response = await fetch(`${API}/claims/next`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        dataset: meta.dataset,
        reviewer_name: reviewer.name,
        reviewer_email: reviewer.email,
        candidate_ids: candidateIds,
        ttl_minutes: 120,
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    if (!payload.entry_id) {
      $("saveStatus").textContent = "No unclaimed server samples right now";
      $("saveStatus").className = "save-status ok";
      return;
    }
    setCurrentById(payload.entry_id);
    $("saveStatus").textContent = payload.reclaimed ? "Resumed claimed sample" : "Claimed next sample";
    $("saveStatus").className = "save-status ok";
  } catch (error) {
    console.error(error);
    $("saveStatus").textContent = "Claim failed, using local next";
    $("saveStatus").className = "save-status err";
    nextLocal();
  }
}

async function claimRows(candidateIds) {
  const response = await fetch(`${API}/claims/next`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      dataset: meta.dataset,
      reviewer_name: reviewer.name,
      reviewer_email: reviewer.email,
      candidate_ids: candidateIds,
      ttl_minutes: 120,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function openSample(index) {
  const row = filtered[index];
  if (!row) return;
  if (!reviewer.name || (decisions[row.id] || {}).label) {
    current = index;
    renderList();
    renderCurrent();
    return;
  }

  $("saveStatus").textContent = "Checking claim...";
  $("saveStatus").className = "save-status";
  try {
    const payload = await claimRows([row.id]);
    if (payload.entry_id !== row.id) {
      $("saveStatus").textContent = "Already claimed or reviewed by someone else";
      $("saveStatus").className = "save-status err";
      return;
    }
    current = index;
    renderList();
    renderCurrent();
    $("saveStatus").textContent = payload.reclaimed ? "Resumed claimed sample" : "Claimed sample";
    $("saveStatus").className = "save-status ok";
  } catch (error) {
    console.error(error);
    $("saveStatus").textContent = "Claim check failed";
    $("saveStatus").className = "save-status err";
  }
}

function next() {
  if (reviewer.name) {
    assignNext(true);
    return;
  }
  nextLocal();
}

function nextLocal() {
  if (!filtered.length) return;
  current = Math.min(current + 1, filtered.length - 1);
  renderList();
  renderCurrent();
}

function prev() {
  if (!filtered.length) return;
  current = Math.max(current - 1, 0);
  renderList();
  renderCurrent();
}

async function refreshStats() {
  try {
    await loadServerDecisions();
    const response = await fetch(`${API}/stats?dataset=${encodeURIComponent(meta.dataset)}`);
    const stats = await response.json();
    renderSummary(`server ${stats.total_decisions || 0}, reviewers ${stats.unique_reviewers || 0}`);
  } catch {
    renderSummary("server stats unavailable");
  }
}

async function loadServerDecisions() {
  const response = await fetch(`${API}/decisions/ids?dataset=${encodeURIComponent(meta.dataset)}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  for (const item of payload.decisions || []) {
    mergeServerDecision(item.entry_id, item.label, item.reviewed_at);
  }
  saveLocal();
}

async function start() {
  reviewer.name = $("reviewerName").value.trim();
  reviewer.email = $("reviewerEmail").value.trim();
  if (!reviewer.name) {
    $("reviewerName").focus();
    return;
  }
  saveLocal();
  $("setup").classList.add("collapsed");
  $("saveStatus").textContent = "Loading server-reviewed samples...";
  $("saveStatus").className = "save-status";
  try {
    await loadServerDecisions();
  } catch (error) {
    console.error(error);
    $("saveStatus").textContent = "Server reviewed-list unavailable";
    $("saveStatus").className = "save-status err";
  }
  applyFilters();
  assignNext();
}

function init() {
  loadLocal();
  document.querySelectorAll(".status").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".status").forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      statusFilter = button.dataset.status;
      current = 0;
      applyFilters();
    });
  });
  $("startReview").addEventListener("click", start);
  $("refreshStats").addEventListener("click", refreshStats);
  $("next").addEventListener("click", next);
  $("prev").addEventListener("click", prev);
  $("speed").addEventListener("change", () => {
    $("audio").playbackRate = Number($("speed").value);
  });
  $("notes").addEventListener("input", () => {
    if (!filtered.length) return;
    const row = filtered[current];
    decisions[row.id] = {...(decisions[row.id] || {}), notes: $("notes").value};
    saveLocal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "TEXTAREA" || event.target.tagName === "INPUT") return;
    if (event.key === "ArrowRight") next();
    if (event.key === "ArrowLeft") prev();
    if (event.key === " ") {
      event.preventDefault();
      const player = $("audio");
      player.paused ? player.play() : player.pause();
    }
    const idx = Number(event.key) - 1;
    if (idx >= 0 && idx < LABELS.length && filtered.length && reviewer.name) {
      submitDecision(filtered[current], LABELS[idx][0]);
    }
  });
  if (reviewer.name) start();
  else renderSummary();
}

init();
