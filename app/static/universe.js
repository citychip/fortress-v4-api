/**
 * universe.js — Fortress Dashboard Universe Tab
 *
 * Renders the ticker universe with inline add / remove / move / exclude controls.
 * Replaces the read-only renderUniverse() in app.js.
 */
"use strict";

// ─── State ────────────────────────────────────────────────────────────────────
let _universeData = null;

// ─── Entry point (called by renderUniverse in app.js) ─────────────────────────
window.renderUniverseEditable = async function (data) {
  _universeData = data;
  const target = document.getElementById("universe-content");
  if (!target) return;
  _renderUniverse(target, data);
};

// ─── Render ───────────────────────────────────────────────────────────────────
function _renderUniverse(target, data) {
  target.innerHTML = "";

  // ── Add ticker form ────────────────────────────────────────────────────────
  const addForm = document.createElement("div");
  addForm.className = "universe-add-form";
  addForm.innerHTML = `
    <div class="universe-add-row">
      <input
        type="text"
        id="uni-new-ticker"
        class="universe-input"
        placeholder="Ticker (e.g. TSLA)"
        maxlength="10"
        onkeydown="if(event.key==='Enter') universeAddTicker()"
        style="text-transform:uppercase;"
      />
      <select id="uni-new-tier" class="universe-select">
        <option value="tier1">Tier 1 — High IV</option>
        <option value="tier2">Tier 2 — Moderate IV</option>
        <option value="macro">Macro / Index</option>
      </select>
      <button class="action-cta action-cta-primary" onclick="universeAddTicker()">+ Add</button>
    </div>
    <div id="uni-feedback" class="universe-feedback" style="display:none;"></div>
  `;
  target.appendChild(addForm);

  // ── Tier sections ──────────────────────────────────────────────────────────
  const tierConfig = [
    { key: "tier1", label: "Tier 1", subtitle: "High IV — primary candidates" },
    { key: "tier2", label: "Tier 2", subtitle: "Moderate IV — secondary candidates" },
    { key: "macro", label: "Macro / Index", subtitle: "Benchmark & hedge instruments" },
  ];

  for (const { key, label, subtitle } of tierConfig) {
    const tickers = data[key] || [];
    const section = document.createElement("div");
    section.className = "universe-section";
    section.id = `uni-section-${key}`;

    const header = document.createElement("div");
    header.className = "universe-section-header";
    header.innerHTML = `
      <div>
        <span class="universe-tier-label">${label}</span>
        <span class="universe-tier-subtitle muted small">${subtitle}</span>
      </div>
      <span class="universe-count muted small">${tickers.length} ticker${tickers.length !== 1 ? "s" : ""}</span>
    `;
    section.appendChild(header);

    const chips = document.createElement("div");
    chips.className = "universe-chips";
    chips.id = `uni-chips-${key}`;

    if (tickers.length === 0) {
      chips.innerHTML = `<span class="universe-empty muted small">No tickers in this tier</span>`;
    } else {
      for (const ticker of tickers) {
        chips.appendChild(_makeChip(ticker, key, data));
      }
    }
    section.appendChild(chips);
    target.appendChild(section);
  }

  // ── Excluded section ───────────────────────────────────────────────────────
  const excluded = data.excluded || [];
  const excSection = document.createElement("div");
  excSection.className = "universe-section universe-excluded-section";
  excSection.id = "uni-section-excluded";

  excSection.innerHTML = `
    <div class="universe-section-header">
      <div>
        <span class="universe-tier-label" style="color:var(--warn);">Excluded</span>
        <span class="universe-tier-subtitle muted small">Regulatory, ignored, or suspended</span>
      </div>
      <span class="universe-count muted small">${excluded.length} ticker${excluded.length !== 1 ? "s" : ""}</span>
    </div>
    <div class="universe-chips" id="uni-chips-excluded">
      ${excluded.length === 0
        ? `<span class="universe-empty muted small">No excluded tickers</span>`
        : excluded.map(e => _makeExcludedChipHTML(e)).join("")
      }
    </div>
  `;
  target.appendChild(excSection);

  // ── Last updated ───────────────────────────────────────────────────────────
  if (data._last_updated) {
    const footer = document.createElement("p");
    footer.className = "muted small";
    footer.style.marginTop = "12px";
    footer.textContent = `Last updated: ${data._last_updated}`;
    target.appendChild(footer);
  }
}

