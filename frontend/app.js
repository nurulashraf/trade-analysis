/* KONSENSUS frontend — no external libraries, custom canvas chart. */
"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n) => `${n >= 0 ? "▲" : "▼"}${Math.abs(n).toFixed(2)}%`;

/* asset class by Yahoo suffix; display form: GC=F → GC, EURUSD=X → EUR/USD */
const assetClass = (s) => (s.endsWith("=F") ? "commodities" : s.endsWith("=X") ? "forex" : "stocks");
const dispSym = (s) => {
  if (s.endsWith("=F")) return s.slice(0, -2);
  if (s.endsWith("=X")) { const p = s.slice(0, -2); return p.length === 6 ? `${p.slice(0, 3)}/${p.slice(3)}` : p; }
  return s;
};

const state = {
  config: null,
  watchlist: [],
  symbol: null,
  candles: [],
  analysis: null,
  days: 66,
  botRunning: false,
  portfolio: null,
  tab: "stocks",
};

/* ------------------------------------------------------------------ clock */
setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("en-GB");
}, 1000);

/* ------------------------------------------------------------- data fetch */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function loadConfig() {
  state.config = await api("/api/config");
  $("data-src").textContent = (state.config.provider || "DATA").toUpperCase();
  $("brains-line").innerHTML =
    `Brain: <b>${state.config.brains.join(" + ")}</b> — independent brains each read the charts AND the news; the bot only trades when <b>${state.config.required_agreement} agree</b>.`;
  $("badge-brains").textContent = `${state.config.brains.length} AI`;
}

async function loadWatchlist() {
  state.watchlist = await api("/api/watchlist");
  renderWatchlist();
  renderTape();
  if (!state.symbol && state.watchlist.length) selectSymbol("INTC" in idx() ? "INTC" : state.watchlist[0].symbol);
  updateMood();
}

function idx() {
  const m = {};
  state.watchlist.forEach((w) => (m[w.symbol] = w));
  return m;
}

function updateMood() {
  const ups = state.watchlist.filter((w) => w.change_pct >= 0).length;
  const total = state.watchlist.length;
  const el = $("mood");
  el.textContent = `Breadth ${ups}/${total} · ${ups >= total / 2 ? "Risk-on" : "Risk-off"}`;
  el.style.color = ups >= total / 2 ? "var(--green)" : "var(--red)";
}

async function selectSymbol(sym) {
  state.symbol = sym;
  renderWatchlist();
  $("chart-title").textContent = `${dispSym(sym)} · ${state.config?.names?.[sym] || sym}`;
  const [candles, analysis] = await Promise.all([
    api(`/api/candles/${encodeURIComponent(sym)}?days=400`),
    api(`/api/analysis/${encodeURIComponent(sym)}`),
  ]);
  state.candles = candles;
  state.analysis = analysis;
  renderTopQuote();
  renderStats();
  renderPlainEnglish();
  drawChart();
}

/* --------------------------------------------------------------- renderers */
function renderWatchlist() {
  const box = $("watchlist");
  box.innerHTML = "";
  const rows = state.watchlist.filter((w) => (w.asset_class || assetClass(w.symbol)) === state.tab);
  for (const w of rows) {
    const row = document.createElement("div");
    row.className = "wl-row" + (w.symbol === state.symbol ? " active" : "");
    const cls = w.change_pct >= 0 ? "up" : "down";
    row.innerHTML = `<div><div class="wl-sym"><i style="background:${w.change_pct >= 0 ? "var(--green)" : "var(--red)"}"></i>${dispSym(w.symbol)}</div>
      <div class="wl-price">${fmt(w.price, w.price < 10 ? 4 : 2)}</div></div>
      <div class="${cls}">${w.change_pct >= 0 ? "+" : ""}${w.change_pct.toFixed(2)}%</div>`;
    row.onclick = () => selectSymbol(w.symbol);
    box.appendChild(row);
  }
}

