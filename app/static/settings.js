/**
 * settings.js — Fortress Dashboard Settings & Strategy Tabs
 *
 * Two independent tabs:
 *   Strategy tab  — Trader Persona selector + Live Narrative + Strategy + Alerts sections
 *   Settings tab  — Technical/Infrastructure section + Display/UI section
 *
 * Both tabs share the same schema-driven field renderer and config store.
 */

"use strict";

// ─── Shared state ─────────────────────────────────────────────────────────────
let _schema  = {};
let _config  = {};
let _presets = [];
let _dirty   = {};   // { section: { key: newValue } }
let _loaded  = false;

// ─── Shared data loader ───────────────────────────────────────────────────────
async function _loadConfigData() {
  if (_loaded) return true;
  const [schemaData, configData, presetsData] = await Promise.all([
    apiFetch("/api/settings/schema"),
    apiFetch("/api/settings"),
    apiFetch("/api/settings/trader_presets").catch(() => null),
  ]);
  if (!schemaData || !schemaData.schema) throw new Error("Schema missing — auth error?");
  if (!configData || !configData.config) throw new Error("Config missing — auth error?");
  _schema  = schemaData.schema;
  _config  = configData.config;
  _presets = (presetsData && presetsData.presets) ? presetsData.presets : [];
  _dirty   = {};
  _loaded  = true;
  return true;
}

// ─── Strategy tab entry point ─────────────────────────────────────────────────
async function initStrategy() {
  const container = document.getElementById("strategy-container");
  if (!container) return;
  container.innerHTML = `<div class="settings-loading">Loading strategy…</div>`;

  try {
    const [_, narrativeData, alertsData] = await Promise.all([
      _loadConfigData(),
      apiFetch("/api/settings/narrative").catch(() => null),
      apiFetch("/api/alerts").catch(() => null),
    ]);
    renderStrategy(container, narrativeData);
    // Populate the live alerts panel now that the DOM is ready
    if (typeof renderAlerts === "function" && alertsData) renderAlerts(alertsData);
  } catch (err) {
    container.innerHTML = `<div class="settings-error">Failed to load strategy: ${err.message}</div>`;
  }
}

function renderStrategy(container, narrativeData) {
  let html = `
    <div class="settings-header">
      <h2>Strategy</h2>
      <p class="settings-subtitle">
        Choose your trader persona, review the live strategy narrative, and fine-tune
        strategy parameters. Changes are saved to <code>fortress_config.json</code>
        and take effect immediately.
      </p>
    </div>
  `;

  // ── 1. Trader Persona Selector ──
  html += renderPersonaSelector();

  // ── 2. Live Strategy Narrative ──
  html += renderNarrative(narrativeData);

  // ── 3. Trader Profile (collapsible, open by default) ──
  if (_schema["trader_profile"]) {
    html += buildCollapsibleSectionHtml("trader_profile", "👤 Trader Profile", true);
  }

  // ── 4. Strategy Parameters (collapsible, open by default) ──
  if (_schema["strategy"]) {
    html += buildStrategyParametersHtml();
  }

  // ── 5. Alerts & Thresholds (collapsible, collapsed by default) ──
  if (_schema["alerts"]) {
    html += buildCollapsibleSectionHtml("alerts", "🔔 Alerts & Thresholds", false);
  }

  // ── 6. Live Alerts panel (collapsible, collapsed by default) ──
  html += `
    <details class="settings-collapsible">
      <summary class="settings-collapsible-summary">🔔 Live Alerts</summary>
      <div class="settings-section">
        <div class="settings-section-header">
          <p class="settings-subtitle">Active alerts for the book. Add, snooze, or dismiss alerts manually.
            The stop-loss aggregator also writes here automatically.</p>
        </div>
        <div id="alerts-content"><div class="loading">Loading alerts…</div></div>
      </div>
    </details>
  `;

  container.innerHTML = html;
}