// ─── Chip builders ────────────────────────────────────────────────────────────
function _makeChip(ticker, currentTier, data) {
  const chip = document.createElement("div");
  chip.className = "universe-chip";
  chip.id = `uni-chip-${ticker}`;

  const otherTiers = ["tier1", "tier2", "macro"].filter(t => t !== currentTier);
  const tierLabels = { tier1: "Tier 1", tier2: "Tier 2", macro: "Macro" };

  chip.innerHTML = `
    <span class="universe-chip-ticker">${ticker}</span>
    <div class="universe-chip-actions">
      ${otherTiers.map(t =>
        `<button class="chip-btn chip-btn-move" title="Move to ${tierLabels[t]}"
           onclick="universeMoveTickerTo('${ticker}','${currentTier}','${t}')">
           → ${tierLabels[t]}
         </button>`
      ).join("")}
      <button class="chip-btn chip-btn-exclude" title="Exclude ticker"
              onclick="universeExcludeTicker('${ticker}','${currentTier}')">
        ⊘
      </button>
      <button class="chip-btn chip-btn-remove" title="Remove from universe"
              onclick="universeRemoveTicker('${ticker}','${currentTier}')">
        ✕
      </button>
    </div>
  `;
  return chip;
}

function _makeExcludedChipHTML(entry) {
  const note = entry.note ? ` — ${entry.note}` : "";
  const reason = entry.reason || "";
  return `
    <div class="universe-chip universe-chip-excluded" id="uni-chip-excl-${entry.ticker}">
      <div>
        <span class="universe-chip-ticker">${entry.ticker}</span>
        <span class="muted small" style="margin-left:6px;">${reason}${note}</span>
      </div>
      <div class="universe-chip-actions">
        <button class="chip-btn chip-btn-restore" title="Remove from excluded list"
                onclick="universeUnexclude('${entry.ticker}')">
          ↩ Restore
        </button>
      </div>
    </div>
  `;
}

// ─── Feedback helper ──────────────────────────────────────────────────────────
function _showFeedback(msg, isError = false) {
  const el = document.getElementById("uni-feedback");
  if (!el) return;
  el.textContent = msg;
  el.style.display = "block";
  el.style.color = isError ? "var(--danger, #e05)" : "var(--success, #3c3)";
  clearTimeout(el._timeout);
  el._timeout = setTimeout(() => { el.style.display = "none"; }, 4000);
}

async function _apiCall(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  opts.headers = _authHeaders(opts.headers);
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ─── Actions ──────────────────────────────────────────────────────────────────
window.universeAddTicker = async function () {
  const tickerInput = document.getElementById("uni-new-ticker");
  const tierSelect = document.getElementById("uni-new-tier");
  const ticker = (tickerInput?.value || "").trim().toUpperCase();
  const tier = tierSelect?.value || "tier1";

  if (!ticker) { _showFeedback("Please enter a ticker symbol.", true); return; }

  try {
    const result = await _apiCall("POST", "/api/universe/add", { ticker, tier });
    _universeData = result.universe;
    const target = document.getElementById("universe-content");
    _renderUniverse(target, _universeData);
    tickerInput.value = "";
    _showFeedback(`${ticker} added to ${tier}.`);
  } catch (err) {
    _showFeedback(err.message, true);
  }
};

window.universeRemoveTicker = async function (ticker, tier) {
  if (!confirm(`Remove ${ticker} from ${tier}?\n\nThis removes it from your universe entirely.`)) return;
  try {
    const result = await _apiCall("DELETE", `/api/universe/${tier}/${ticker}`);
    _universeData = result.universe;
    const target = document.getElementById("universe-content");
    _renderUniverse(target, _universeData);
    _showFeedback(`${ticker} removed from ${tier}.`);
  } catch (err) {
    _showFeedback(err.message, true);
  }
};

window.universeMoveTickerTo = async function (ticker, fromTier, toTier) {
  try {
    const result = await _apiCall("POST", "/api/universe/move", {
      ticker, from_tier: fromTier, to_tier: toTier
    });
    _universeData = result.universe;
    const target = document.getElementById("universe-content");
    _renderUniverse(target, _universeData);
    _showFeedback(`${ticker} moved from ${fromTier} to ${toTier}.`);
  } catch (err) {
    _showFeedback(err.message, true);
  }
};

window.universeExcludeTicker = async function (ticker, tier) {
  const reason = prompt(`Reason for excluding ${ticker}? (e.g. regulatory, earnings, suspended)`, "manual");
  if (reason === null) return; // cancelled
  try {
    const result = await _apiCall("POST", "/api/universe/exclude", {
      ticker, reason: reason || "manual", until_cleared: true
    });
    _universeData = result.universe;
    const target = document.getElementById("universe-content");
    _renderUniverse(target, _universeData);
    _showFeedback(`${ticker} moved to excluded list.`);
  } catch (err) {
    _showFeedback(err.message, true);
  }
};

window.universeUnexclude = async function (ticker) {
  if (!confirm(`Remove ${ticker} from the excluded list?\n\nYou will need to add it to a tier manually.`)) return;
  try {
    const result = await _apiCall("DELETE", `/api/universe/exclude/${ticker}`);
    _universeData = result.universe;
    const target = document.getElementById("universe-content");
    _renderUniverse(target, _universeData);
    _showFeedback(`${ticker} removed from excluded list. Add it to a tier above.`);
  } catch (err) {
    _showFeedback(err.message, true);
  }
};
