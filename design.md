# Dashboard Design System (CSS/HTML Export)

This document captures the reusable look-and-feel used by this dashboard so you can lift it into other apps.

## 1) Fonts

Use these fonts (or swap to your own equivalents):

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap">
```

- UI: `Space Grotesk`
- Numbers/telemetry: `DM Mono`

## 2) Theme Tokens (Light/Dark)

Theme is driven by CSS variables. Toggle by setting `data-theme="dark"` on `<html>`.

```css
:root {
  color-scheme: light;
  --bg: #f5f1ea;
  --ink: #1d2b24;
  --muted: rgba(29, 43, 36, 0.55);

  --accent: #2c9c8f;
  --accent-strong: #1c6c62;
  --accent-soft: #eaf6f3;

  --card: #ffffff;
  --card-alt: #f7faf8;
  --card-glass: rgba(255, 255, 255, 0.86);
  --border: rgba(29, 43, 36, 0.12);
  --shadow: 0 20px 55px rgba(29, 43, 36, 0.12);

  /* Charts */
  --chart-text: #1d2b24;
  --chart-grid: rgba(29, 43, 36, 0.12);
  --chart-aqi: #d66c53;
  --chart-temp: #2c9c8f;
  --chart-humidity: #3b78b9;
  --chart-fan: #e0b457;
}

html[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f1311;
  --ink: #f5f4f0;
  --muted: rgba(245, 244, 240, 0.55);

  --accent: #3bb8a5;
  --accent-strong: #2a8f82;
  --accent-soft: rgba(59, 184, 165, 0.18);

  --card: #151a18;
  --card-alt: #1b221f;
  --card-glass: rgba(18, 22, 20, 0.88);
  --border: rgba(245, 244, 240, 0.12);
  --shadow: 0 26px 60px rgba(0, 0, 0, 0.45);

  --chart-text: #f5f4f0;
  --chart-grid: rgba(245, 244, 240, 0.14);
  --chart-aqi: #f08e74;
  --chart-temp: #53d1bc;
  --chart-humidity: #6aa8e6;
  --chart-fan: #f2c86d;
}
```

## 3) Base Page Background

This gives the “soft gradient glass” vibe with a subtle grid overlay.

```css
body {
  font-family: "Space Grotesk", system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
  overflow-x: hidden;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  background:
    radial-gradient(circle at 10% 0%, rgba(44, 156, 143, 0.18), transparent 55%),
    radial-gradient(circle at 90% 15%, rgba(224, 180, 87, 0.22), transparent 45%),
    radial-gradient(circle at 30% 90%, rgba(214, 108, 83, 0.18), transparent 60%);
  pointer-events: none;
  z-index: -2;
}

body::after {
  content: "";
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(29, 43, 36, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(29, 43, 36, 0.04) 1px, transparent 1px);
  background-size: 44px 44px;
  pointer-events: none;
  z-index: -1;
  opacity: 0.35;
}

html[data-theme="dark"] body::before {
  background:
    radial-gradient(circle at 10% 0%, rgba(59, 184, 165, 0.2), transparent 55%),
    radial-gradient(circle at 90% 15%, rgba(242, 200, 109, 0.15), transparent 50%),
    radial-gradient(circle at 30% 90%, rgba(240, 142, 116, 0.18), transparent 60%);
}

html[data-theme="dark"] body::after {
  background-image:
    linear-gradient(rgba(245, 244, 240, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(245, 244, 240, 0.04) 1px, transparent 1px);
}
```

## 4) Layout: Full-width Top Bar + Masonry Columns

Goal:
- The top status bar spans the full viewport width.
- All “cards” below stack down columns (no row-gap holes) and reflow when collapsing.

```css
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  width: 100%;
}

.top-status {
  background: var(--card-glass);
  border: 1px solid var(--border);
  border-radius: 0 0 18px 18px;
  padding: 18px 20px;
  box-shadow: var(--shadow);
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(10px);

  /* Full-bleed */
  width: 100vw;
  margin-left: calc(50% - 50vw);
  margin-right: calc(50% - 50vw);
}

.dashboard-masonry {
  max-width: 2200px;
  margin: 0 auto;
  padding: 18px 20px 40px;
  column-gap: 18px;
  column-width: 520px; /* controls “card width”; browser chooses column count */
  column-fill: balance;
}

.dashboard-masonry > * {
  display: inline-block;
  width: 100%;
  vertical-align: top;
  margin: 0 0 18px;
  break-inside: avoid;
  page-break-inside: avoid;
  -webkit-column-break-inside: avoid;
}