function renderTape() {
  const parts = state.watchlist.map(
    (w) => `<span><b>${dispSym(w.symbol)}</b> ${fmt(w.price, w.price < 10 ? 4 : 2)} <span class="${w.change_pct >= 0 ? "up" : "down"}">${pct(w.change_pct)}</span></span>`
  );
  const el = $("tape-inner");
  el.innerHTML = parts.join("") + parts.join(""); // doubled for seamless loop
  // Constant speed (~45 px/s) no matter how many symbols are on the tape.
  const dur = Math.max(el.scrollWidth / 2 / 45, 20);
  el.style.animationDuration = `${dur}s`;
  // Quotes refresh every 8s and rebuilding the tape restarts the CSS
  // animation — resume from where the loop would be instead of snapping back.
  renderTape.t0 ??= Date.now();
  el.style.animationDelay = `-${((Date.now() - renderTape.t0) / 1000) % dur}s`;
}

function renderTopQuote() {
  const a = state.analysis?.analysis;
  if (!a) return;
  $("top-symbol").textContent = dispSym(a.symbol);
  $("top-price").textContent = fmt(a.price, a.price < 10 ? 4 : 2);
  const el = $("top-change");
  el.textContent = `${a.change_pct >= 0 ? "+" : ""}${a.change_pct.toFixed(2)}%`;
  el.className = a.change_pct >= 0 ? "up" : "down";
}

function renderStats() {
  const a = state.analysis?.analysis;
  if (!a) return;
  const last = state.candles[state.candles.length - 1] || {};
  const cls = assetClass(a.symbol);
  const d = a.price < 10 ? 4 : 2;
  const unit = cls === "forex" ? dispSym(a.symbol).slice(-3) : "USD";
  const vol = last.volume ?? 0;
  const rows = [
    ["Price", `${fmt(a.price, d)} ${unit}`],
    ["Change", `<span class="${a.change_pct >= 0 ? "up" : "down"}">${a.change_pct >= 0 ? "+" : ""}${a.change_pct.toFixed(2)}%</span>`],
    ["Open", fmt(last.open ?? 0, d)],
    ["High", fmt(last.high ?? 0, d)],
    ["Low", fmt(last.low ?? 0, d)],
    ["Volume", vol >= 1e6 ? `${fmt(vol / 1e6, 1)}M` : vol > 0 ? `${fmt(vol / 1e3, 0)}K` : "—"],
    ["52W High", fmt(a.high_52w, d)],
    ["52W Low", fmt(a.low_52w, d)],
    ["RSI(14)", a.rsi14 == null ? "—" : Math.round(a.rsi14)],
    ["Ann. vol", `${Math.round(a.ann_vol * 100)}%`],
  ];
  $("stats").innerHTML = rows.map(([k, v]) => `<div class="k">${k}</div><div class="v">${v}</div>`).join("");
}

function renderPlainEnglish() {
  const a = state.analysis?.analysis;
  if (!a) return;
  const dir = a.trend === "up" ? "an uptrend" : a.trend === "down" ? "a downtrend" : "a sideways range";
  const nearHigh = a.price > a.high_52w * 0.95 ? ", near its 1-year high" : "";
  const noun = { stocks: "stock", commodities: "commodity", forex: "currency pair" }[assetClass(a.symbol)];
  const wild = a.ann_vol > 0.55 ? `a very volatile ${noun}` : a.ann_vol > 0.3 ? `a moderately volatile ${noun}` : `a steady ${noun}`;
  $("bottom-line").innerHTML = `<b>Bottom line:</b> ${dispSym(a.symbol)} is ${wild} in ${dir}${nearHigh} — ${a.health >= 60 ? "in favour with buyers right now." : a.health >= 40 ? "the picture is mixed." : "out of favour right now."}`;
  const h = $("health");
  h.textContent = a.health;
  h.style.color = a.health >= 60 ? "var(--green)" : a.health >= 40 ? "var(--gold)" : "var(--red)";
  const r = $("risk");
  r.textContent = a.risk;
  r.style.color = a.risk === "Wild" ? "var(--red)" : a.risk === "Normal" ? "var(--gold)" : "var(--green)";
  $("bullets").innerHTML = a.bullets
    .map((b) => {
      const i = b.indexOf(":");
      return `<li>${i > 0 && i < 40 ? `<b>${b.slice(0, i)}:</b>${b.slice(i + 1)}` : b}</li>`;
    })
    .join("");
}

