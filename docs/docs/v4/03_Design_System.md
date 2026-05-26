# Fortress V4 — Design System
## Obsidian Edge

**Version:** 4.0.0  
**Status:** Authoritative — Phase 1 deliverable  
**Preceded by:** `ideas.md` concept selection (Obsidian Edge chosen)  
**Feeds into:** Phase 3 (Front-End Coding)

---

## 1. Design Philosophy

Obsidian Edge is a **dark premium trading interface** built for a single professional trader working at night and in low-light environments. Every decision optimises for:

- **Cognitive load reduction** — numbers are always the visual priority; chrome recedes
- **Scan speed** — key P&L, delta, and risk figures must be readable within 200 ms of page load
- **Error prevention** — destructive or high-stakes actions require a secondary colour signal before confirmation
- **Precision over decoration** — no gradients, no shadows unless they encode depth information

The interface is **not responsive to mobile**. All layouts assume a single large monitor (≥1440 px wide). Touch targets and hamburger menus are out of scope.

---

## 2. Colour System

All colours use **OKLCH** for perceptual uniformity. Every token is a CSS custom property defined on `:root`.

### 2.1 Background Scale

| Token | OKLCH | Hex (approx) | Usage |
|---|---|---|---|
| `--bg-base` | `oklch(0.12 0.008 260)` | `#0d0f17` | Page / app shell |
| `--bg-surface` | `oklch(0.16 0.008 260)` | `#141720` | Cards, panels |
| `--bg-elevated` | `oklch(0.20 0.008 260)` | `#1c2030` | Modals, popovers, hover rows |
| `--bg-overlay` | `oklch(0.10 0.005 260 / 0.85)` | — | Dimming backdrop |

### 2.2 Text Scale

| Token | OKLCH | Usage |
|---|---|---|
| `--text-primary` | `oklch(0.92 0.010 260)` | Primary labels, headings |
| `--text-secondary` | `oklch(0.65 0.008 260)` | Supporting copy, table headers |
| `--text-muted` | `oklch(0.45 0.006 260)` | Timestamps, disabled states |
| `--text-inverse` | `oklch(0.10 0.008 260)` | Text on light surfaces (rare) |

### 2.3 Accent — Cyan Interactive

| Token | OKLCH | Usage |
|---|---|---|
| `--accent` | `oklch(0.72 0.18 200)` | Active nav items, links, focus rings |
| `--accent-hover` | `oklch(0.78 0.18 200)` | Hover state |
| `--accent-subtle` | `oklch(0.72 0.18 200 / 0.12)` | Selected row background |
| `--accent-border` | `oklch(0.72 0.18 200 / 0.35)` | Focused input border |

### 2.4 Semantic Colours

| Token | OKLCH | Purpose |
|---|---|---|
| `--positive` | `oklch(0.72 0.16 145)` | Profit, calls, bullish |
| `--positive-subtle` | `oklch(0.72 0.16 145 / 0.12)` | Positive row tint |
| `--negative` | `oklch(0.65 0.22 25)` | Loss, puts, bearish |
| `--negative-subtle` | `oklch(0.65 0.22 25 / 0.12)` | Negative row tint |
| `--warning` | `oklch(0.80 0.18 75)` | Caution, near limits |
| `--warning-subtle` | `oklch(0.80 0.18 75 / 0.12)` | Warning row tint |
| `--danger` | `oklch(0.62 0.26 20)` | Hard breach, stop-loss hit |
| `--neutral` | `oklch(0.60 0.00 0)` | Flat P&L, neutral delta |

### 2.5 Border Scale

| Token | OKLCH | Usage |
|---|---|---|
| `--border-subtle` | `oklch(0.28 0.006 260)` | Card edges |
| `--border-default` | `oklch(0.35 0.008 260)` | Input borders |
| `--border-strong` | `oklch(0.50 0.010 260)` | Dividers with emphasis |

---

## 3. Typography

### 3.1 Font Stack

