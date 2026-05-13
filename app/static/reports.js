/**
 * reports.js — Fortress Dashboard
 * Batch evaluations, trade reports, position monitor, and Reports tab logic.
 * Depends on helpers from app.js: el, fmt, apiFetch, authFetch, escapeHtml, navigateToTab.
 */
"use strict";

// ─── Shared helpers ────────────────────────────────────────────────────────────
function rptShortExp(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(-2)}`;
  } catch { return iso; }
}

function rptVerdictPill(v) {
  const map = {
    PROCEED: "pill-success", PASS: "pill-success",
    BLOCKED: "pill-blocked", FAIL: "pill-blocked",
    WATCH: "pill-fair", ACT: "pill-blocked", ACT_IMMEDIATELY: "pill-blocked",
    URGENT: "pill-blocked", WARNING: "pill-fair", APPROACHING: "pill-info",
    NONE: "pill-mute", SAFE: "pill-mute",
    PRIME_ENTRY: "pill-prime", CONDITIONAL: "pill-fair", EVALUATE: "pill-info",
    NEW_ENTRY: "pill-prime", ADD_TO_POSITION: "pill-info",
    ROLL: "pill-fair", CLOSE: "pill-blocked", CLOSE_FOR_PROFIT: "pill-success",
    POST_EARNINGS_PLAYBOOK: "pill-info",
  };
  const cls = map[v] || "pill-mute";
  return el("span", { class: "pill " + cls + " pill-large" }, (v || "—").replace(/_/g, " "));
}

function rptDotClass(v) {
  if (["ACT_IMMEDIATELY","ACT","BLOCKED","FAIL","URGENT"].includes(v)) return "dot-red";
  if (["WATCH","WARNING","APPROACHING","CONDITIONAL"].includes(v)) return "dot-amber";
  if (["PROCEED","PASS","SAFE","NONE","PRIME_ENTRY","NEW_ENTRY"].includes(v)) return "dot-green";
  return "dot-gray";
}

function rptFmtPrice(v) {
  return v == null ? "—" : "$" + Number(v).toFixed(2);
}

function rptFmtPct(v) {
  return v == null ? "—" : Number(v).toFixed(1) + "%";
}

function rptSummaryBadges(summary) {
  const badges = [];
  for (const [k, v] of Object.entries(summary || {})) {
    if (typeof v === "number") {
      const cls = (k.includes("act") || k.includes("urgent") || k.includes("blocked") || k.includes("fail"))
        ? "pill-blocked"
        : (k.includes("warn") || k.includes("watch") || k.includes("approaching"))
          ? "pill-fair"
          : (k.includes("proceed") || k.includes("pass") || k.includes("safe") || k.includes("none"))
            ? "pill-mute"
            : "pill-info";
      badges.push(el("span", { class: "pill " + cls }, `${k.replace(/_/g, " ")}: ${v}`));
    } else if (typeof v === "string") {
      badges.push(el("span", { class: "pill pill-mute" }, `${k.replace(/_/g, " ")}: ${v}`));
    }
  }
  const row = el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;" });
  badges.forEach(b => row.appendChild(b));
  return row;
}

// ─── Batch stop-loss scan (Manage tab, item B) ─────────────────────────────────
document.getElementById("batch-stop-loss-run")?.addEventListener("click", async () => {
  const target = document.getElementById("batch-stop-loss-result");
  if (!target) return;
  target.innerHTML = '<div class="loading">Scanning all positions for stop-loss signals…</div>';
  try {
    const res = await authFetch("/api/manage/stop_loss_all");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    target.appendChild(rptSummaryBadges(data.summary));

    if (!data.positions || !data.positions.length) {
      target.appendChild(el("p", { class: "empty-state" }, "No positions to evaluate."));
      return;
    }

    const table = el("table", { class: "matrix-table" });
    table.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Ticker"), el("th", {}, "Strategy"), el("th", {}, "Expiry"),
      el("th", {}, "Verdict"), el("th", {}, "Signals"), el("th", {}, "Action")
    )));
    const tbody = el("tbody");
    for (const r of data.positions) {
      const verdictCls = rptDotClass(r.verdict);
      tbody.appendChild(el("tr", {},
        el("td", {}, el("span", { class: "ticker" }, r.ticker)),
        el("td", {}, r.strategy || "—"),
        el("td", {}, rptShortExp(r.expiry)),
        el("td", {}, el("span", { class: "pill " + (
          r.verdict === "ACT_IMMEDIATELY" ? "pill-blocked" :
          r.verdict === "ACT" ? "pill-blocked" :
          r.verdict === "WATCH" ? "pill-fair" : "pill-mute"
        ) }, r.verdict || "—")),
        el("td", { class: "muted small" }, (r.signals || []).join(", ") || "—"),
        el("td", {}, el("button", {
          class: "action-cta action-cta-small",
          onclick: `navigateToManageEval('${r.synthesized_id}', 'stop_loss')`
        }, "Evaluate →"))
      ));
    }
    table.appendChild(tbody);
    target.appendChild(table);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Batch stop-loss scan failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Batch roll scan (Manage tab, item H) ──────────────────────────────────────
document.getElementById("batch-roll-run")?.addEventListener("click", async () => {
  const target = document.getElementById("batch-roll-result");
  if (!target) return;
  target.innerHTML = '<div class="loading">Scanning all short positions for roll candidates…</div>';
  try {
    const res = await authFetch("/api/manage/roll_all");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    target.appendChild(rptSummaryBadges(data.summary));

    if (!data.positions || !data.positions.length) {
      target.appendChild(el("p", { class: "empty-state" }, "No roll candidates found."));
      return;
    }

    const table = el("table", { class: "matrix-table" });
    table.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Ticker"), el("th", {}, "Strategy"), el("th", {}, "Expiry"),
      el("th", {}, "DTE"), el("th", {}, "Δ"), el("th", {}, "Urgency"),
      el("th", {}, "Reasons"), el("th", {}, "")
    )));
    const tbody = el("tbody");
    for (const r of data.positions) {
      const urgCls = r.urgency === "URGENT" ? "pill-blocked"
        : r.urgency === "WARNING" ? "pill-fair"
        : r.urgency === "APPROACHING" ? "pill-info" : "pill-mute";
      tbody.appendChild(el("tr", {},
        el("td", {}, el("span", { class: "ticker" }, r.ticker)),
        el("td", {}, r.strategy || "—"),
        el("td", {}, rptShortExp(r.expiry)),
        el("td", {}, r.current_dte != null ? r.current_dte + "d" : "—"),
        el("td", {}, r.current_delta != null ? Number(r.current_delta).toFixed(2) : "—"),
        el("td", {}, el("span", { class: "pill " + urgCls }, r.urgency || "—")),
        el("td", { class: "muted small" }, (r.reasons || []).join("; ") || "—"),
        el("td", {}, r.roll_needed ? el("button", {
          class: "action-cta action-cta-small",
          onclick: `navigateToManageEval('${r.synthesized_id}', 'roll')`
        }, "Roll →") : el("span", { class: "muted small" }, "—"))
      ));
    }
    table.appendChild(tbody);
    target.appendChild(table);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Batch roll scan failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Position monitor → auto-alerts (Manage tab, item E) ──────────────────────
document.getElementById("position-monitor-run")?.addEventListener("click", async () => {
  const target = document.getElementById("position-monitor-result");
  if (!target) return;
  target.innerHTML = '<div class="loading">Running position monitor…</div>';
  try {
    const res = await authFetch("/api/manage/monitor_alerts", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    if (data.new_alerts_created === 0) {
      target.appendChild(el("p", { class: "empty-state" }, "✓ No new alerts — all positions within thresholds."));
      return;
    }

    target.appendChild(el("p", { class: "verdict-action" },
      `${data.new_alerts_created} new alert(s) created and written to the Alerts panel.`));

    // Show live alerts banner
    const banner = document.getElementById("live-alerts-banner");
    const bannerText = document.getElementById("live-alerts-text");
    if (banner && bannerText) {
      bannerText.textContent = `Position monitor: ${data.new_alerts_created} alert(s) require attention.`;
      banner.style.display = "flex";
    }

    const table = el("table", { class: "matrix-table" });
    table.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Ticker"), el("th", {}, "Severity"), el("th", {}, "Message")
    )));
    const tbody = el("tbody");
    for (const a of data.alerts || []) {
      const sevCls = a.severity === "critical" ? "pill-blocked"
        : a.severity === "warn" ? "pill-fair" : "pill-info";
      tbody.appendChild(el("tr", {},
        el("td", {}, el("span", { class: "ticker" }, a.ticker)),
        el("td", {}, el("span", { class: "pill " + sevCls }, a.severity)),
        el("td", { class: "small" }, a.message)
      ));
    }
    table.appendChild(tbody);
    target.appendChild(table);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Position monitor failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// Helper: navigate to Manage tab and trigger a single-position evaluator
window.navigateToManageEval = function(posId, action) {
  navigateToTab("manage");
  setTimeout(() => {
    const sel = document.getElementById(action === "roll" ? "roll-position" : "stop-loss-position");
    const btn = document.getElementById(action === "roll" ? "roll-run" : "stop-loss-run");
    if (sel) sel.value = posId;
    if (btn) btn.click();
  }, 300);
};

// ─── Reports tab initialisation ────────────────────────────────────────────────
let _reportsInitialised = false;
window.initReports = async function() {
  if (_reportsInitialised) return;
  _reportsInitialised = true;
  await _fillReportPickers();
};

async function _fillReportPickers() {
  const data = await apiFetch("/api/manage/positions");
  const positions = (data && data.positions) || [];
  const universe = await apiFetch("/api/universe");
  const tickers = [];
  if (universe) {
    for (const key of ["tier1", "tier2", "macro"]) {
      const arr = universe[key];
      if (Array.isArray(arr)) arr.forEach(t => { if (t && !tickers.includes(t.toUpperCase())) tickers.push(t.toUpperCase()); });
    }
  }

  for (const selId of ["rpt-new-ticker", "rpt-buy-ticker"]) {
    const sel = document.getElementById(selId);
    if (!sel) continue;
    sel.innerHTML = '<option value="">— select —</option>';
    for (const t of tickers) {
      sel.appendChild(el("option", { value: t }, t));
    }
  }

  for (const selId of ["rpt-roll-position", "rpt-sell-position"]) {
    const sel = document.getElementById(selId);
    if (!sel) continue;
    sel.innerHTML = '<option value="">— select —</option>';
    for (const p of positions) {
      const label = `${p.ticker} — ${p.strategy || "—"} ${p.short_strike ? p.short_strike + "c" : ""} ${rptShortExp(p.expiry)}`.trim();
      sel.appendChild(el("option", { value: p.id }, label));
    }
  }
}

// ─── Pre-trade matrix — all universe tickers (Reports tab, item C/K) ───────────
document.getElementById("pretrade-all-run")?.addEventListener("click", async () => {
  const target = document.getElementById("pretrade-all-result");
  if (!target) return;
  target.innerHTML = '<div class="loading">Running pre-trade gates across all universe tickers…</div>';
  try {
    const res = await authFetch("/api/manage/pretrade_all");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    target.appendChild(rptSummaryBadges(data.summary));

    if (!data.results || !data.results.length) {
      target.appendChild(el("p", { class: "empty-state" }, "No universe tickers found."));
      return;
    }

    const table = el("table", { class: "matrix-table" });
    table.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Ticker"), el("th", {}, "Verdict"), el("th", {}, "Earnings"),
      el("th", {}, "Conc %"), el("th", {}, "VIX"), el("th", {}, "Failures"), el("th", {}, "")
    )));
    const tbody = el("tbody");
    for (const r of data.results) {
      const vCls = r.verdict === "PROCEED" ? "pill-success" : "pill-blocked";
      tbody.appendChild(el("tr", {},
        el("td", {}, el("span", { class: "ticker" }, r.ticker)),
        el("td", {}, el("span", { class: "pill " + vCls }, r.verdict)),
        el("td", {}, r.days_to_earnings != null
          ? el("span", { class: r.earnings_state === "blackout" ? "pill pill-blocked" : r.earnings_state === "approaching" ? "pill pill-fair" : "pill pill-mute" },
              r.days_to_earnings + "d")
          : el("span", { class: "muted small" }, "—")),
        el("td", {}, rptFmtPct(r.concentration_pct)),
        el("td", {}, r.vix != null ? r.vix.toFixed(1) : "—"),
        el("td", { class: "muted small" }, (r.failures || []).join(", ") || "—"),
        el("td", {}, r.verdict === "PROCEED" ? el("button", {
          class: "action-cta action-cta-small",
          onclick: `_openNewTradeReport('${r.ticker}')`
        }, "Report →") : el("span", { class: "muted small" }, "—"))
      ));
    }
    table.appendChild(tbody);
    target.appendChild(table);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Pre-trade matrix failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

function _openNewTradeReport(ticker) {
  const sel = document.getElementById("rpt-new-ticker");
  if (sel) sel.value = ticker;
  document.getElementById("rpt-new-run")?.click();
  document.getElementById("rpt-new-result")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ─── New trade evaluation report ──────────────────────────────────────────────
document.getElementById("rpt-new-run")?.addEventListener("click", async () => {
  const target = document.getElementById("rpt-new-result");
  if (!target) return;
  const ticker = document.getElementById("rpt-new-ticker")?.value?.trim()?.toUpperCase();
  const strategy = document.getElementById("rpt-new-strategy")?.value;
  const qty = parseInt(document.getElementById("rpt-new-qty")?.value || "1");
  if (!ticker) { target.innerHTML = '<p class="warn">Select a ticker first.</p>'; return; }
  target.innerHTML = '<div class="loading">Generating new trade evaluation report…</div>';
  try {
    // Fetch pre-trade gate + IV data + briefing in parallel
    const [gateRes, briefingData, candidatesData] = await Promise.all([
      authFetch(`/api/manage/pre_trade_check?ticker=${encodeURIComponent(ticker)}`),
      apiFetch("/api/briefing"),
      apiFetch("/api/candidates"),
    ]);
    if (!gateRes.ok) throw new Error(await gateRes.text());
    const gate = await gateRes.json();

    target.innerHTML = "";

    // Header
    const overallPass = gate.all_passed;
    target.appendChild(el("div", { class: "verdict-headline" },
      el("div", {},
        el("h3", { class: "muted-h3" }, `${ticker} — ${strategy} × ${qty} contract(s)`),
        el("p", { class: "muted small" }, gate.verdict_reason || "")
      ),
      rptVerdictPill(gate.verdict)
    ));

    // Gate checklist
    const gateList = el("ul", { class: "signal-list" });
    for (const [name, g] of Object.entries(gate.gates || {})) {
      const dot = g.passed ? "dot-green" : "dot-red";
      gateList.appendChild(el("li", { class: "signal-row" },
        el("span", { class: "dot " + dot }),
        el("strong", {}, name.replace(/_/g, " ")),
        el("span", { class: "pill " + (g.passed ? "pill-mute" : "pill-blocked"), style: "margin-left:6px" }, g.passed ? "PASS" : "FAIL"),
        el("p", { class: "muted small" }, g.detail || "")
      ));
    }
    target.appendChild(el("h4", { class: "muted-h3", style: "margin:12px 0 6px" }, "Pre-trade gates"));
    target.appendChild(gateList);

    // Macro context
    const macro = (briefingData && briefingData.macro_regime) || {};
    const macroCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    macroCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "Macro context"));
    const macroMeta = el("ul", { class: "meta-list" });
    macroMeta.appendChild(el("li", {}, "VIX: ", el("strong", {}, macro.vix != null ? macro.vix.toFixed(1) : "—")));
    macroMeta.appendChild(el("li", {}, "Regime: ", el("strong", {}, macro.regime || macro.vix_state || "—")));
    macroMeta.appendChild(el("li", {}, "Trend: ", el("strong", {}, macro.trend || "—")));
    macroCard.appendChild(macroMeta);
    target.appendChild(macroCard);

    // IV data from candidates
    const ivRow = (candidatesData && candidatesData.rows || []).find(r => (r.ticker || "").toUpperCase() === ticker);
    if (ivRow) {
      const ivCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
      ivCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "IV / premium data"));
      const ivMeta = el("ul", { class: "meta-list" });
      ivMeta.appendChild(el("li", {}, "IV Rank: ", el("strong", {}, ivRow.iv_rank != null ? ivRow.iv_rank.toFixed(1) + "%" : "—")));
      ivMeta.appendChild(el("li", {}, "IV Pct: ", el("strong", {}, ivRow.iv_pct != null ? ivRow.iv_pct.toFixed(1) + "%" : "—")));
      ivMeta.appendChild(el("li", {}, "Spot: ", el("strong", {}, rptFmtPrice(ivRow.spot))));
      ivMeta.appendChild(el("li", {}, "Earnings: ", el("strong", {}, ivRow.earnings_date || "—")));
      ivCard.appendChild(ivMeta);
      target.appendChild(ivCard);
    }

    // Order checklist
    if (overallPass) {
      const checkCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
      checkCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "§8 order checklist"));
      const steps = [
        `Pull live ${ticker} option chain from IBKR — verify bid/ask spread is tight.`,
        `Pull Clean Decision Chart from TradingView (D timeframe, 50/200 SMA, volume).`,
        `Confirm strategy: ${strategy} × ${qty} contract(s).`,
        `Select strikes using real bid/ask/delta + chart structure.`,
        `Verify limit price direction (credit vs debit) and magnitude vs mid.`,
        `Submit limit order at mid; walk patiently. After 10:00 ET / 16:00 Amsterdam.`,
        `Log the trade in Journal immediately after fill.`,
      ];
      const ol = el("ol", { class: "checklist" });
      steps.forEach(s => ol.appendChild(el("li", {}, s)));
      checkCard.appendChild(ol);
      target.appendChild(checkCard);
    }
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>New trade report failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Roll evaluation report ────────────────────────────────────────────────────
document.getElementById("rpt-roll-run")?.addEventListener("click", async () => {
  const target = document.getElementById("rpt-roll-result");
  if (!target) return;
  const posId = document.getElementById("rpt-roll-position")?.value;
  if (!posId) { target.innerHTML = '<p class="warn">Select a position first.</p>'; return; }
  const dteLow = document.getElementById("rpt-roll-dte-low")?.value || 30;
  const dteHigh = document.getElementById("rpt-roll-dte-high")?.value || 45;
  const deltaLow = document.getElementById("rpt-roll-delta-low")?.value || 0.20;
  const deltaHigh = document.getElementById("rpt-roll-delta-high")?.value || 0.25;
  target.innerHTML = '<div class="loading">Generating roll evaluation report (fetching option chain)…</div>';
  try {
    const params = new URLSearchParams({
      target_dte_low: dteLow, target_dte_high: dteHigh,
      target_delta_low: deltaLow, target_delta_high: deltaHigh,
    });
    const res = await authFetch(`/api/manage/roll/${encodeURIComponent(posId)}?${params}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    const pos = data.position || {};
    target.appendChild(el("div", { class: "verdict-headline" },
      el("div", {},
        el("h3", { class: "muted-h3" }, `${pos.ticker || "—"} — Roll evaluation`),
        el("p", { class: "muted small" }, `Short ${pos.short_strike || "—"}c ${rptShortExp(pos.expiry)} · ${(data.candidates || []).length} candidate(s) found`)
      ),
      el("span", { class: "pill pill-info pill-large" }, `${(data.candidates || []).length} candidate${(data.candidates || []).length === 1 ? "" : "s"}`)
    ));

    if (data.error) {
      target.appendChild(el("div", { class: "error-banner" }, el("span", {}, "Chain error: " + data.error)));
      return;
    }

    // Current position meta
    const metaCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    metaCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "Current position"));
    const metaList = el("ul", { class: "meta-list" });
    metaList.appendChild(el("li", {}, "Strategy: ", el("strong", {}, pos.strategy || "—")));
    metaList.appendChild(el("li", {}, "Short strike: ", el("strong", {}, pos.short_strike || "—")));
    metaList.appendChild(el("li", {}, "Expiry: ", el("strong", {}, rptShortExp(pos.expiry))));
    metaList.appendChild(el("li", {}, "Spot: ", el("strong", {}, rptFmtPrice(data.spot))));
    metaList.appendChild(el("li", {}, "Current short mid: ", el("strong", {}, rptFmtPrice(data.current_short?.estimated_mid))));
    metaCard.appendChild(metaList);
    target.appendChild(metaCard);

    if (!data.candidates || !data.candidates.length) {
      target.appendChild(el("p", { class: "empty-state", style: "margin-top:12px" }, "No roll candidates in target band. Widen DTE/delta or check chain."));
    } else {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 8px" }, "Roll candidates"));
      const grid = el("div", { class: "candidates-grid" });
      for (const c of data.candidates) {
        const labelPill = c.label === "framework_match"
          ? el("span", { class: "pill pill-prime" }, "framework match")
          : c.label === "conservative"
            ? el("span", { class: "pill pill-info" }, "conservative")
            : el("span", { class: "pill pill-fair" }, "aggressive");
        const recBadge = c.recommended ? el("span", { class: "pill pill-success" }, "★ recommended") : null;
        const creditClass = (c.net_credit_total || 0) >= 0 ? "pos" : "neg";

        const card = el("div", { class: "candidate-card" + (c.recommended ? " candidate-rec" : "") },
          el("div", { class: "candidate-row" }, labelPill, recBadge),
          el("h3", {}, `$${c.strike} ${rptShortExp(c.expiry)}`),
          el("table", { class: "candidate-table" },
            el("tbody", {},
              el("tr", {}, el("td", { class: "muted small" }, "DTE"), el("td", { class: "num" }, `${c.dte}d`)),
              el("tr", {}, el("td", { class: "muted small" }, "Δ"), el("td", { class: "num" }, c.delta?.toFixed(2) || "—")),
              el("tr", {}, el("td", { class: "muted small" }, "IV"), el("td", { class: "num" }, c.iv != null ? (c.iv*100).toFixed(1)+"%" : "—")),
              el("tr", {}, el("td", { class: "muted small" }, "Mid"), el("td", { class: "num" }, c.mid != null ? "$"+c.mid.toFixed(2) : "—")),
              el("tr", {}, el("td", { class: "muted small" }, "Bid/Ask"), el("td", { class: "num" }, `$${(c.bid||0).toFixed(2)} / $${(c.ask||0).toFixed(2)}`)),
              el("tr", {}, el("td", { class: "muted small" }, "Net credit"), el("td", { class: "num " + creditClass },
                (c.net_credit_total >= 0 ? "+" : "") + "$" + Math.abs(c.net_credit_total || 0).toFixed(0)))
            )
          )
        );
        grid.appendChild(card);
      }
      target.appendChild(grid);

      if (data.ticket_text) {
        target.appendChild(el("h4", { class: "muted-h3", style: "margin-top:16px" }, "IBKR ticket"));
        target.appendChild(el("pre", { class: "ticket-text" }, data.ticket_text));
        const copyBtn = el("button", { class: "action-cta action-cta-small", style: "margin-top:8px" }, "Copy ticket");
        copyBtn.addEventListener("click", () => {
          navigator.clipboard.writeText(data.ticket_text).then(() => {
            copyBtn.textContent = "Copied ✓";
            setTimeout(() => { copyBtn.textContent = "Copy ticket"; }, 2000);
          });
        });
        target.appendChild(copyBtn);
      }
    }

    // Post-roll checklist
    const checkCard = el("div", { class: "phase4-result", style: "margin-top:14px;" });
    checkCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "Post-roll checklist"));
    const steps = [
      "Verify the recommended candidate against the live IBKR option chain.",
      "Confirm net credit is positive (roll for credit per Strategy §5).",
      "Check new expiry clears any upcoming earnings date by ≥ 10 days.",
      "Submit as a combo order (buy-to-close + sell-to-open) at mid.",
      "Log the roll in Journal immediately after fill.",
    ];
    const ol = el("ol", { class: "checklist" });
    steps.forEach(s => ol.appendChild(el("li", {}, s)));
    checkCard.appendChild(ol);
    target.appendChild(checkCard);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Roll report failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Buy / open position report ────────────────────────────────────────────────