/* ------------------------------------------------------------ canvas chart */
function smaSeries(closes, period) {
  const out = new Array(closes.length).fill(null);
  let acc = 0;
  for (let i = 0; i < closes.length; i++) {
    acc += closes[i];
    if (i >= period) acc -= closes[i - period];
    if (i >= period - 1) out[i] = acc / period;
  }
  return out;
}

function drawChart() {
  const canvas = $("chart");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  if (!W || !H) return;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const all = state.candles;
  if (!all.length) return;
  const data = all.slice(-state.days);
  const closesAll = all.map((c) => c.close);
  const s20All = smaSeries(closesAll, 20), s50All = smaSeries(closesAll, 50);
  const off = all.length - data.length;

  const PAD_R = 56, PAD_T = 10;
  const coneFrac = 0.18;                       // right space for forecast cone
  const priceH = H * 0.62, volH = H * 0.14, rsiH = H * 0.16, axisH = H * 0.08;
  const plotW = (W - PAD_R) * (1 - coneFrac);
  const coneW = (W - PAD_R) * coneFrac;

  const a = state.analysis?.analysis || {};
  const vol = a.ann_vol || 0.4;
  const lastClose = data[data.length - 1].close;
  const coneSteps = 30;
  const drift = a.trend === "up" ? 0.25 : a.trend === "down" ? -0.25 : 0;
  let coneTop = lastClose, coneBot = lastClose;
  for (let i = 1; i <= coneSteps; i++) {
    const t = i / 252;
    coneTop = Math.max(coneTop, lastClose * Math.exp(drift * t + 1.3 * vol * Math.sqrt(t)));
    coneBot = Math.min(coneBot, lastClose * Math.exp(drift * t - 1.3 * vol * Math.sqrt(t)));
  }
  let lo = Math.min(...data.map((c) => c.low), coneBot);
  let hi = Math.max(...data.map((c) => c.high), coneTop);
  const span = hi - lo || 1;
  lo -= span * 0.05; hi += span * 0.05;

  const x = (i) => (i + 0.5) * (plotW / data.length);
  const y = (p) => PAD_T + (1 - (p - lo) / (hi - lo)) * (priceH - PAD_T);

  /* grid + price axis */
  ctx.strokeStyle = "#141a26"; ctx.fillStyle = "#5b6678"; ctx.font = "10px monospace"; ctx.textAlign = "left";
  const stepsAxis = 5;
  for (let i = 0; i <= stepsAxis; i++) {
    const p = lo + ((hi - lo) * i) / stepsAxis;
    const yy = y(p);
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(W - PAD_R, yy); ctx.stroke();
    ctx.fillText(fmt(p, p < 10 ? 2 : 0), W - PAD_R + 6, yy + 3);
  }

  /* time axis labels (month names) */
  ctx.textAlign = "center";
  let lastMonth = -1;
  data.forEach((c, i) => {
    const d = new Date(c.time * 1000);
    if (d.getMonth() !== lastMonth) {
      lastMonth = d.getMonth();
      if (i > 3)
        ctx.fillText(d.toLocaleString("en", { month: "short" }), x(i), priceH + volH + rsiH + 14);
    }
  });

  /* volume bars (forex has no volume — guard against divide-by-zero) */
  const maxV = Math.max(...data.map((c) => c.volume), 1);
  data.forEach((c, i) => {
    ctx.fillStyle = c.close >= c.open ? "rgba(47,213,135,0.45)" : "rgba(244,83,110,0.45)";
    const h = (c.volume / maxV) * (volH - 6);
    ctx.fillRect(x(i) - Math.max((plotW / data.length) * 0.3, 0.5), priceH + (volH - h), Math.max((plotW / data.length) * 0.6, 1), h);
  });

  /* RSI panel */
  const rsiTop = priceH + volH;
  const rsiVals = rsiSeries(closesAll, 14).slice(off);
  ctx.strokeStyle = "#141a26";
  [30, 70].forEach((lvl) => {
    const yy = rsiTop + (1 - lvl / 100) * rsiH;
    ctx.beginPath(); ctx.setLineDash([3, 3]); ctx.moveTo(0, yy); ctx.lineTo(plotW, yy); ctx.stroke(); ctx.setLineDash([]);
  });
  ctx.strokeStyle = "#4f8ff7"; ctx.lineWidth = 1; ctx.beginPath();
  let started = false;
  rsiVals.forEach((v, i) => {
    if (v == null) return;
    const yy = rsiTop + (1 - v / 100) * rsiH;
    if (!started) { ctx.moveTo(x(i), yy); started = true; } else ctx.lineTo(x(i), yy);
  });
  ctx.stroke();

  /* candles */
  const cw = Math.max((plotW / data.length) * 0.6, 1.5);
  data.forEach((c, i) => {
    const up = c.close >= c.open;
    ctx.strokeStyle = ctx.fillStyle = up ? "#2fd587" : "#f4536e";
    ctx.beginPath(); ctx.moveTo(x(i), y(c.high)); ctx.lineTo(x(i), y(c.low)); ctx.stroke();
    const top = y(Math.max(c.open, c.close)), bh = Math.max(Math.abs(y(c.open) - y(c.close)), 1);
    ctx.fillRect(x(i) - cw / 2, top, cw, bh);
  });

  /* SMA lines */
  const drawLine = (series, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 1.4; ctx.beginPath();
    let on = false;
    series.slice(off).forEach((v, i) => {
      if (v == null) return;
      if (!on) { ctx.moveTo(x(i), y(v)); on = true; } else ctx.lineTo(x(i), y(v));
    });
    ctx.stroke(); ctx.lineWidth = 1;
  };
  drawLine(s20All, "#e7b941");
  drawLine(s50All, "#8f7df7");

  /* forecast cone */
  const cx0 = plotW, y0 = y(lastClose);
  ctx.fillStyle = "rgba(231,185,65,0.07)";
  ctx.beginPath(); ctx.moveTo(cx0, y0);
  for (let i = 1; i <= coneSteps; i++) {
    const t = i / 252;
    ctx.lineTo(cx0 + (i / coneSteps) * coneW, y(lastClose * Math.exp(drift * t + 1.3 * vol * Math.sqrt(t))));
  }
  for (let i = coneSteps; i >= 1; i--) {
    const t = i / 252;
    ctx.lineTo(cx0 + (i / coneSteps) * coneW, y(lastClose * Math.exp(drift * t - 1.3 * vol * Math.sqrt(t))));
  }
  ctx.closePath(); ctx.fill();
  /* cone median */
  ctx.strokeStyle = "#e7b941"; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(cx0, y0);
  for (let i = 1; i <= coneSteps; i++) {
    const t = i / 252;
    ctx.lineTo(cx0 + (i / coneSteps) * coneW, y(lastClose * Math.exp(drift * t)));
  }
  ctx.stroke();

  /* last-price dashed line + tag */
  ctx.strokeStyle = "#e7b941"; ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(W - PAD_R, y0); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = "#e7b941"; ctx.fillRect(W - PAD_R, y0 - 8, PAD_R, 16);
  ctx.fillStyle = "#000"; ctx.textAlign = "center";
  ctx.fillText(fmt(lastClose, lastClose < 10 ? 2 : 2), W - PAD_R / 2, y0 + 3);
}