// Renders Strategy Parameters section with sub-group dividers for readability
function buildStrategyParametersHtml() {
  const fields  = _schema["strategy"] || [];
  const values  = (_config["strategy"]) || {};

  // Sub-groups for the strategy section
  const subGroups = [
    { key: "entry",      label: "Entry Rules",           keys: ["target_delta_low","target_delta_high","delta_critical_threshold","target_dte_low","target_dte_high","ivr_min_entry","ivr_high_threshold","max_long_option_cost_pct"] },
    { key: "exit",       label: "Exit & Roll Rules",      keys: ["dte_roll_threshold","profit_target_pct","stop_loss_drawdown_pct","stop_loss_sma200_buffer"] },
    { key: "sizing",     label: "Sizing & Pacing",        keys: ["max_positions","entries_per_week_max","max_concentration_pct"] },
    { key: "income",     label: "Income Strategies",      keys: ["min_credit_jade_lizard","min_credit_pcs","min_credit_pmcc","min_credit_covered_call","min_credit_csput","wheel_csp_delta","wheel_cc_delta"] },
    { key: "volatility", label: "Volatility Strategies",  keys: ["iron_condor_short_delta","iron_condor_wing_width","straddle_dte_target","strangle_short_delta","butterfly_wing_width"] },
    { key: "directional",label: "Directional Strategies", keys: ["long_call_target_delta","long_put_target_delta","vertical_spread_width","leaps_min_dte","leaps_target_delta","diagonal_front_dte","diagonal_back_dte"] },
    { key: "protection", label: "Protection Strategies",  keys: ["collar_put_delta_target","collar_call_delta_target","protective_put_delta_target","spy_hedge_min_usd","spy_hedge_max_usd","spy_hedge_target_usd"] },
  ];

  const fieldMap = {};
  for (const f of fields) fieldMap[f.key] = f;

  let innerHtml = `
    <div class="settings-section-header">
      <div class="settings-section-actions">
        <span class="settings-save-status" id="save-status-strategy"></span>
        <button class="btn btn-primary btn-sm" onclick="saveSection('strategy')" id="save-btn-strategy">
          Save Strategy
        </button>
      </div>
    </div>
    <div class="settings-section-body">`;

  const usedKeys = new Set();
  for (const grp of subGroups) {
    const grpFields = grp.keys.map(k => fieldMap[k]).filter(Boolean);
    if (grpFields.length === 0) continue;
    innerHtml += `<div class="strategy-subgroup">`;
    innerHtml += `<div class="strategy-subgroup-label">${grp.label}</div>`;
    innerHtml += `<div class="settings-grid">`;
    for (const f of grpFields) {
      innerHtml += renderField("strategy", f, values[f.key]);
      usedKeys.add(f.key);
    }
    innerHtml += `</div></div>`;
  }

  // Catch-all for any fields not in a sub-group
  const remaining = fields.filter(f => !usedKeys.has(f.key));
  if (remaining.length > 0) {
    innerHtml += `<div class="strategy-subgroup">`;
    innerHtml += `<div class="strategy-subgroup-label">Other</div>`;
    innerHtml += `<div class="settings-grid">`;
    for (const f of remaining) innerHtml += renderField("strategy", f, values[f.key]);
    innerHtml += `</div></div>`;
  }

  innerHtml += `</div>`; // close settings-section-body

  return `
    <details class="settings-collapsible" open>
      <summary class="settings-collapsible-summary">📈 Strategy Parameters</summary>
      <div class="settings-section" id="settings-section-strategy">
        ${innerHtml}
      </div>
    </details>`;
}