document.getElementById("rpt-buy-run")?.addEventListener("click", async () => {
  const target = document.getElementById("rpt-buy-result");
  if (!target) return;
  const ticker = document.getElementById("rpt-buy-ticker")?.value?.trim()?.toUpperCase();
  const strategy = document.getElementById("rpt-buy-strategy")?.value;
  const credit = parseFloat(document.getElementById("rpt-buy-credit")?.value || "0");
  const qty = parseInt(document.getElementById("rpt-buy-qty")?.value || "1");
  if (!ticker) { target.innerHTML = '<p class="warn">Select a ticker first.</p>'; return; }
  target.innerHTML = '<div class="loading">Generating buy/open position report…</div>';
  try {
    const [gateRes, briefingData, candidatesData] = await Promise.all([
      authFetch(`/api/manage/pre_trade_check?ticker=${encodeURIComponent(ticker)}`),
      apiFetch("/api/briefing"),
      apiFetch("/api/candidates"),
    ]);
    if (!gateRes.ok) throw new Error(await gateRes.text());
    const gate = await gateRes.json();

    target.innerHTML = "";

    target.appendChild(el("div", { class: "verdict-headline" },
      el("div", {},
        el("h3", { class: "muted-h3" }, `${ticker} — ${strategy} × ${qty} — Buy/Open`),
        el("p", { class: "muted small" }, gate.verdict_reason || "")
      ),
      rptVerdictPill(gate.verdict)
    ));

    // Gate summary
    const gateList = el("ul", { class: "signal-list" });
    for (const [name, g] of Object.entries(gate.gates || {})) {
      const dot = g.passed ? "dot-green" : "dot-red";
      gateList.appendChild(el("li", { class: "signal-row" },
        el("span", { class: "dot " + dot }),
        el("strong", {}, name.replace(/_/g, " ")),
        el("span", { class: "pill " + (g.passed ? "pill-mute" : "pill-blocked"), style: "margin-left:6px" }, g.passed ? "PASS" : "FAIL"),
        el("p", { class: "muted small" }, g.detail || "")
      ));
    }
    target.appendChild(el("h4", { class: "muted-h3", style: "margin:12px 0 6px" }, "Pre-trade gates"));
    target.appendChild(gateList);

    // Sizing / margin impact
    const sizingCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    sizingCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "Sizing & margin impact"));
    const sizingMeta = el("ul", { class: "meta-list" });
    const totalCredit = credit > 0 ? credit * qty * 100 : null;
    sizingMeta.appendChild(el("li", {}, "Contracts: ", el("strong", {}, String(qty))));
    sizingMeta.appendChild(el("li", {}, "Credit/share: ", el("strong", {}, credit > 0 ? rptFmtPrice(credit) : "—")));
    sizingMeta.appendChild(el("li", {}, "Total credit: ", el("strong", {}, totalCredit != null ? "$" + totalCredit.toFixed(0) : "—")));
    sizingMeta.appendChild(el("li", {}, "Note: ", el("span", { class: "muted small" }, "Confirm margin impact in IBKR before submitting.")));
    sizingCard.appendChild(sizingMeta);
    target.appendChild(sizingCard);

    // IV data
    const ivRow = (candidatesData && candidatesData.rows || []).find(r => (r.ticker || "").toUpperCase() === ticker);
    if (ivRow) {
      const ivCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
      ivCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "IV / premium data"));
      const ivMeta = el("ul", { class: "meta-list" });
      ivMeta.appendChild(el("li", {}, "IV Rank: ", el("strong", {}, ivRow.iv_rank != null ? ivRow.iv_rank.toFixed(1) + "%" : "—")));
      ivMeta.appendChild(el("li", {}, "Spot: ", el("strong", {}, rptFmtPrice(ivRow.spot))));
      ivMeta.appendChild(el("li", {}, "Earnings: ", el("strong", {}, ivRow.earnings_date || "—")));
      ivCard.appendChild(ivMeta);
      target.appendChild(ivCard);
    }

    // Order checklist
    const checkCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    checkCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "§8 order checklist"));
    const steps = [
      `Pull live ${ticker} option chain from IBKR — verify bid/ask spread is tight.`,
      `Confirm strategy: ${strategy} × ${qty} contract(s) at ${credit > 0 ? rptFmtPrice(credit) + " credit/share" : "target credit TBD"}.`,
      `Select strikes using real bid/ask/delta + chart structure.`,
      `Verify limit price direction (credit) and magnitude vs mid.`,
      `Submit limit order at mid; walk patiently. After 10:00 ET / 16:00 Amsterdam.`,
      `Log the trade in Journal immediately after fill.`,
    ];
    const ol = el("ol", { class: "checklist" });
    steps.forEach(s => ol.appendChild(el("li", {}, s)));
    checkCard.appendChild(ol);
    target.appendChild(checkCard);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Buy report failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Sell / close position report ─────────────────────────────────────────────