function rsiSeries(values, period) {
  const out = new Array(values.length).fill(null);
  if (values.length <= period) return out;
  let g = 0, l = 0;
  for (let i = 1; i <= period; i++) {
    const d = values[i] - values[i - 1];
    g += Math.max(d, 0); l += Math.max(-d, 0);
  }
  let ag = g / period, al = l / period;
  const val = () => (al === 0 ? 100 : 100 - 100 / (1 + ag / al));
  out[period] = val();
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    ag = (ag * (period - 1) + Math.max(d, 0)) / period;
    al = (al * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = val();
  }
  return out;
}

/* ------------------------------------------------------- economic calendar */
async function loadCalendar() {
  let cal;
  try { cal = await api("/api/calendar"); } catch { return; }
  $("cal-src").textContent = cal.source === "mock" ? "DEMO" : "LIVE";
  $("cal-src").className = `chip ${cal.source === "mock" ? "" : "blue"}`;
  const now = Date.now() / 1000;
  // upcoming events only (keep ones from the last hour so "just released" stays visible)
  const events = cal.events.filter((e) => e.ts > now - 3600).slice(0, 20);
  const dayName = (ts) => {
    const d = new Date(ts * 1000), today = new Date();
    const tomorrow = new Date(today.getTime() + 86400000);
    if (d.toDateString() === today.toDateString()) return "TODAY";
    if (d.toDateString() === tomorrow.toDateString()) return "TOMORROW";
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }).toUpperCase();
  };
  let html = "", lastDay = "";
  for (const e of events) {
    const day = dayName(e.ts);
    if (day !== lastDay) { html += `<div class="cal-day">${day}</div>`; lastDay = day; }
    const t = e.all_day ? "All day" : new Date(e.ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    const soon = !e.all_day && e.ts > now && e.ts - now < 7200 && e.impact === "High" ? " soon" : "";
    const fc = e.forecast ? `F ${e.forecast}` : "";
    const pv = e.previous ? ` · P ${e.previous}` : "";
    html += `<div class="cal-row${soon}">
      <span class="cal-time">${t}</span>
      <span class="cal-imp imp-${(e.impact || "none").toLowerCase()}"></span>
      <span class="cal-ccy">${e.currency}</span>
      <span class="cal-title" title="${escapeHtml(e.title)}">${escapeHtml(e.title)}</span>
      <span class="cal-fc">${fc}${pv}</span>
    </div>`;
  }
  $("calendar").innerHTML = html || `<div class="muted small">No upcoming events this week.</div>`;
}