// ─── Trader Persona Selector ──────────────────────────────────────────────────
function renderPersonaSelector() {
  if (!_presets || _presets.length === 0) return "";

  const currentType = (_config.trader_profile || {}).trader_type || "custom";

  const cards = _presets.map(p => {
    const isActive = p.id === currentType;
    const stratBadges = (p.strategies || []).slice(0, 5).map(s =>
      `<span class="persona-strat-badge">${escHtml(s)}</span>`
    ).join("") + (p.strategies && p.strategies.length > 5
      ? `<span class="persona-strat-badge persona-strat-more">+${p.strategies.length - 5}</span>` : "");

    const riskClass = {
      conservative: "risk-conservative",
      moderate:     "risk-moderate",
      aggressive:   "risk-aggressive",
    }[p.risk_tolerance] || "";

    return `
      <div class="persona-card ${isActive ? "persona-card--active" : ""}"
           id="persona-card-${p.id}"
           onclick="applyPreset('${p.id}')">
        <div class="persona-card-header">
          <span class="persona-icon">${p.icon || "🎯"}</span>
          <span class="persona-label">${escHtml(p.label)}</span>
          ${isActive ? `<span class="persona-active-badge">Active</span>` : ""}
        </div>
        <p class="persona-desc">${escHtml(p.description)}</p>
        <div class="persona-meta">
          <span class="persona-risk ${riskClass}">${escHtml(p.risk_tolerance || "")}</span>
          <span class="persona-objective">${escHtml(p.primary_objective || "")}</span>
        </div>
        <div class="persona-strats">${stratBadges}</div>
      </div>`;
  }).join("");

  return `
    <div class="settings-section persona-selector-section">
      <div class="settings-section-header">
        <h3>🎯 Trader Persona</h3>
        <p class="settings-subtitle">
          Select a preset that matches your trading style. Applying a preset overwrites
          the Trader Profile, Strategy Parameters, and Alert Thresholds sections below.
          You can then fine-tune individual fields.
        </p>
      </div>
      <div class="persona-grid">
        ${cards}
      </div>
      <div id="persona-apply-status" class="persona-apply-status"></div>
    </div>`;
}

async function applyPreset(presetId) {
  const statusEl = document.getElementById("persona-apply-status");
  if (statusEl) { statusEl.textContent = "Applying preset…"; statusEl.className = "persona-apply-status loading"; }

  try {
    const res = await authFetch("/api/settings/apply_preset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset_id: presetId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Apply failed");

    // Reload config and re-render the whole strategy tab
    _loaded = false;
    _dirty  = {};
    await initStrategy();

    if (statusEl) {
      statusEl.textContent = `✓ Preset "${data.label}" applied successfully.`;
      statusEl.className = "persona-apply-status success";
      setTimeout(() => { if (statusEl) statusEl.textContent = ""; }, 5000);
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = `✗ Error: ${err.message}`;
      statusEl.className = "persona-apply-status error";
    }
  }
}

// ─── Settings tab entry point ─────────────────────────────────────────────────
async function initSettings() {
  const container = document.getElementById("settings-container");
  if (!container) return;
  container.innerHTML = `<div class="settings-loading">Loading settings…</div>`;

  try {
    await _loadConfigData();
    renderSettingsTab(container);
  } catch (err) {
    container.innerHTML = `<div class="settings-error">Failed to load settings: ${err.message}</div>`;
  }
}

function renderSettingsTab(container) {
  const sectionLabels = {
    security:  "🔐 Security & Credentials",
    technical: "⚙️  Technical / Infrastructure",
    ui:        "🖥️  Display & UI",
  };

  let html = `
    <div class="settings-header">
      <h2>Settings</h2>
      <p class="settings-subtitle">
        Infrastructure, connection, and display preferences.
        All changes are saved immediately to <code>fortress_config.json</code> on the VPS
        and take effect on the next API call — no restart required.
      </p>
      <button class="btn btn-danger btn-sm settings-reset-btn" onclick="confirmReset()">
        ↺ Reset All to Defaults
      </button>
    </div>
  `;

  // Security section first
  for (const section of ["security", "technical", "ui"]) {
    if (!_schema[section]) continue;
    html += buildCollapsibleSectionHtml(section, sectionLabels[section],
      section === "security" ? true : false);
  }

  // Backup & Restore card
  html += renderBackupRestoreCard();

  container.innerHTML = html;
}

// ─── Collapsible section wrapper ─────────────────────────────────────────────
function buildCollapsibleSectionHtml(section, label, defaultOpen = true) {
  const inner = buildSectionHtml(section, label);
  // Wrap in a <details> for collapsibility
  return `
    <details class="settings-collapsible" ${defaultOpen ? "open" : ""}>
      <summary class="settings-collapsible-summary">${label}</summary>
      ${inner}
    </details>`;
}