@media (max-width: 980px) {
  .top-status { position: static; }
  .dashboard-masonry {
    column-count: 1;
    column-width: auto;
    padding: 16px 16px 32px;
  }
}
```

## 5) Core Components

### 5.1 “Glass Card” Sections (Weather/Graphs/Schedule/Logging/etc.)

```css
.weather-section,
.graph-section,
.schedule-section {
  background: var(--card-glass);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow);
}
```

### 5.2 Collapsible Header + Content

```css
.collapsible-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 14px 16px;
  user-select: none;
  background: transparent;
}

.collapsible-header:hover {
  background: rgba(44, 156, 143, 0.08);
}

.collapsible-title {
  font-size: 14px;
  font-weight: 600;
  opacity: 0.9;
}

.collapse-icon {
  font-size: 0;
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.collapse-icon::after {
  content: ">";
  font-size: 14px;
  color: var(--muted);
  transition: transform 0.3s ease;
}

.collapsible-header.collapsed .collapse-icon::after {
  transform: rotate(-90deg);
}

.collapsible-content {
  overflow: hidden;
  padding: 0 16px 16px;
  max-height: 2000px;
  transition: max-height 0.3s ease-out, padding 0.3s ease-out;
}

.collapsible-content.collapsed {
  max-height: 0;
  padding: 0 16px;
}
```

Example HTML:

```html
<div class="schedule-section">
  <div class="collapsible-header collapsed" onclick="toggleCollapse(this, 'example')">
    <div class="collapsible-title">Section Title</div>
    <div class="collapse-icon">></div>
  </div>
  <div class="collapsible-content collapsed" id="example-content-wrapper">
    <div>Section content...</div>
  </div>
</div>
```

### 5.3 Buttons

Primary:

```css
.btn {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
  padding: 14px 24px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
  margin-top: 10px;
  transition: background 0.2s ease;
}

.btn:hover { background: var(--accent-strong); }
```

Secondary (theme-safe in dark mode):

```css
.btn-secondary {
  background: var(--card-alt);
  border: 1px solid var(--border);
  color: var(--ink);
}

.btn-secondary:hover { background: var(--card); }
```

### 5.4 Inputs

```css
.select-input,
.number-input {
  background: var(--card);
  border: 1px solid var(--border);
  color: var(--ink);
  border-radius: 8px;
  padding: 12px;
  font-size: 16px;
  width: 100%;
}

.slider {
  height: 8px;
  border-radius: 4px;
  background: #e5ece8;
  outline: none;
  -webkit-appearance: none;
}

.slider::-webkit-slider-thumb,
.slider::-moz-range-thumb {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: none;
}
```

### 5.5 Toggle Switch

Use a hidden checkbox + `.toggle-slider`.

```html
<label class="toggle-switch">
  <input type="checkbox" />
  <span class="toggle-slider"></span>
</label>
```

### 5.6 Toast

```css
.toast {
  position: fixed;
  bottom: 20px;
  left: 20px;
  right: 20px;
  background: #1d2b24;
  color: #f5f1ea;
  border: 1px solid rgba(29, 43, 36, 0.25);
  padding: 15px 20px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  z-index: 2000;
  display: none;
}

.toast.show { display: block; }
.toast.success { background: #2b7d6f; }
.toast.error { background: #b8493a; }
```

## 6) “Mode Panel” Card (Side Menu + Settings Panel)

Pattern:
- A card-style side menu using `.menu-item` tiles.
- A settings panel container with rounded corners + subtle header gradient.

Minimal structure:

```html
<div class="main-layout">
  <div class="side-menu">
    <div class="menu-item active"><div class="menu-icon">…</div><div class="menu-label">Auto</div></div>
    <div class="menu-item"><div class="menu-icon">…</div><div class="menu-label">Curve</div></div>
  </div>
  <div class="content-area">
    <div class="settings-panel">
      <div class="settings-header"><div class="settings-title">Select a Mode</div></div>
      <div class="settings-content">…</div>
    </div>
  </div>
</div>
```

## 7) Modal Overlay (Log Explorer)

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  z-index: 3000;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.modal-overlay.show { display: flex; }

.modal-container {
  background: var(--card);
  border-radius: 16px;
  max-width: 700px;
  width: 100%;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
```

## 8) Integration Checklist

- Copy token blocks from **(2)** and base background from **(3)**.
- Copy layout from **(4)** and wrap your cards inside:
  - `<div class="app-container">`
  - full-width `<div class="top-status">…</div>`
  - `<div class="dashboard-masonry">…cards…</div>`
- Reuse components from **(5)** for collapsibles/buttons/inputs/toasts.
- Toggle theme by setting `<html data-theme="dark">` (and store it in `localStorage` if desired).