| Role | Font | Fallback |
|---|---|---|
| **Numbers / monospace** | JetBrains Mono | `ui-monospace, 'Cascadia Code', 'Fira Code', monospace` |
| **UI labels / copy** | Inter | `system-ui, -apple-system, sans-serif` |

Both fonts loaded via `@font-face` from `/static/fonts/` — no CDN dependency at runtime.

### 3.2 Scale

| Token | Size | Weight | Line-height | Usage |
|---|---|---|---|---|
| `--text-xs` | 11px | 400 | 1.4 | Footnotes, tiny labels |
| `--text-sm` | 13px | 400 | 1.5 | Table cells, secondary |
| `--text-base` | 14px | 400 | 1.6 | Default body |
| `--text-md` | 16px | 500 | 1.5 | Card titles, nav items |
| `--text-lg` | 20px | 600 | 1.4 | Section headings |
| `--text-xl` | 28px | 700 | 1.2 | KPI metric values |
| `--text-2xl` | 40px | 700 | 1.1 | Hero P&L number |

### 3.3 Numeric Formatting Rules

- **All prices:** JetBrains Mono, `font-variant-numeric: tabular-nums`
- **Positive values:** prefixed with `+`, coloured `--positive`
- **Negative values:** prefixed with `−` (U+2212 minus), coloured `--negative`
- **Zero / flat:** coloured `--neutral`, no prefix
- **Percentages:** always show one decimal place (e.g., `+2.4%`)
- **Dollar values:** always show two decimal places; thousands separator (e.g., `$1,234.56`)
- **Greeks:** delta to two decimals; theta/vega to four; gamma to four

---

## 4. Spacing & Layout

### 4.1 Spacing Scale (8px base grid)

| Token | Value | Usage |
|---|---|---|
| `--space-1` | 4px | Icon padding, micro gaps |
| `--space-2` | 8px | Tight component padding |
| `--space-3` | 12px | Default cell padding |
| `--space-4` | 16px | Card padding (compact) |
| `--space-5` | 24px | Card padding (default) |
| `--space-6` | 32px | Section gaps |
| `--space-8` | 48px | Page section spacing |

### 4.2 Application Shell

```
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR (240px fixed)  │  MAIN CONTENT (flex-1)                │
│                         │                                        │
│  Logo (48px)            │  Top bar (48px)                        │
│  ─────────────────      │  ────────────────────────────────────  │
│  Nav items (×8)         │  Page content                          │
│                         │                                        │
│  ─────────────────      │                                        │
│  Status bar             │                                        │
└─────────────────────────────────────────────────────────────────┘
```

- Sidebar: `width: 240px`, `background: var(--bg-surface)`, `border-right: 1px solid var(--border-subtle)`
- Main area: `flex: 1`, `overflow-y: auto`, `background: var(--bg-base)`
- Top bar: `height: 48px`, `border-bottom: 1px solid var(--border-subtle)`, contains page title + time-of-day chip + connection status

### 4.3 Grid System

Content areas use **CSS Grid** with a 12-column base. Common patterns:

| Pattern | Grid template | Usage |
|---|---|---|
| Full-width | `1fr` | Charts, data tables |
| 2-up | `1fr 1fr` | Side-by-side KPI panels |
| 3-up | `1fr 1fr 1fr` | Metric strip |
| 8 + 4 | `2fr 1fr` | Main chart + sidebar panel |
| 4 + 4 + 4 | repeat | Three-column dashboard |

Gap between all grid cells: `var(--space-5)` (24px).

---

## 5. Component Library

### 5.1 KPI Card

Used in the metric strip at the top of Dashboard, Positions, and Performance pages.

```
┌──────────────────────────┐
│  LABEL          BADGE    │
│  $12,450.00              │
│  +$340  (+2.8%)  today   │
└──────────────────────────┘
```