// ─── Backup & Restore card ────────────────────────────────────────────────────
function renderBackupRestoreCard() {
  return `
    <div class="settings-section backup-restore-card">
      <div class="settings-section-header">
        <h3>💾 Backup &amp; Restore</h3>
        <p class="settings-subtitle">
          Export all settings, alerts, journal, and watchlist to a ZIP file.
          Restore from a previous backup to roll back configuration changes.
        </p>
      </div>
      <div class="settings-section-body">
        <div class="backup-restore-row">
          <div class="backup-block">
            <h4>Export backup</h4>
            <p class="field-desc">Downloads a ZIP containing <code>fortress_config.json</code>,
              <code>ticker_universe.json</code>, <code>alerts.json</code>, and <code>journal.json</code>.
              No positions or uploads are included.</p>
            <button class="btn btn-primary" onclick="downloadBackup()">⬇ Download backup</button>
            <span id="backup-status" class="settings-save-status"></span>
          </div>
          <div class="restore-block">
            <h4>Restore from backup</h4>
            <p class="field-desc">Upload a <code>fortress_backup_*.zip</code> file.
              Settings are applied immediately. Other files are written to the data directory.</p>
            <label class="btn btn-secondary restore-upload-label">
              ⬆ Choose backup file
              <input type="file" id="restore-file-input" accept=".zip" style="display:none"
                     onchange="uploadRestore(this)" />
            </label>
            <span id="restore-status" class="settings-save-status"></span>
          </div>
        </div>
      </div>
    </div>`;
}

async function downloadBackup() {
  const btn = document.querySelector(".backup-block .btn-primary");
  const status = document.getElementById("backup-status");
  if (btn) { btn.disabled = true; btn.textContent = "Preparing…"; }
  if (status) { status.textContent = ""; status.className = "settings-save-status"; }
  try {
    const token = await window._tokenReady;
    const res = await fetch("/api/settings/backup", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "fortress_backup.zip";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    if (status) { status.textContent = `✓ Downloaded ${filename}`; status.className = "settings-save-status success"; }
  } catch (err) {
    if (status) { status.textContent = `✗ ${err.message}`; status.className = "settings-save-status error"; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "⬇ Download backup"; }
  }
}

async function uploadRestore(input) {
  const file = input.files[0];
  if (!file) return;
  const status = document.getElementById("restore-status");
  const label = document.querySelector(".restore-upload-label");
  if (status) { status.textContent = "Uploading…"; status.className = "settings-save-status loading"; }
  try {
    const token = await window._tokenReady;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/settings/restore", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Restore failed");
    if (status) {
      status.textContent = `✓ Restored: ${data.restored.join(", ")}`;
      status.className = "settings-save-status success";
    }
    // Reload config
    _loaded = false;
    await initSettings();
  } catch (err) {
    if (status) { status.textContent = `✗ ${err.message}`; status.className = "settings-save-status error"; }
  } finally {
    input.value = "";
  }
}

// ─── Shared section builder ───────────────────────────────────────────────────
function buildSectionHtml(section, label) {
  const fields = _schema[section];
  const values = _config[section] || {};
  const groups = groupFields(fields);

  // Determine a short save label (strip emoji prefix)
  const saveLabel = (label || section).replace(/^[\u{1F000}-\u{1FFFF}️🎯📈🔔⚙️🖥️👤\s]+/u, "").trim() || section;

  let html = `
    <div class="settings-section" id="settings-section-${section}">
      <div class="settings-section-header">
        <h3>${label || section}</h3>
        <div class="settings-section-actions">
          <span class="settings-save-status" id="save-status-${section}"></span>
          <button class="btn btn-primary btn-sm"
                  onclick="saveSection('${section}')"
                  id="save-btn-${section}">
            Save ${saveLabel}
          </button>
        </div>
      </div>
      <div class="settings-section-body">
  `;

  for (const [groupName, groupFields] of Object.entries(groups)) {
    if (groupName !== "__default__") {
      html += `<div class="settings-group-label">${groupName}</div>`;
    }
    html += `<div class="settings-grid">`;
    for (const field of groupFields) {
      html += renderField(section, field, values[field.key]);
    }
    html += `</div>`;
  }

  html += `</div></div>`;
  return html;
}