/* -------------------------------------------------------------- bot wiring */
async function toggleBot() {
  const status = await api(`/api/bot/${state.botRunning ? "stop" : "start"}`, { method: "POST" });
  setBotState(status.running);
}

function setBotState(running) {
  state.botRunning = running;
  const btn = $("btn-bot");
  btn.textContent = running ? "STOP AUTO-TRADER" : "START AUTO-TRADER";
  btn.className = `bot-btn ${running ? "stop" : "start"}`;
  $("bot-live").textContent = running ? "LIVE" : "OFF";
  $("bot-live").className = `live-pill ${running ? "on" : "off"}`;
  const badge = $("botlog-badge");
  badge.className = `badge ${running ? "on" : "off"}`;
  badge.innerHTML = `<i class="dot"></i> BOT ${running ? "LIVE" : "OFF"}`;
  $("bot-dot").className = `dot ${running ? "green" : "blue"}`;
}

function renderPortfolio(p) {
  state.portfolio = p;
  const pl = p.realized_pnl + p.unrealized_pnl;
  for (const id of ["bot-pl", "footer-pl"]) {
    const el = $(id);
    el.textContent = `${pl >= 0 ? "+" : "-"}$${fmt(Math.abs(pl), 2)}`;
    el.classList.toggle("neg", pl < 0);
  }
  $("holding").textContent = `${p.positions.length}`;
  $("trade-count").textContent = `${p.trades.length} trades`;
  $("held-symbols").textContent = p.positions.map((x) => dispSym(x.symbol)).join(" · ");
}

function addLog(ev) {
  const box = $("log-lines");
  const div = document.createElement("div");
  div.className = `log-line ${ev.kind || "info"}`;
  const t = new Date(ev.ts * 1000).toLocaleTimeString("en-GB");
  div.innerHTML = `<span class="log-time">${t}</span>${escapeHtml(ev.msg)}`;
  box.appendChild(div);
  while (box.children.length > 300) box.removeChild(box.firstChild);
  box.parentElement.scrollTop = box.parentElement.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "log") addLog(ev);
    else if (ev.type === "portfolio") renderPortfolio(ev.data);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

