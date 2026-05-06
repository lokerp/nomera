---
name: Nomera Operations UI
description: Calm, clear, and friendly dashboard system for parking access operations.
colors:
  primary: "#0ea5e9"
  primary-strong: "#0284c7"
  neutral-bg: "#f3f6fb"
  neutral-surface: "#ffffff"
  neutral-text: "#0f172a"
  neutral-muted: "#64748b"
  neutral-border: "#dbe5ef"
  neutral-border-strong: "#c5d2df"
  success: "#22c55e"
  success-strong: "#166534"
  danger: "#ef4444"
  danger-strong: "#b91c1c"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1.2
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "20px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.primary-strong}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  button-danger:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.danger-strong}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  card-default:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.xl}"
    padding: "14px"
  chip-info:
    backgroundColor: "{colors.neutral-bg}"
    textColor: "{colors.primary-strong}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "24px"
  input-default:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "36px"
---

# Design System: Nomera Operations UI

## 1. Overview

**Creative North Star: "The Calm Control Atlas"**

This system is an approachable operations surface for people making repetitive, high-responsibility decisions. The visual language keeps state and actions obvious first, then supports speed with stable spacing, familiar control shapes, and clear status color semantics.

The interface rejects decorative noise and favors practical legibility. Card groups, table rows, pills, and action buttons exist to organize operational choices, not to perform as visual theater. The dominant rhythm is medium density with generous grouping boundaries so users can parse quickly under live conditions.

This system explicitly rejects the anti-references from PRODUCT.md: a noisy dark-neon monitoring dashboard, over-styled marketing visuals, and dense legacy enterprise clutter.

**Key Characteristics:**
- Calm neutral canvas with one dominant operational accent (blue).
- Compact controls with predictable heights (36px) and small radius corners (6px to 14px).
- Status semantics are literal and consistent (green success, red danger, slate neutral).
- Information is grouped by task units, not decorative patterns.

## 2. Colors

The palette is restrained and operational, one primary accent over tinted light neutrals, with explicit status colors for approvals and errors.

### Primary
- **Primary** (`#0ea5e9`): default action emphasis, selected interactive states, and high-importance controls.
- **Primary Strong** (`#0284c7`): hover/active reinforcement for primary controls and accent text contrast.

### Neutral
- **Neutral Background** (`#f3f6fb`): page-level canvas and soft chip backgrounds.
- **Neutral Surface** (`#ffffff`): cards, forms, and most interactive surfaces.
- **Neutral Text** (`#0f172a`): default high-contrast copy and data labels.
- **Neutral Muted** (`#64748b`): secondary metadata, helper copy, and non-critical context.
- **Neutral Border** (`#dbe5ef`): default container and separator outlines.
- **Neutral Border Strong** (`#c5d2df`): control outlines that need stronger affordance.

### Tertiary
- **Success** (`#22c55e`): positive actions and approved status.
- **Success Strong** (`#166534`): high-contrast success text.
- **Danger** (`#ef4444`): destructive or negative actions.
- **Danger Strong** (`#b91c1c`): high-contrast danger text and error messaging.

### Named Rules
**The Single Accent Rule.** Blue is the only non-status accent. If an element is not a primary interaction or selected state, it does not use primary blue.

**The Literal Status Rule.** Green means confirmed success, red means destructive or failed state. Never invert these semantics.

## 3. Typography

**Display Font:** Inter (with system sans fallbacks)  
**Body Font:** Inter (with system sans fallbacks)  
**Label/Mono Font:** Inter (labels share the same family for consistency)

**Character:** Practical and friendly. Typography avoids stylistic flourish and instead supports quick reading in dense operational blocks.

### Hierarchy
- **Display** (700, 32px, 1.2): page-level heading anchors.
- **Headline** (700, 24px, 1.25): section anchors in major panels.
- **Title** (600, 16px, 1.35): control group and component-local titles.
- **Body** (400, 14px, 1.45): default table, form, and supporting text; keep long prose near 65 to 75ch.
- **Label** (600, 12px, 1.3): compact labels, pills, and helper markers.

### Named Rules
**The Fast Parse Rule.** Hierarchy must be obvious in one scan by weight and size changes, not by decorative color shifts.

## 4. Elevation

This system is flat-first with tonal layering. Depth is communicated primarily through border contrast and surface separation, with only light ambient shadows on larger cards and transient overlays.

### Shadow Vocabulary
- **Ambient Card Lift** (`0 6px 20px rgba(15, 23, 42, 0.04)`): default card presence on the main dashboard.
- **Overlay Lift** (`0 10px 26px rgba(15, 23, 42, 0.12)`): toasts and transient messages above the workspace.
- **Focused Panel Lift** (`0 14px 40px rgba(15, 23, 42, 0.08)`): authentication and modal-focused surfaces.

### Named Rules
**The Flat at Rest Rule.** Data surfaces are mostly flat at rest; stronger elevation appears only for overlays or context shifts.

## 5. Components

Component philosophy: practical and friendly.

### Buttons
- **Shape:** gently rounded utility corners (6px).
- **Primary:** blue action fill (`#0ea5e9`) with white text (`#ffffff`), compact horizontal padding (`0 12px`), fixed control height (`36px`).
- **Hover / Focus:** mild upward translation (`translateY(-1px)`) and stronger blue tone (`#0284c7`) on primary controls.
- **Danger / Success:** semantic text emphasis on neutral surface, preserving explicit risk and confirmation cues.

### Chips
- **Style:** rounded pills (`999px`) with light blue background (`#eff6ff`) and strong blue text (`#1e3a8a`).
- **State:** designed for concise status signaling and source type labels.

### Cards / Containers
- **Corner Style:** medium-soft corners (`14px` main cards, `8px` to `10px` for inner utility blocks).
- **Background:** white surface over cool-tinted page background.
- **Shadow Strategy:** very light ambient shadow for grouping clarity, not dramatic depth.
- **Border:** explicit soft borders (`#dbe5ef` to `#d7e1ea`) to separate dense data blocks.
- **Internal Padding:** compact-operational spacing (`10px` to `14px`) with rhythm breaks at section boundaries.

### Inputs / Fields
- **Style:** white fill, visible border (`#c5d2df`), rounded corners (`6px`), fixed field height (`36px`).
- **Focus:** focus should remain high-contrast and obvious; preserve border clarity and keyboard-visible states.
- **Error / Disabled:** error uses danger strong (`#b91c1c`), disabled reduces emphasis through opacity while retaining readability.

### Navigation
- **Style, typography, default/hover/active states, mobile treatment:** top tab row uses pill geometry; active tab shifts to blue-tinted background and blue text; small screens stack header controls while preserving full-width action availability.

## 6. Do's and Don'ts

### Do:
- **Do** keep primary controls at `36px` height with `6px` radius to preserve scan consistency across forms and tables.
- **Do** use the blue accent family (`#0ea5e9`, `#0284c7`) only for active selections and primary actions.
- **Do** keep panel borders visible (`#dbe5ef` or `#c5d2df`) to segment operational groups cleanly.
- **Do** keep success and danger semantics literal (`#22c55e` / `#ef4444`) for decision clarity.

### Don't:
- **Don't** build a noisy dark-neon monitoring dashboard.
- **Don't** introduce over-styled marketing visuals into operational surfaces.
- **Don't** recreate dense legacy enterprise clutter through excessive compression or weak grouping.
- **Don't** use gradient text, decorative glass effects, or colored side-stripe borders as accents.