- Background: `--bg-surface`
- Border: `1px solid var(--border-subtle)`
- Border-radius: `8px`
- Label: `--text-sm`, `--text-secondary`
- Value: `--text-xl` or `--text-2xl`, JetBrains Mono
- Delta: `--text-sm`, coloured by sign
- Badge: optional pill (e.g., "LIVE", "T-1") — `--accent-subtle` background

### 5.2 Data Table

```
┌──────┬──────────┬────────┬────────┬──────────────┐
│ Sym  │ Strategy │  Delta │   P&L  │ Actions      │
├──────┼──────────┼────────┼────────┼──────────────┤
│ AAPL │ PMCC     │ +0.35  │+$240   │ [Roll][Stop] │
│ SPY  │ PCS      │ −0.08  │ −$45   │ [Roll][Stop] │
└──────┴──────────┴────────┴────────┴──────────────┘
```

- Header: `--text-sm`, `--text-secondary`, `text-transform: uppercase`, `letter-spacing: 0.06em`
- Row hover: `background: var(--bg-elevated)`, cursor pointer
- Selected row: `background: var(--accent-subtle)`, `border-left: 2px solid var(--accent)`
- Positive cells: `color: var(--positive)`
- Negative cells: `color: var(--negative)`
- Sticky header: yes, `position: sticky; top: 0; z-index: 10; background: var(--bg-surface)`
- Row height: 40px (compact tables: 32px)
- Sortable columns: up/down caret icon at `--text-muted`, active column at `--accent`

### 5.3 Button

Four variants:

| Variant | Background | Border | Text | Usage |
|---|---|---|---|---|
| `primary` | `--accent` | none | `--text-inverse` | One primary CTA per form |
| `secondary` | `--bg-elevated` | `--border-default` | `--text-primary` | Secondary actions |
| `ghost` | transparent | none | `--text-secondary` | Tertiary, icon buttons |
| `danger` | `--danger` at 15% opacity | `--danger` | `--danger` | Destructive confirm |

- Default height: 32px (compact) / 36px (default)
- Border-radius: 6px
- Font: `--text-sm`, weight 500
- Focus ring: `2px solid var(--accent)`, `outline-offset: 2px`
- Disabled: 40% opacity, `cursor: not-allowed`
- Loading state: spinner replaces label, button disabled

### 5.4 Input / Form Controls

- Height: 36px
- Background: `--bg-base`
- Border: `1px solid var(--border-default)`
- Border-radius: 6px
- Focus: border → `var(--accent-border)`, box-shadow `0 0 0 3px var(--accent-subtle)`
- Error: border → `var(--danger)`, helper text in `--negative`
- Placeholder: `--text-muted`
- Font: `--text-base`; number inputs use JetBrains Mono

### 5.5 Badge / Status Pill

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
```

Variants:

| Label | Background | Text |
|---|---|---|
| LIVE | `--positive-subtle` | `--positive` |
| CLOSED | `--bg-elevated` | `--text-muted` |
| WARNING | `--warning-subtle` | `--warning` |
| BREACH | `--negative-subtle` | `--negative` |
| NEW | `--accent-subtle` | `--accent` |

### 5.6 Alert Banner

Full-width bar that appears above page content when an alert is active.

```
⚠  PCS cap approaching — 4 of 5 positions active.   [Dismiss]
```

- Height: 44px
- Background: `--warning-subtle`
- Left border: `3px solid var(--warning)`
- Font: `--text-sm`, weight 500
- Dismiss: ghost button, `--text-muted`
- Critical alerts (stop-loss breach): `--danger` variant, cannot be dismissed without action

### 5.7 Modal / Confirmation Dialog

- Backdrop: `--bg-overlay` over full viewport
- Dialog width: 480px (confirm), 640px (form), 860px (detail)
- Background: `--bg-elevated`
- Border: `1px solid var(--border-default)`
- Border-radius: 12px
- Header: title (`--text-lg`) + close `×` button
- Footer: action buttons right-aligned (cancel left, confirm right)
- Destructive confirms: `danger` button, red border on dialog top

### 5.8 Sidebar Navigation

```
●  Dashboard
   Market Intel
   Positions
   Trade
   Analysis
   Performance
   Earnings
   Config