/* ---------------------------------------------------------------- backtest */
async function openBacktest() {
  if (!state.symbol) return;
  const bt = await api(`/api/backtest/${encodeURIComponent(state.symbol)}`, { method: "POST" });
  $("bt-symbol").textContent = dispSym(bt.symbol);
  $("bt-note").textContent = bt.note;
  const stats = [
    [`${(bt.strategy_return * 100).toFixed(0)}%`, "Strategy", bt.strategy_return >= 0 ? "var(--green)" : "var(--red)"],
    [`${(bt.buy_hold_return * 100).toFixed(0)}%`, "Buy & hold", bt.buy_hold_return >= 0 ? "var(--green)" : "var(--red)"],
    [`${(bt.win_rate * 100).toFixed(0)}%`, "Win rate", "var(--text)"],
    [`${bt.trades}`, "Trades", "var(--text)"],
    [`${(bt.max_drawdown * 100).toFixed(0)}%`, "Max drop", "var(--red)"],
  ];
  $("bt-stats").innerHTML = stats
    .map(([v, k, c]) => `<div class="bt-stat"><div class="v" style="color:${c}">${v}</div><div class="k">${k}</div></div>`)
    .join("");
  const edge = bt.edge;
  $("bt-verdict").textContent =
    edge >= 0
      ? `The rule strategy beat buy-and-hold by ${(edge * 100).toFixed(0)}% over this window.`
      : `The rule strategy lagged buy-and-hold by ${(-edge * 100).toFixed(0)}% over this window.`;
  $("bt-verdict").style.color = edge >= 0 ? "var(--green)" : "var(--red)";
  drawBacktest(bt.equity_curve);
  $("modal").classList.remove("hidden");
}

function drawBacktest(curve) {
  const canvas = $("bt-chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (!curve.length) return;
  const vals = curve.flatMap((p) => [p.strategy, p.buy_hold]);
  const lo = Math.min(...vals) * 0.97, hi = Math.max(...vals) * 1.03;
  const x = (i) => (i / (curve.length - 1)) * (W - 60);
  const y = (v) => 10 + (1 - (v - lo) / (hi - lo)) * (H - 40);
  ctx.strokeStyle = "#1c2230"; ctx.fillStyle = "#5b6678"; ctx.font = "10px monospace";
  [lo, (lo + hi) / 2, hi].forEach((v) => {
    ctx.beginPath(); ctx.moveTo(0, y(v)); ctx.lineTo(W - 60, y(v)); ctx.stroke();
    ctx.fillText(fmt(v, 0), W - 55, y(v) + 3);
  });
  const line = (key, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = key === "strategy" ? 1.8 : 1; ctx.beginPath();
    curve.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p[key])) : ctx.moveTo(x(i), y(p[key]))));
    ctx.stroke();
  };
  line("buy_hold", "#9aa7bd");
  line("strategy", "#e7b941");
  /* month labels */
  ctx.fillStyle = "#5b6678"; ctx.textAlign = "center";
  let lastM = -1;
  curve.forEach((p, i) => {
    const d = new Date(p.time * 1000);
    if (d.getMonth() !== lastM && i % Math.ceil(curve.length / 6) === 0) {
      lastM = d.getMonth();
      ctx.fillText(d.toLocaleString("en", { month: "short", year: "2-digit" }), x(i), H - 8);
    }
  });
  ctx.textAlign = "left";
}

/* ------------------------------------------------------------------- init */
async function init() {
  await loadConfig();
  await loadWatchlist();
  const status = await api("/api/bot/status");
  setBotState(status.running);
  renderPortfolio(await api("/api/portfolio"));
  loadCalendar();
  setInterval(loadCalendar, 30 * 60 * 1000); // calendar refreshes half-hourly
  connectWS();

  $("btn-bot").onclick = toggleBot;
  $("btn-backtest").onclick = openBacktest;
  document.querySelectorAll(".wl-tab").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".wl-tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.tab = b.dataset.class;
      renderWatchlist();
      // jump the chart to the first symbol of the tab if the current one doesn't belong
      const first = state.watchlist.find((w) => (w.asset_class || assetClass(w.symbol)) === state.tab);
      if (first && (!state.symbol || assetClass(state.symbol) !== state.tab)) selectSymbol(first.symbol);
    };
  });
  $("modal-close").onclick = () => $("modal").classList.add("hidden");
  $("modal").onclick = (e) => { if (e.target === $("modal")) $("modal").classList.add("hidden"); };
  document.querySelectorAll(".tf[data-days]").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".tf[data-days]").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.days = Math.min(Number(b.dataset.days), state.candles.length);
      drawChart();
    };
  });
  window.addEventListener("resize", drawChart);

  /* periodic refresh of quotes & analysis */
  setInterval(loadWatchlist, 8000);
  setInterval(async () => {
    if (!state.symbol) return;
    state.analysis = await api(`/api/analysis/${encodeURIComponent(state.symbol)}`);
    renderTopQuote(); renderStats(); renderPlainEnglish();
  }, 10000);
}

init().catch((e) => console.error(e));