document.getElementById("rpt-sell-run")?.addEventListener("click", async () => {
  const target = document.getElementById("rpt-sell-result");
  if (!target) return;
  const posId = document.getElementById("rpt-sell-position")?.value;
  const closePrice = parseFloat(document.getElementById("rpt-sell-price")?.value || "0");
  const qty = parseInt(document.getElementById("rpt-sell-qty")?.value || "1");
  if (!posId) { target.innerHTML = '<p class="warn">Select a position first.</p>'; return; }
  target.innerHTML = '<div class="loading">Generating sell/close report…</div>';
  try {
    const posData = await apiFetch("/api/manage/positions");
    const pos = (posData && posData.positions || []).find(p => p.id === posId);
    if (!pos) throw new Error("Position not found in cache.");

    target.innerHTML = "";

    target.appendChild(el("div", { class: "verdict-headline" },
      el("div", {},
        el("h3", { class: "muted-h3" }, `${pos.ticker} — Close / Sell × ${qty}`),
        el("p", { class: "muted small" }, `${pos.strategy || "—"} · ${pos.short_strike ? pos.short_strike + "c" : ""} ${rptShortExp(pos.expiry)}`)
      ),
      el("span", { class: "pill pill-info pill-large" }, "CLOSE EVAL")
    ));

    // P&L estimate
    const pnlCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    pnlCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "P&L estimate"));
    const pnlMeta = el("ul", { class: "meta-list" });
    const totalDebit = closePrice > 0 ? closePrice * qty * 100 : null;
    pnlMeta.appendChild(el("li", {}, "Close price/share: ", el("strong", {}, closePrice > 0 ? rptFmtPrice(closePrice) : "—")));
    pnlMeta.appendChild(el("li", {}, "Contracts to close: ", el("strong", {}, String(qty))));
    pnlMeta.appendChild(el("li", {}, "Total debit (cost to close): ", el("strong", {}, totalDebit != null ? "$" + totalDebit.toFixed(0) : "—")));
    pnlMeta.appendChild(el("li", {}, "Net liq %: ", el("strong", {}, rptFmtPct(pos.net_liq_pct))));
    pnlMeta.appendChild(el("li", {}, "Note: ", el("span", { class: "muted small" }, "Confirm actual P&L in IBKR Activity Statement before closing.")));
    pnlCard.appendChild(pnlMeta);
    target.appendChild(pnlCard);

    // Post-close checklist
    const checkCard = el("div", { class: "phase4-result", style: "margin-top:12px;" });
    checkCard.appendChild(el("h4", { class: "muted-h3", style: "margin-bottom:6px" }, "Post-close checklist"));
    const steps = [
      `Verify the close price (${closePrice > 0 ? rptFmtPrice(closePrice) : "TBD"}) against the live IBKR option chain mid.`,
      `Submit buy-to-close order at mid; walk patiently.`,
      `Confirm margin release in IBKR after fill.`,
      `Log the close in Journal immediately after fill (include realized P&L).`,
      `Review whether to redeploy capital into a new position (run New Trade report).`,
    ];
    const ol = el("ol", { class: "checklist" });
    steps.forEach(s => ol.appendChild(el("li", {}, s)));
    checkCard.appendChild(ol);
    target.appendChild(checkCard);
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Sell report failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Full book trade report ────────────────────────────────────────────────────
document.getElementById("full-report-run")?.addEventListener("click", async () => {
  const target = document.getElementById("full-report-result");
  if (!target) return;
  target.innerHTML = '<div class="loading">Generating full book trade report (this may take 15–30 seconds)…</div>';
  try {
    const res = await authFetch("/api/manage/trade_report");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    target.innerHTML = "";

    // Macro header
    const macro = data.macro || {};
    target.appendChild(el("div", { class: "verdict-headline" },
      el("div", {},
        el("h3", { class: "muted-h3" }, "Full Book Trade Report"),
        el("p", { class: "muted small" }, `As of ${new Date(data.as_of).toLocaleString()} · VIX ${macro.vix || "—"} (${macro.vix_state || "—"}) · Regime: ${macro.regime || "—"}`)
      ),
      el("span", { class: "pill pill-info pill-large" }, `${data.summary?.urgent_actions || 0} urgent action(s)`)
    ));

    target.appendChild(rptSummaryBadges(data.summary));

    // ── Stop-loss alerts ──
    if (data.stop_loss_alerts && data.stop_loss_alerts.length) {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 6px" },
        `🔴 Stop-loss alerts (${data.stop_loss_alerts.length})`));
      const table = el("table", { class: "matrix-table" });
      table.appendChild(el("thead", {}, el("tr", {},
        el("th", {}, "Ticker"), el("th", {}, "Verdict"), el("th", {}, "Action"), el("th", {}, "Signals")
      )));
      const tbody = el("tbody");
      for (const r of data.stop_loss_alerts) {
        const vCls = r.verdict === "ACT_IMMEDIATELY" ? "pill-blocked" : r.verdict === "ACT" ? "pill-blocked" : "pill-fair";
        tbody.appendChild(el("tr", {},
          el("td", {}, el("span", { class: "ticker" }, r.ticker)),
          el("td", {}, el("span", { class: "pill " + vCls }, r.verdict)),
          el("td", { class: "small" }, r.recommended_action || "—"),
          el("td", { class: "muted small" }, (r.signals || []).join(", ") || "—")
        ));
      }
      table.appendChild(tbody);
      target.appendChild(table);
    }

    // ── Roll candidates ──
    if (data.roll_candidates && data.roll_candidates.length) {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 6px" },
        `🟡 Roll candidates (${data.roll_candidates.length})`));
      const table = el("table", { class: "matrix-table" });
      table.appendChild(el("thead", {}, el("tr", {},
        el("th", {}, "Ticker"), el("th", {}, "Urgency"), el("th", {}, "DTE"), el("th", {}, "Reasons"), el("th", {}, "")
      )));
      const tbody = el("tbody");
      for (const r of data.roll_candidates) {
        const uCls = r.urgency === "URGENT" ? "pill-blocked" : r.urgency === "WARNING" ? "pill-fair" : "pill-info";
        tbody.appendChild(el("tr", {},
          el("td", {}, el("span", { class: "ticker" }, r.ticker)),
          el("td", {}, el("span", { class: "pill " + uCls }, r.urgency)),
          el("td", {}, r.current_dte != null ? r.current_dte + "d" : "—"),
          el("td", { class: "muted small" }, (r.reasons || []).join("; ") || "—"),
          el("td", {}, el("button", {
            class: "action-cta action-cta-small",
            onclick: `navigateToTab('reports'); setTimeout(()=>{ document.getElementById('rpt-roll-position').value='${r.synthesized_id}'; document.getElementById('rpt-roll-run').click(); }, 400);`
          }, "Roll report →"))
        ));
      }
      table.appendChild(tbody);
      target.appendChild(table);
    }

    // ── Entry candidates ──
    if (data.entry_candidates && data.entry_candidates.length) {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 6px" },
        `🟢 Entry candidates (${data.entry_candidates.length})`));
      const table = el("table", { class: "matrix-table" });
      table.appendChild(el("thead", {}, el("tr", {},
        el("th", {}, "Ticker"), el("th", {}, "Action"), el("th", {}, "IV Rank"), el("th", {}, "Earnings"), el("th", {}, "Conc %"), el("th", {}, "")
      )));
      const tbody = el("tbody");
      for (const r of data.entry_candidates) {
        tbody.appendChild(el("tr", {},
          el("td", {}, el("span", { class: "ticker" }, r.ticker)),
          el("td", {}, el("span", { class: "pill " + (r.action === "NEW_ENTRY" ? "pill-prime" : "pill-info") }, r.action?.replace(/_/g, " ") || "—")),
          el("td", {}, r.iv_rank != null ? r.iv_rank.toFixed(1) + "%" : "—"),
          el("td", {}, r.days_to_earnings != null ? r.days_to_earnings + "d" : "—"),
          el("td", {}, rptFmtPct(r.concentration_pct)),
          el("td", {}, el("button", {
            class: "action-cta action-cta-small",
            onclick: `_openNewTradeReport('${r.ticker}')`
          }, "Trade report →"))
        ));
      }
      table.appendChild(tbody);
      target.appendChild(table);
    }

    // ── Exit candidates ──
    if (data.exit_candidates && data.exit_candidates.length) {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 6px" },
        `💰 Exit / profit-take candidates (${data.exit_candidates.length})`));
      const table = el("table", { class: "matrix-table" });
      table.appendChild(el("thead", {}, el("tr", {},
        el("th", {}, "Ticker"), el("th", {}, "Strategy"), el("th", {}, "Net MV"), el("th", {}, "Note"), el("th", {}, "")
      )));
      const tbody = el("tbody");
      for (const r of data.exit_candidates) {
        tbody.appendChild(el("tr", {},
          el("td", {}, el("span", { class: "ticker" }, r.ticker)),
          el("td", {}, r.strategy || "—"),
          el("td", {}, r.net_market_value != null ? "$" + r.net_market_value.toFixed(0) : "—"),
          el("td", { class: "muted small" }, r.note || "—"),
          el("td", {}, el("button", {
            class: "action-cta action-cta-small",
            onclick: `navigateToTab('reports'); setTimeout(()=>{ document.getElementById('rpt-sell-position').value='${r.synthesized_id}'; document.getElementById('rpt-sell-run').click(); }, 400);`
          }, "Close report →"))
        ));
      }
      table.appendChild(tbody);
      target.appendChild(table);
    }

    // ── Post-earnings ──
    if (data.post_earnings_candidates && data.post_earnings_candidates.length) {
      target.appendChild(el("h4", { class: "muted-h3", style: "margin:14px 0 6px" },
        `📊 Post-earnings playbook candidates (${data.post_earnings_candidates.length})`));
      const table = el("table", { class: "matrix-table" });
      table.appendChild(el("thead", {}, el("tr", {},
        el("th", {}, "Ticker"), el("th", {}, "Days since earnings"), el("th", {}, "Price"), el("th", {}, "Note")
      )));
      const tbody = el("tbody");
      for (const r of data.post_earnings_candidates) {
        tbody.appendChild(el("tr", {},
          el("td", {}, el("span", { class: "ticker" }, r.ticker)),
          el("td", {}, r.days_since_earnings + "d"),
          el("td", {}, rptFmtPrice(r.current_price)),
          el("td", { class: "muted small" }, r.note || "—")
        ));
      }
      table.appendChild(tbody);
      target.appendChild(table);
    }

    if (!data.stop_loss_alerts?.length && !data.roll_candidates?.length &&
        !data.entry_candidates?.length && !data.exit_candidates?.length &&
        !data.post_earnings_candidates?.length) {
      target.appendChild(el("p", { class: "empty-state" }, "No action items found. Book is in good shape."));
    }
  } catch (e) {
    target.innerHTML = `<div class="error-banner"><span>Full report failed: ${escapeHtml(e.message)}</span></div>`;
  }
});