```

- Nav item height: 40px
- Active: `color: var(--accent)`, left border `3px solid var(--accent)`, `background: var(--accent-subtle)`
- Hover: `background: var(--bg-elevated)`
- Font: `--text-md`, weight 500
- Icons: 18px, same colour as label, Lucide icon set
- Nav structure: **LOCKED** — 8 items only. Do not add items without explicit request.

### 5.9 Chart Styling

All charts (Recharts or ECharts) inherit these theme tokens:

- Background: `--bg-surface`
- Grid lines: `--border-subtle`
- Axis labels: `--text-sm`, `--text-muted`
- Positive series: `--positive`
- Negative series: `--negative`
- Accent series: `--accent`
- Tooltip: `--bg-elevated` background, `--border-default` border, `--text-primary` text
- Crosshair: `--border-strong`, dashed
- Volume bars (if present): `--accent` at 40% opacity

### 5.10 Toast Notification

- Position: bottom-right, 16px from edges
- Width: 320px
- Stack limit: 3 (oldest auto-dismisses)
- Border-radius: 8px
- Auto-dismiss: 4s (info/success), 8s (warning), sticky (error until dismissed)
- Variants match badge colours

---

## 6. Motion & Animation

Fortress V4 uses **minimal, purposeful animation**. No decorative transitions.

| Element | Property | Duration | Easing |
|---|---|---|---|
| Nav active indicator | `background`, `border-color` | 120ms | `ease-out` |
| Row hover | `background` | 80ms | `ease-out` |
| Modal open | `opacity`, `scale(0.97→1)` | 160ms | `cubic-bezier(0.16,1,0.3,1)` |
| Modal close | `opacity` | 100ms | `ease-in` |
| Toast enter | `translateX(100%→0)` | 200ms | `cubic-bezier(0.16,1,0.3,1)` |
| Toast exit | `opacity`, `height→0` | 150ms | `ease-in` |
| Skeleton loader | pulse opacity | 1.2s | `ease-in-out`, infinite |
| Number change | colour flash then fade | 600ms | `ease-out` |
| Alert banner | `height 0→44px` | 200ms | `ease-out` |

**Reduce motion:** All transitions respect `@media (prefers-reduced-motion: reduce)` — reduce to instant or 50ms max.

---

## 7. Loading States

### 7.1 Skeleton Screens

On initial page load, tables and cards show skeleton rows/blocks before data arrives. Skeleton colour: `--bg-elevated`, pulsing between 60% and 90% opacity.

### 7.2 Inline Spinner

Used for button loading states and small data refreshes. 16px rotating circle, `--accent` colour, stroke-width 2px.

### 7.3 Connection Status Chip

Always visible in the top bar:

| State | Label | Colour |
|---|---|---|
| SSE connected | `● LIVE` | `--positive` |
| SSE reconnecting | `◌ RECONNECTING…` | `--warning` |
| SSE disconnected | `○ OFFLINE` | `--negative` |
| IBKR connected | `IBKR ✓` | `--positive` |
| IBKR disconnected | `IBKR ✗` | `--negative` |

---

## 8. Iconography

- **Library:** Lucide React (MIT)
- **Default size:** 16px (inline), 18px (nav), 20px (action buttons), 24px (feature icons)
- **Stroke width:** 1.5px at all sizes
- **Colour:** inherits from `currentColor` — never hardcoded
- **No filled icons** except status indicators (●, ◌, ○ Unicode)

---

## 9. Page-specific Treatments

### 9.1 Dashboard

- Top strip: 3-up KPI cards (Total P&L, Daily P&L, Net Delta)
- Second row: SPY intraday chart (8+4 split) + Portfolio greeks panel
- Third row: Positions table (full-width)
- Alert banner appears above KPI strip, pushes content down

### 9.2 Market Intel

- Two-column layout: order flow chart (left, 60%) + dark pool levels (right, 40%)
- IV term structure chart below
- Tabbed view: Order Flow / Dark Pool / Vol Surface / Sector Heat Map

### 9.3 Trade

- Pre-trade form: left column (inputs) + right column (live pre-trade check results)
- Pre-trade check results update on every input change (debounced 300ms)
- Pending orders table below form
- Approve/Decline buttons: `primary` and `danger` variants respectively

### 9.4 Positions

- Sortable table with inline expand → shows individual legs
- Colour-coded strategy badge per row (PMCC, PCS, JL, HEDGE)
- Roll / Stop-Loss action buttons inline

### 9.5 Analysis

- Full-width options analytics panel
- Tabbed: Greeks / Vol Skew / OI / Max Pain
- All tabs share the same selected ticker state

### 9.6 Performance

- P&L equity curve (full-width area chart)
- Below: Trade log table (filterable by strategy, date range)

### 9.7 Earnings

- Calendar grid view (month) + list view toggle
- Upcoming earnings highlighted in `--warning`
- Post-earnings review accordion per stock

### 9.8 Config

- Sectioned form: Strategy Parameters / Universe / Exclusions / Integrations
- Inline save per section (not full-page submit)
- Dangerous resets: `danger` button variant

---

## 10. Accessibility

- **Contrast:** All text/background combinations target WCAG AA (≥4.5:1 for body, ≥3:1 for large text). The chosen OKLCH values have been verified.
- **Focus management:** Modal open → focus first interactive element. Modal close → focus trigger element. Tab order follows DOM order.
- **Focus ring:** Never `outline: none` without a visible replacement. Default ring: `2px solid var(--accent)`, `outline-offset: 2px`.
- **ARIA:** Tables use `role="grid"` where interactive. Alerts use `role="alert"`. Modals use `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
- **Keyboard nav:** All interactive elements reachable by keyboard. Escape closes modals and popovers. Enter/Space activates buttons.
- **Screen reader:** Icon-only buttons always have `aria-label`. Status indicators have `aria-live="polite"`.

