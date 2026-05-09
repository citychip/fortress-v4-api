/* ============================================================
   Fortress Dashboard — TradingView Lightweight Charts component
   Renders candlestick chart with Dark Pool floor and GEX wall
   overlays for any ticker in the Manage tab.
   Depends on: lightweight-charts (loaded via CDN in index.html)
   ============================================================ */

(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────────
  let _chartInstance = null;
  let _candleSeries  = null;
  let _priceLines    = [];
  let _currentTicker = null;

  // ── Colour palette ─────────────────────────────────────────────────────────
  const COLORS = {
    dp_floor:  { line: "#ff4d4d", title: "DP Floor" },
    gex_call:  { line: "#00e676", title: "GEX Call Wall" },
    gex_put:   { line: "#ff9800", title: "GEX Put Wall" },
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _destroyChart() {
    if (_chartInstance) {
      _chartInstance.remove();
      _chartInstance = null;
      _candleSeries  = null;
      _priceLines    = [];
    }
  }

  function _buildLegend(container, ticker, levels) {
    const old = container.querySelector(".chart-legend");
    if (old) old.remove();

    const legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.style.cssText = [
      "position:absolute", "top:8px", "left:12px",
      "background:rgba(22,26,30,0.85)", "border-radius:4px",
      "padding:6px 10px", "font-size:11px", "line-height:1.7",
      "pointer-events:none", "z-index:10",
    ].join(";");

    let html = `<strong style="font-size:13px;color:#e0e0e0">${ticker}</strong>`;

    if (levels.dp_floors && levels.dp_floors.length) {
      html += `<br><span style="color:${COLORS.dp_floor.line}">● DP Floors: `;
      html += levels.dp_floors.map(p => `$${p.toFixed(2)}`).join(", ");
      html += "</span>";
    }
    if (levels.gex_calls && levels.gex_calls.length) {
      html += `<br><span style="color:${COLORS.gex_call.line}">● GEX Calls: `;
      html += levels.gex_calls.map(p => `$${p.toFixed(0)}`).join(", ");
      html += "</span>";
    }
    if (levels.gex_puts && levels.gex_puts.length) {
      html += `<br><span style="color:${COLORS.gex_put.line}">● GEX Puts: `;
      html += levels.gex_puts.map(p => `$${p.toFixed(0)}`).join(", ");
      html += "</span>";
    }

    legend.innerHTML = html;
    container.style.position = "relative";
    container.appendChild(legend);
  }

  function _addPriceLines(levels) {
    if (!_candleSeries) return;

    // Remove old lines
    _priceLines.forEach(pl => {
      try { _candleSeries.removePriceLine(pl); } catch (_) {}
    });
    _priceLines = [];

    function addLines(prices, colorKey, labelPrefix) {
      (prices || []).forEach((price, i) => {
        const pl = _candleSeries.createPriceLine({
          price,
          color:       COLORS[colorKey].line,
          lineWidth:   1,
          lineStyle:   2,   // dashed
          axisLabelVisible: true,
          title:       `${labelPrefix} ${i + 1}`,
        });
        _priceLines.push(pl);
      });
    }

    addLines(levels.dp_floors, "dp_floor", "DP");
    addLines(levels.gex_calls, "gex_call",  "GC");
    addLines(levels.gex_puts,  "gex_put",   "GP");
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Render (or re-render) the chart for a given ticker.
   * @param {string} ticker  e.g. "MSFT"
   * @param {string} period  yfinance period: "1mo" | "3mo" | "6mo" | "1y"
   */
  window.renderChart = async function (ticker, period) {
    ticker = (ticker || "").trim().toUpperCase();
    period = period || "3mo";

    const container = document.getElementById("chart-container");
    if (!container) {
      console.error("renderChart: #chart-container not found");
      return;
    }

    if (!ticker) {
      container.innerHTML = '<p class="muted small" style="padding:16px">Select a ticker to view chart.</p>';
      return;
    }

    // Show loading state
    container.innerHTML = '<p class="muted small" style="padding:16px">Loading chart for ' + ticker + '…</p>';
    _destroyChart();

    try {
      const resp = await authFetch(`/api/chart/${ticker}?period=${period}`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        container.innerHTML = `<p class="muted small" style="padding:16px;color:var(--color-text-danger)">
          Chart error: ${err.detail || resp.statusText}</p>`;
        return;
      }
      const data = await resp.json();

      // Clear and set fixed height
      container.innerHTML = "";
      container.style.height = "420px";

      // Guard: LightweightCharts must be loaded
      if (typeof LightweightCharts === "undefined") {
        container.innerHTML = '<p class="muted small" style="padding:16px;color:var(--color-text-danger)">TradingView library not loaded.</p>';
        return;
      }

      // Create chart
      _chartInstance = LightweightCharts.createChart(container, {
        width:  container.clientWidth || 900,
        height: 420,
        layout: {
          background: { color: "#161a1e" },
          textColor:  "#c0c0c0",
        },
        grid: {
          vertLines:  { color: "#2a2e33" },
          horzLines:  { color: "#2a2e33" },
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: "#3a3e43" },
        timeScale: {
          borderColor:  "#3a3e43",
          timeVisible:  true,
          secondsVisible: false,
        },
      });

      // Resize observer
      const ro = new ResizeObserver(() => {
        if (_chartInstance) {
          _chartInstance.applyOptions({ width: container.clientWidth });
        }
      });
      ro.observe(container);

      // Candlestick series
      _candleSeries = _chartInstance.addCandlestickSeries({
        upColor:          "#26a69a",
        downColor:        "#ef5350",
        borderUpColor:    "#26a69a",
        borderDownColor:  "#ef5350",
        wickUpColor:      "#26a69a",
        wickDownColor:    "#ef5350",
      });

      _candleSeries.setData(data.candles);
      _chartInstance.timeScale().fitContent();

      // Overlay price lines
      _addPriceLines(data.levels);

      // Legend
      _buildLegend(container, ticker, data.levels);

      _currentTicker = ticker;

    } catch (err) {
      console.error("renderChart error:", err);
      container.innerHTML = `<p class="muted small" style="padding:16px;color:var(--color-text-danger)">
        Unexpected error: ${err.message}</p>`;
    }
  };

  /**
   * Refresh only the overlay levels for the currently displayed ticker.
   * Call this after a new QuantData report is uploaded.
   */
  window.refreshChartLevels = async function () {
    if (!_currentTicker || !_candleSeries) return;
    try {
      const resp = await authFetch(`/api/chart/${_currentTicker}/levels`);
      if (!resp.ok) return;
      const data = await resp.json();
      _addPriceLines(data);
      const container = document.getElementById("chart-container");
      if (container) _buildLegend(container, _currentTicker, data);
    } catch (_) {}
  };

})();