// ─── Live alerts banner auto-check on refreshAll ───────────────────────────────
// Hook into the global refreshAll cycle to silently check for critical alerts
// and show/update the live-alerts banner (item D).
(function() {
  const _origRefreshAll = window.refreshAll;
  if (typeof _origRefreshAll === "function") {
    window.refreshAll = async function() {
      await _origRefreshAll.apply(this, arguments);
      _checkLiveAlertsBanner();
    };
  }

  async function _checkLiveAlertsBanner() {
    try {
      const data = await apiFetch("/api/alerts");
      const alerts = (data && data.alerts) || [];
      const critical = alerts.filter(a => !a.snoozed && a.severity === "critical");
      const banner = document.getElementById("live-alerts-banner");
      const bannerText = document.getElementById("live-alerts-text");
      if (!banner) return;
      if (critical.length > 0) {
        if (bannerText) bannerText.textContent = `${critical.length} critical alert(s) require attention: ${critical.map(a => a.ticker).join(", ")}`;
        banner.style.display = "flex";
      } else {
        // Only hide if it was auto-shown (not manually dismissed — check if it was already hidden)
        // We leave user-dismissed state alone by not forcing display:none here
      }
    } catch { /* silent */ }
  }

  // Run once on load after token ready
  if (window._tokenReady) {
    window._tokenReady.then(() => _checkLiveAlertsBanner()).catch(() => {});
  }
})();