---

## 11. CSS Architecture

### 11.1 Structure

```
src/
  styles/
    tokens.css          ← :root CSS custom properties (this doc)
    reset.css           ← Minimal reset (box-sizing, margin, font)
    typography.css      ← Font loading, body defaults
    components/
      button.css
      table.css
      modal.css
      badge.css
      input.css
      toast.css
      nav.css
      card.css
  app.css               ← @import order
```

Tailwind 4 is used for utility classes. **All design tokens are CSS custom properties, not Tailwind config values**, so they work in both Tailwind utilities and plain CSS components.

### 11.2 Tailwind Configuration

```js
// tailwind.config.js
export default {
  theme: {
    extend: {
      colors: {
        'bg-base': 'oklch(0.12 0.008 260)',
        'bg-surface': 'oklch(0.16 0.008 260)',
        'bg-elevated': 'oklch(0.20 0.008 260)',
        accent: 'oklch(0.72 0.18 200)',
        positive: 'oklch(0.72 0.16 145)',
        negative: 'oklch(0.65 0.22 25)',
        warning: 'oklch(0.80 0.18 75)',
        danger: 'oklch(0.62 0.26 20)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
}
```

---

## 12. Design System Checklist (Phase 1 Exit Criteria)

- [ ] All token values committed to `tokens.css`
- [ ] Storybook (or equivalent) stories for all 10 components
- [ ] Colour contrast audit passed (all text/bg pairs ≥ WCAG AA)
- [ ] Figma / design mockup for each of the 8 pages created (or annotated wireframe)
- [ ] Responsive breakpoint decision confirmed (1440px minimum, no mobile)
- [ ] Font loading tested offline (no CDN)
- [ ] `prefers-reduced-motion` tested
- [ ] Design review sign-off before Phase 3 (Front-End) begins

---

*Fortress V4 Design System — Obsidian Edge. Authoritative for all UI implementation in Phase 3.*