// ─── Mode 3: Narrative Panel ──────────────────────────────────────────────────
function renderNarrative(data) {
  if (!data) {
    return `
      <div class="narrative-panel narrative-panel--error">
        <div class="narrative-panel-header">
          <span class="narrative-title">📋 Live Strategy Narrative</span>
          <span class="narrative-badge narrative-badge--warn">Unavailable</span>
        </div>
        <p class="narrative-error-msg">Could not load narrative data. Check API connectivity.</p>
      </div>`;
  }

  const asOf = data.as_of
    ? new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "—";

  const traderBadge = data.trader_type
    ? `<span class="narrative-trader-badge">${escHtml(data.trader_type.replace(/_/g, " "))}</span>`
    : "";

  const paragraphsHtml = (data.paragraphs || []).map(p =>
    `<p class="narrative-para">${markdownBold(p)}</p>`
  ).join("");

  const obsHtml = (data.observations || []).length === 0 ? "" : `
    <div class="narrative-observations">
      ${data.observations.map(obs => {
        const cls  = obs.level === "critical" ? "obs-critical"
                   : obs.level === "warn"     ? "obs-warn"
                   :                            "obs-info";
        const icon = obs.level === "critical" ? "🔴"
                   : obs.level === "warn"     ? "🟡"
                   :                            "🔵";
        return `<div class="narrative-obs ${cls}">${icon} ${escHtml(obs.text)}</div>`;
      }).join("")}
    </div>`;

  const whatIfHtml = (data.what_if || []).length === 0 ? "" : `
    <details class="narrative-whatif">
      <summary class="narrative-whatif-summary">💡 What-if scenarios (${data.what_if.length})</summary>
      <ul class="narrative-whatif-list">
        ${data.what_if.map(s => `<li>${escHtml(s)}</li>`).join("")}
      </ul>
    </details>`;

  return `
    <div class="narrative-panel">
      <div class="narrative-panel-header">
        <span class="narrative-title">📋 Live Strategy Narrative</span>
        ${traderBadge}
        <span class="narrative-as-of">as of ${asOf}</span>
        <button class="btn btn-sm btn-secondary narrative-refresh-btn"
                onclick="refreshNarrative()" title="Refresh narrative">↻ Refresh</button>
      </div>
      <div class="narrative-body" id="narrative-body">
        ${paragraphsHtml}
        ${obsHtml}
        ${whatIfHtml}
      </div>
    </div>`;
}