// ─── Journal auto-populate from last trade ────────────────────────────────────
// When the Journal tab is opened, pre-fill the ticker/action/description
// from the most recent position action if available (item G).
window.autoPopulateJournal = async function() {
  try {
    const positions = await apiFetch("/api/manage/positions");
    const pos = (positions && positions.positions || [])[0];
    if (!pos) return;
    const tickerEl = document.getElementById("jnl-ticker");
    if (tickerEl && !tickerEl.value) tickerEl.value = pos.ticker || "";
    const descEl = document.getElementById("jnl-description");
    if (descEl && !descEl.value) descEl.value = `${pos.strategy || ""} ${pos.short_strike ? pos.short_strike + "c" : ""} ${pos.expiry ? rptShortExp(pos.expiry) : ""}`.trim();
  } catch { /* silent */ }
};

// ─── Positions colour coding (item L) — patch renderPositions ─────────────────
// Wrap the global renderPositions to add colour-coded rows for delta/DTE/alert states.
(function() {
  const _origRenderPositions = window.renderPositions;
  if (typeof _origRenderPositions !== "function") return;
  window.renderPositions = function(data) {
    _origRenderPositions(data);
    // After render, apply colour classes to rows based on alert_state / delta_state
    setTimeout(() => {
      const rows = document.querySelectorAll("#positions-content table tbody tr");
      rows.forEach(row => {
        const tickerCell = row.querySelector(".ticker");
        if (!tickerCell) return;
        const ticker = tickerCell.textContent.trim().toUpperCase();
        // Find matching position in data
        const positions = (data && (data.positions || data)) || [];
        const pos = Array.isArray(positions)
          ? positions.find(p => (p.ticker || "").toUpperCase() === ticker)
          : null;
        if (!pos) return;
        const alertState = (pos.alert_state || "").toLowerCase();
        const deltaState = (pos.delta_state || "").toLowerCase();
        if (alertState === "critical" || deltaState === "critical") {
          row.classList.add("delta-critical");
        } else if (alertState === "watch" || deltaState === "watch") {
          row.classList.add("delta-watch");
        }
      });
    }, 50);
  };
})();
