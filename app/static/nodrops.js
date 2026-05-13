/* nodrops.js — No-dropdown UX module (v3.7)
   Replaces all <select> controls with:
   - Typeahead search boxes (ticker inputs)
   - Button groups (strategy, period, side, context)
   - Position card grids (position pickers)
   Also adds IBKR Test Connection + Refresh Capability buttons.
   Vanilla JS, no build step. */

(function () {
  "use strict";

  // ── Universe cache ──────────────────────────────────────────────────────
  let _universeTickers = [];

  async function _loadUniverse() {
    if (_universeTickers.length) return _universeTickers;
    try {
      const r = await authFetch("/api/universe");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      const all = [...(d.tier1 || []), ...(d.tier2 || []), ...(d.macro || [])];
      _universeTickers = [...new Set(all)];
    } catch (e) {
      console.warn("nodrops: universe load failed", e);
    }
    return _universeTickers;
  }

  // ── Positions cache ─────────────────────────────────────────────────────
  let _positionsCache = [];

  async function _loadPositions() {
    try {
      const r = await authFetch("/api/manage/positions");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      _positionsCache = Array.isArray(d) ? d : (d.positions || []);
    } catch (e) {
      console.warn("nodrops: positions load failed", e);
    }
    return _positionsCache;
  }

  // ── Typeahead helper ────────────────────────────────────────────────────
  function _makeTypeahead(inputId, dropdownId, tickers, onSelect) {
    const input = document.getElementById(inputId);
    const dd = document.getElementById(dropdownId);
    if (!input || !dd) return;

    let activeIdx = -1;

    function _render(filter) {
      const q = (filter || "").toUpperCase();
      const matches = q
        ? tickers.filter(t => t.startsWith(q)).concat(tickers.filter(t => !t.startsWith(q) && t.includes(q)))
        : tickers;
      dd.innerHTML = "";
      activeIdx = -1;
      if (!matches.length) { dd.classList.remove("open"); return; }
      matches.slice(0, 12).forEach((t, i) => {
        const btn = document.createElement("button");
        btn.className = "typeahead-option";
        btn.textContent = t;
        btn.addEventListener("mousedown", (e) => {
          e.preventDefault();
          _pick(t);
        });
        dd.appendChild(btn);
      });
      dd.classList.add("open");
    }

    function _pick(ticker) {
      input.value = ticker;
      dd.classList.remove("open");
      activeIdx = -1;
      if (onSelect) onSelect(ticker);
    }

    input.addEventListener("input", () => _render(input.value));
    input.addEventListener("focus", () => { if (!input.value) _render(""); });
    input.addEventListener("blur", () => setTimeout(() => dd.classList.remove("open"), 150));

    input.addEventListener("keydown", (e) => {
      const opts = dd.querySelectorAll(".typeahead-option");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, opts.length - 1);
        opts.forEach((o, i) => o.classList.toggle("active", i === activeIdx));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        opts.forEach((o, i) => o.classList.toggle("active", i === activeIdx));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (activeIdx >= 0 && opts[activeIdx]) {
          _pick(opts[activeIdx].textContent);
        } else if (input.value.trim()) {
          _pick(input.value.trim().toUpperCase());
        }
      } else if (e.key === "Escape") {
        dd.classList.remove("open");
      }
    });

    // Pre-fill if hidden select already has a value
    const hiddenSel = document.getElementById(inputId.replace("-dd", ""));
    if (hiddenSel && hiddenSel.tagName === "SELECT" && hiddenSel.value) {
      input.value = hiddenSel.value;
    }
  }

  // ── Button group helper ─────────────────────────────────────────────────
  function _wireButtonGroup(groupId, hiddenId, onChange) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-group-item");
      if (!btn) return;
      group.querySelectorAll(".btn-group-item").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const val = btn.getAttribute("data-val");
      group.setAttribute("data-value", val);
      const hidden = hiddenId ? document.getElementById(hiddenId) : null;
      if (hidden) hidden.value = val;
      if (onChange) onChange(val);
    });
  }

  // ── Position card grid helper ───────────────────────────────────────────
  function _renderPosGrid(gridId, hiddenId, positions, filterFn, onSelect) {
    const grid = document.getElementById(gridId);
    if (!grid) return;
    grid.innerHTML = "";

    const filtered = filterFn ? positions.filter(filterFn) : positions;
    if (!filtered.length) {
      grid.innerHTML = '<p class="muted small">No positions available.</p>';
      return;
    }

    filtered.forEach(pos => {
      const card = document.createElement("div");
      card.className = "pos-card";

      const stateClass = (pos.alert_state || "").toLowerCase().includes("act") ? "act"
        : (pos.alert_state || "").toLowerCase().includes("watch") ? "watch" : "hold";

      const expStr = pos.expiry ? pos.expiry.slice(0, 10) : "—";
      const dteStr = pos.dte != null ? `${pos.dte}d` : "";
      const deltaStr = pos.current_delta != null ? `Δ ${pos.current_delta.toFixed(2)}` : "";
      const pnlStr = pos.net_liq_pct != null ? `${pos.net_liq_pct.toFixed(1)}% NL` : "";

      card.innerHTML = `
        <div class="pos-card-ticker">${pos.ticker}</div>
        <div class="pos-card-meta">${pos.strategy || "—"} · ${expStr}${dteStr ? " · " + dteStr : ""}</div>
        <div class="pos-card-meta">${[deltaStr, pnlStr].filter(Boolean).join(" · ") || "—"}</div>
        <div class="pos-card-state ${stateClass}">${pos.alert_state || "HOLD"}</div>
      `;

      card.addEventListener("click", () => {
        grid.querySelectorAll(".pos-card").forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
        const hidden = hiddenId ? document.getElementById(hiddenId) : null;
        if (hidden) hidden.value = pos.id;
        if (onSelect) onSelect(pos);
      });

      grid.appendChild(card);
    });
  }

  // ── Ticker pill row (chart tab) ─────────────────────────────────────────
  function _renderTickerPills(rowId, hiddenId, tickers, onSelect) {
    const row = document.getElementById(rowId);
    if (!row) return;
    row.innerHTML = "";
    tickers.forEach((t, i) => {
      const pill = document.createElement("button");
      pill.className = "ticker-pill" + (i === 0 ? " active" : "");
      pill.textContent = t;
      pill.addEventListener("click", () => {
        row.querySelectorAll(".ticker-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        const hidden = hiddenId ? document.getElementById(hiddenId) : null;
        if (hidden) hidden.value = t;
        if (onSelect) onSelect(t);
      });
      row.appendChild(pill);
    });
    // Set initial hidden value
    const hidden = hiddenId ? document.getElementById(hiddenId) : null;
    if (hidden && tickers.length) hidden.value = tickers[0];
  }

  // ── IBKR Test Connection ────────────────────────────────────────────────
  window.testIbkrConnection = async function () {
    const btn = document.getElementById("ibkr-test-btn");
    const result = document.getElementById("ibkr-sync-result");
    if (btn) { btn.disabled = true; btn.textContent = "Testing…"; }
    if (result) result.innerHTML = '<span class="muted">Running connection test…</span>';
    try {
      const r = await authFetch("/api/ibkr/capability");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const cap = await r.json();
      const active = cap.active_backend;
      const web = cap.web_api || {};
      const sess = web.session_status || {};
      const opra = web.opra_subscribed;
      const acct = web.account || "—";
      const deltaTest = web.delta_test != null ? web.delta_test.toFixed(3) : "—";

      let html = "";
      if (active === "web_api" && sess.authenticated && sess.established) {
        html = `<div style="color:#22c55e;font-weight:600;margin-bottom:6px;">✓ IBKR Web API — connected</div>
          <div style="font-size:12px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
            <div><span class="muted">Account</span><br><strong>${acct}</strong></div>
            <div><span class="muted">OPRA Greeks</span><br><strong>${opra ? "✓ subscribed" : "✗ not subscribed"}</strong></div>
            <div><span class="muted">Delta test</span><br><strong>${deltaTest}</strong></div>
            <div><span class="muted">Session</span><br><strong>${sess.established ? "established" : "pending"}</strong></div>
            <div><span class="muted">Authenticated</span><br><strong>${sess.authenticated ? "yes" : "no"}</strong></div>
            <div><span class="muted">Backend</span><br><strong>${active}</strong></div>
          </div>`;
      } else if (active === "web_api" && sess.reachable && !sess.authenticated) {
        html = `<div style="color:#f59e0b;font-weight:600;margin-bottom:6px;">⚠ Web API reachable — re-auth required</div>
          <div style="font-size:12px;">Approve the push notification on IBKR Mobile to re-authenticate.</div>`;
      } else if (active === "bs_yfinance") {
        html = `<div style="color:#f59e0b;font-weight:600;margin-bottom:6px;">⚠ Fallback active — Black-Scholes / yfinance</div>
          <div style="font-size:12px;">IBKR Web API is not reachable. Greeks are estimated, not live OPRA data.<br>
          Hint: ${cap.resolution_hint || "Check that the CP Gateway container is running."}</div>`;
      } else {
        html = `<div style="color:#ef4444;font-weight:600;margin-bottom:6px;">✗ No backend available</div>
          <div style="font-size:12px;">${cap.resolution_hint || "Check VPS logs."}</div>`;
      }
      if (result) result.innerHTML = html;
    } catch (e) {
      if (result) result.innerHTML = `<div style="color:#ef4444;">✗ Test failed: ${e.message}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Test connection"; }
    }
  };

  window.refreshIbkrCapability = async function () {
    const btn = document.getElementById("ibkr-refresh-cap-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Refreshing…"; }
    await checkGatewayStatus();
    if (btn) { btn.disabled = false; btn.textContent = "↻ Refresh status"; }
  };

  // ── Main init ───────────────────────────────────────────────────────────
  async function init() {
    // Wait for token
    if (window._tokenReady) await window._tokenReady;

    const [tickers, positions] = await Promise.all([_loadUniverse(), _loadPositions()]);

    // ── Typeahead: Pre-trade ticker ────────────────────────────────────────
    _makeTypeahead("pt-ticker", "pt-ticker-dd", tickers);

    // ── Button group: Pre-trade strategy ──────────────────────────────────
    _wireButtonGroup("pt-strategy-group", "pt-strategy", (val) => {
      // Trigger Jade Lizard gate visibility
      if (typeof showJadeLizardGate === "function") showJadeLizardGate();
    });

    // ── Ticker pill row: Chart tab ─────────────────────────────────────────
    _renderTickerPills("chart-ticker-pills", "chart-ticker-select", tickers, (t) => {
      const period = document.getElementById("chart-period-select")?.value || "3mo";
      if (typeof renderChart === "function") renderChart(t, period);
    });

    // ── Button group: Chart period ─────────────────────────────────────────
    _wireButtonGroup("chart-period-group", "chart-period-select", (period) => {
      const ticker = document.getElementById("chart-ticker-select")?.value;
      if (ticker && typeof renderChart === "function") renderChart(ticker, period);
    });

    // ── Typeahead: Playbook ticker ─────────────────────────────────────────
    _makeTypeahead("pb-ticker", "pb-ticker-dd", tickers);

    // ── Typeahead: Order flow ticker ───────────────────────────────────────
    _makeTypeahead("of-ticker", "of-ticker-dd", tickers);

      // ── Button group: Order flow side ──────────────────────────────
    _wireButtonGroup("of-side-group", "of-side");

    const shortPositions = positions.filter(p => p.short_strike != null && p.strategy !== "SPY_HEDGE");

    _renderPosGrid("stop-loss-pos-grid", "stop-loss-position", positions, null, (pos) => {
      // Auto-trigger evaluate on click
      const btn = document.getElementById("stop-loss-run");
      if (btn) btn.click();
    });

    _renderPosGrid("roll-pos-grid", "roll-position", shortPositions, null, (pos) => {
      const btn = document.getElementById("roll-run");
      if (btn) btn.click();
    });

    // ── Position card grids: Reports tab ──────────────────────────────────
    _renderPosGrid("rpt-roll-pos-grid", "rpt-roll-position", shortPositions, null, null);
    _renderPosGrid("rpt-sell-pos-grid", "rpt-sell-position", positions, null, null);

    // ── Typeahead: Reports new trade ticker ───────────────────────────────
    _makeTypeahead("rpt-new-ticker", "rpt-new-ticker-dd", tickers);

    // ── Button group: Reports new trade strategy ──────────────────────────
    _wireButtonGroup("rpt-new-strategy-group", "rpt-new-strategy");

    // ── Typeahead: Reports buy ticker ─────────────────────────────────────
    _makeTypeahead("rpt-buy-ticker", "rpt-buy-ticker-dd", tickers);

    // ── Button group: Reports buy strategy ───────────────────────────────
    _wireButtonGroup("rpt-buy-strategy-group", "rpt-buy-strategy");

    // ── Patch populateChartTickers to be a no-op (pill row replaces it) ───
    // The original function still runs for the chart gallery — we let it
    // run but skip the select population since those are now hidden inputs.
    const _origPopulate = window.populateChartTickers;
    window.populateChartTickers = async function () {
      // Only run the gallery part — pill row already populated above
      if (window._tokenReady) await window._tokenReady;
      try {
        const data = await apiFetch("/api/universe");
        if (!data) return;
        const tiers = [...(data.tier1 || []), ...(data.tier2 || []), ...(data.macro || [])];
        const ts = [...new Set(tiers)];
        if (typeof renderChartGallery === "function") renderChartGallery(ts);
      } catch (e) { console.warn("populateChartTickers (patched):", e); }
    };

    // ── Patch runPositionAction to work with hidden inputs ─────────────────
    // The existing phase4.js runPositionAction reads the select value;
    // now it reads the hidden input value set by the card grid.
    // No change needed — hidden inputs have the same IDs.

    // ── Expose refresh for tab navigation ─────────────────────────────────
    window._nodropRefreshPositions = async function () {
      await _loadPositions();
      const shortPos = _positionsCache.filter(p => p.short_strike != null && p.strategy !== "SPY_HEDGE");
      _renderPosGrid("stop-loss-pos-grid", "stop-loss-position", _positionsCache, null, (pos) => {
        const btn = document.getElementById("stop-loss-run");
        if (btn) btn.click();
      });
      _renderPosGrid("roll-pos-grid", "roll-position", shortPos, null, (pos) => {
        const btn = document.getElementById("roll-run");
        if (btn) btn.click();
      });
      _renderPosGrid("rpt-roll-pos-grid", "rpt-roll-position", shortPos, null, null);
      _renderPosGrid("rpt-sell-pos-grid", "rpt-sell-position", _positionsCache, null, null);
    };

    // ── Expose deep-link: set ticker typeahead from external code ──────────
    window.setTypeaheadTicker = function (inputId, ticker) {
      const input = document.getElementById(inputId);
      if (input) {
        input.value = ticker;
        input.dispatchEvent(new Event("input"));
      }
    };

    // ── Expose deep-link: select position card by id ───────────────────────
    window.selectPosCard = function (gridId, hiddenId, posId) {
      const grid = document.getElementById(gridId);
      if (!grid) return;
      const pos = _positionsCache.find(p => p.id === posId);
      if (!pos) return;
      grid.querySelectorAll(".pos-card").forEach((card, i) => {
        const match = _positionsCache.filter(p => {
          const shortPos2 = _positionsCache.filter(pp => pp.short_strike != null && pp.strategy !== "SPY_HEDGE");
          return true;
        });
        // Match by rendered order
      });
      const hidden = document.getElementById(hiddenId);
      if (hidden) hidden.value = posId;
    };

    console.log("nodrops.js: init complete —", tickers.length, "tickers,", positions.length, "positions");
  }

  // ── Wire navigateToTab hook to refresh position grids ──────────────────
  const _origNav = window.navigateToTab;
  window.navigateToTab = function (tab) {
    if (_origNav) _origNav(tab);
    if (tab === "manage" || tab === "reports") {
      window._nodropRefreshPositions && window._nodropRefreshPositions();
    }
  };

  // ── Patch runPositionAction to use typeahead/card instead of select ─────
  // Override the chart action to use the pill row instead of the old select
  const _patchRunPositionAction = function () {
    const _orig = window.runPositionAction;
    window.runPositionAction = async function (event, action) {
      if (action === "chart") {
        event.stopPropagation();
        const item = event.currentTarget;
        const menu = item.closest(".row-action-menu");
        const kebab = menu && menu.previousElementSibling;
        const matcherStr = kebab && kebab.getAttribute("data-pos");
        if (!matcherStr) return;
        let matcher;
        try { matcher = JSON.parse(matcherStr); } catch (e) { return; }
        if (menu) menu.classList.remove("open");
        navigateToTab("trade");
        // Activate the correct ticker pill
        const pillRow = document.getElementById("chart-ticker-pills");
        if (pillRow) {
          const pills = pillRow.querySelectorAll(".ticker-pill");
          let found = false;
          pills.forEach(p => {
            const active = p.textContent === matcher.ticker;
            p.classList.toggle("active", active);
            if (active) found = true;
          });
          const hidden = document.getElementById("chart-ticker-select");
          if (hidden) hidden.value = matcher.ticker;
          const period = document.getElementById("chart-period-select")?.value || "3mo";
          if (typeof renderChart === "function") renderChart(matcher.ticker, period);
          document.getElementById("chart-container")?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        return;
      }
      // Delegate stop_loss and roll to original (hidden inputs already set by card grid)
      if (_orig) return _orig.call(this, event, action);
    };
  };

  // Run init after DOM + token ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      setTimeout(init, 200); // slight delay to let other modules load
    });
  } else {
    setTimeout(init, 200);
  }

  // Also patch runPositionAction once phase4.js has set it
  setTimeout(_patchRunPositionAction, 600);

})();