async function refreshNarrative() {
  const btn  = document.querySelector(".narrative-refresh-btn");
  const body = document.getElementById("narrative-body");
  if (btn) { btn.disabled = true; btn.textContent = "↻ Loading…"; }
  try {
    const data = await apiFetch("/api/settings/narrative");
    if (body && data) {
      const asOf = data.as_of
        ? new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : "—";
      const asOfEl = document.querySelector(".narrative-as-of");
      if (asOfEl) asOfEl.textContent = `as of ${asOf}`;

      const traderBadgeEl = document.querySelector(".narrative-trader-badge");
      if (traderBadgeEl && data.trader_type) {
        traderBadgeEl.textContent = data.trader_type.replace(/_/g, " ");
      }

      const paragraphsHtml = (data.paragraphs || []).map(p =>
        `<p class="narrative-para">${markdownBold(p)}</p>`
      ).join("");

      const obsHtml = (data.observations || []).length === 0 ? "" : `
        <div class="narrative-observations">
          ${data.observations.map(obs => {
            const cls  = obs.level === "critical" ? "obs-critical"
                       : obs.level === "warn"     ? "obs-warn"
                       :                            "obs-info";
            const icon = obs.level === "critical" ? "🔴"
                       : obs.level === "warn"     ? "🟡"
                       :                            "🔵";
            return `<div class="narrative-obs ${cls}">${icon} ${escHtml(obs.text)}</div>`;
          }).join("")}
        </div>`;

      const whatIfHtml = (data.what_if || []).length === 0 ? "" : `
        <details class="narrative-whatif">
          <summary class="narrative-whatif-summary">💡 What-if scenarios (${data.what_if.length})</summary>
          <ul class="narrative-whatif-list">
            ${data.what_if.map(s => `<li>${escHtml(s)}</li>`).join("")}
          </ul>
        </details>`;

      body.innerHTML = paragraphsHtml + obsHtml + whatIfHtml;
    }
  } catch (err) {
    if (body) body.innerHTML += `<p class="narrative-error-msg">Refresh failed: ${escHtml(err.message)}</p>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "↻ Refresh"; }
  }
}

function markdownBold(str) {
  return str.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

// ─── Field renderer ───────────────────────────────────────────────────────────
function groupFields(fields) {
  const groups = {};
  for (const f of fields) {
    const g = f.group || "__default__";
    if (!groups[g]) groups[g] = [];
    groups[g].push(f);
  }
  return groups;
}

function renderField(section, field, value) {
  const id    = `field-${section}-${field.key}`;
  const label = field.label + (field.unit ? ` <span class="field-unit">(${field.unit})</span>` : "");
  const desc  = field.description ? `<div class="field-desc">${field.description}</div>` : "";
  let input   = "";

  switch (field.type) {
    case "number":
      input = `<input type="number"
        id="${id}"
        class="settings-input"
        value="${value ?? ""}"
        min="${field.min ?? ""}"
        max="${field.max ?? ""}"
        step="${field.step ?? "any"}"
        onchange="markDirty('${section}', '${field.key}', parseFloat(this.value))"
      />`;
      break;

    case "text":
      input = `<input type="text"
        id="${id}"
        class="settings-input"
        value="${escHtml(String(value ?? ""))}"
        onchange="markDirty('${section}', '${field.key}', this.value)"
      />`;
      break;

    case "password":
      input = `
        <div class="password-field">
          <input type="password"
            id="${id}"
            class="settings-input"
            value="${value === "••••••••" ? "" : escHtml(String(value ?? ""))}"
            placeholder="${value === "••••••••" ? "••••••••  (unchanged)" : ""}"
            autocomplete="new-password"
            onchange="markDirty('${section}', '${field.key}', this.value)"
          />
          <button class="btn-icon" onclick="togglePasswordVisibility('${id}')" title="Show/hide">👁</button>
        </div>`;
      break;

    case "readonly":
      input = `<div class="settings-readonly">${escHtml(String(value ?? ""))}</div>`;
      break;

    case "boolean":
      const checked = value ? "checked" : "";
      input = `<label class="toggle-switch">
        <input type="checkbox" id="${id}" ${checked}
          onchange="markDirty('${section}', '${field.key}', this.checked)" />
        <span class="toggle-slider"></span>
      </label>`;
      break;

    case "select":
      const opts = (field.options || []).map(o =>
        `<option value="${escHtml(o)}" ${o === value ? "selected" : ""}>${escHtml(o)}</option>`
      ).join("");
      input = `<select id="${id}" class="settings-input settings-select"
        onchange="markDirty('${section}', '${field.key}', this.value)">
        ${opts}
      </select>`;
      break;

    case "multiselect":
      const allOpts  = field.options || [];
      const selected = Array.isArray(value) ? value : [];
      input = `<div class="multiselect-group" id="${id}">` +
        allOpts.map(o => `
          <label class="multiselect-item">
            <input type="checkbox" value="${escHtml(o)}"
              ${selected.includes(o) ? "checked" : ""}
              onchange="updateMultiselect('${section}', '${field.key}', '${id}')"
            />
            ${escHtml(o)}
          </label>`
        ).join("") +
        `</div>`;
      break;

    default:
      input = `<input type="text" id="${id}" class="settings-input"
        value="${escHtml(String(value ?? ""))}"
        onchange="markDirty('${section}', '${field.key}', this.value)" />`;
  }

  return `
    <div class="settings-field" id="field-wrapper-${section}-${field.key}">
      <label class="field-label" for="${id}">${label}</label>
      ${input}
      ${desc}
    </div>
  `;
}

// ─── Interaction handlers ─────────────────────────────────────────────────────
function markDirty(section, key, value) {
  if (!_dirty[section]) _dirty[section] = {};
  _dirty[section][key] = value;
  const btn = document.getElementById(`save-btn-${section}`);
  if (btn) btn.classList.add("btn-dirty");
  const status = document.getElementById(`save-status-${section}`);
  if (status) { status.textContent = "Unsaved changes"; status.className = "settings-save-status unsaved"; }
}

function updateMultiselect(section, key, containerId) {
  const container = document.getElementById(containerId);
  const checked = Array.from(container.querySelectorAll("input:checked")).map(el => el.value);
  markDirty(section, key, checked);
}

function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
}

async function saveSection(section) {
  const changes = _dirty[section];
  if (!changes || Object.keys(changes).length === 0) {
    showSaveStatus(section, "No changes to save.", "info");
    return;
  }

  const btn = document.getElementById(`save-btn-${section}`);
  if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }

  try {
    const res = await authFetch(`/api/settings/${section}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: changes }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Save failed");

    if (!_config[section]) _config[section] = {};
    Object.assign(_config[section], changes);
    delete _dirty[section];

    showSaveStatus(section, `✓ Saved ${data.updated_keys.length} field(s)`, "success");
    if (btn) {
      btn.classList.remove("btn-dirty");
      btn.textContent = `Save ${section.charAt(0).toUpperCase() + section.slice(1)}`;
    }

    // If trader_profile was saved, refresh narrative to reflect new persona
    if (section === "trader_profile") {
      const data2 = await apiFetch("/api/settings/narrative").catch(() => null);
      if (data2) {
        const body = document.getElementById("narrative-body");
        if (body) {
          const paragraphsHtml = (data2.paragraphs || []).map(p =>
            `<p class="narrative-para">${markdownBold(p)}</p>`
          ).join("");
          body.innerHTML = paragraphsHtml;
        }
      }
    }
  } catch (err) {
    showSaveStatus(section, `✗ Error: ${err.message}`, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function showSaveStatus(section, msg, type) {
  const el = document.getElementById(`save-status-${section}`);
  if (!el) return;
  el.textContent = msg;
  el.className = `settings-save-status ${type}`;
  if (type === "success") setTimeout(() => { el.textContent = ""; el.className = "settings-save-status"; }, 4000);
}

async function confirmReset() {
  if (!confirm("Reset ALL settings to factory defaults?\n\nThis cannot be undone.")) return;
  try {
    const res = await authFetch("/api/settings/reset", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Reset failed");
    alert("Settings reset to defaults. Reloading…");
    _loaded = false;
    await initSettings();
  } catch (err) {
    alert(`Reset failed: ${err.message}`);
  }
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ─── Exports ──────────────────────────────────────────────────────────────────
window.initSettings  = initSettings;
window.initStrategy  = initStrategy;
window.applyPreset   = applyPreset;
window.saveSection   = saveSection;
window.markDirty     = markDirty;
window.updateMultiselect = updateMultiselect;
window.togglePasswordVisibility = togglePasswordVisibility;
window.confirmReset  = confirmReset;
window.refreshNarrative = refreshNarrative;
window.downloadBackup   = downloadBackup;
window.uploadRestore    = uploadRestore;

// Auto-init if either tab is already active on page load
document.addEventListener("DOMContentLoaded", function () {
  const strategyContainer = document.getElementById("strategy-container");
  if (strategyContainer && (strategyContainer.classList.contains("tab-content-active") ||
      strategyContainer.style.display !== "none")) {
    initStrategy();
  }
  const settingsContainer = document.getElementById("settings-container");
  if (settingsContainer && (settingsContainer.classList.contains("tab-content-active") ||
      settingsContainer.style.display !== "none")) {
    initSettings();
  }
});
