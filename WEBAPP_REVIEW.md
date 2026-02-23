# Webapp Review: Look & Feel, Mobile, Consistency, and Bugs

## 1. BUGS

### 1.1 CSS Syntax Error in base.html — Missing closing brace
**File:** `webapp/templates/base.html` ~line 237  
**Issue:** The `.stat-card:hover` rule is missing its closing `}`. This causes `.stat-card .stat-value` and `.stat-card .stat-label` to be parsed as nested selectors inside the `:hover` block, which is invalid CSS. This likely breaks stat card styling on the stats page and anywhere stat cards are used.

```css
/* BROKEN — missing closing brace */
.stat-card:hover {
    border-left-width: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);

.stat-card .stat-value {
```

**Fix:** Add `}` after the `box-shadow` line in `.stat-card:hover`.

---

### 1.2 Global `* { transition: all 0.2s ease-in-out }` causes performance issues
**File:** `webapp/templates/base.html` ~line 34  
**Issue:** Applying transitions to ALL elements (`*`) causes unintended visual artifacts — layout shifts, sluggish scrolling, flickering on page load (especially mobile), and makes the `fadeInUp` animation on `.container` conflict with all child element transitions. This is particularly bad on low-powered mobile devices.

**Fix:** Remove the global `*` transition. Apply transitions only to specific interactive elements (buttons, cards, links, nav items).

---

### 1.3 `format_mark` labels Discus and Shot Put as "jump events"
**File:** `webapp/app.py` ~line 123 (and JavaScript duplicate ~line 305 of season_bests_2025.html)  
**Issue:** The variable `jump_events` includes `'Discus'` and `'Shot Put'`, which are throw events. The code converts their marks from meters to feet/inches, which is correct behavior for US display, but the variable name is misleading. More importantly, if any new throw event is added (e.g., Javelin), it won't be converted unless manually added to this list.

**Fix:** Rename to `imperial_events` or `feet_inch_events` and ensure all field events that should display in imperial are included.

---

### 1.4 Duplicate `import datetime` inside routes
**File:** `webapp/app.py` — `index()` ~line 214, `calendar()` ~line 252  
**Issue:** `datetime` and `json` are re-imported inside individual route functions even though they're already imported at the top of the file. Not a runtime bug but clutters the code and is inconsistent.

**Fix:** Remove the redundant imports from inside the route functions.

---

### 1.5 Hardcoded graduation year to grade mapping
**File:** `webapp/app.py` — multiple locations  
**Issue:** Grade is computed as:
```python
CASE WHEN graduation_year = 2026 THEN '12th' ...
```
This will be wrong next school year. Every year these values need manual updating.

**Fix:** Compute grade dynamically based on the current year or season year.

---

### 1.6 Communications page has stale/placeholder data
**File:** `webapp/templates/communications.html`  
**Issue:** The "2025 Meet Schedule" section has only 3 hardcoded meets (Jan 18, Jan 25, Feb 1) with a note "More meets will be added." The actual calendar page has current data. The "Team Calendar" and "Forms & Documents" links under "Important Links" point to `#` (broken links).

**Fix:** Either pull schedule data dynamically (like the calendar page does) or remove the duplicate hardcoded schedule. Fix or remove the `#` placeholder links.

---

### 1.7 `athlete_stats.html` has place column missing responsive hiding
**File:** `webapp/templates/athlete_stats.html` ~line 167  
**Issue:** The `<td>{{ result.place or '-' }}</td>` column has no responsive class (unlike the Level column which uses `d-none d-md-table-cell`), but the `<th>` for Place uses `d-none d-md-table-cell`. This means the header hides on mobile but the data cell doesn't, causing column misalignment.

**Fix:** Add `class="d-none d-md-table-cell"` to the Place `<td>`.

---

### 1.8 Band App CTA on home page has a dead link
**File:** `webapp/templates/index.html` ~line 30  
**Issue:** The "Get the Band App" button links to `#` instead of the actual Band app URL. The communications page has the correct URL (`https://band.us/n/a2afbeUbC5j2G`).

**Fix:** Replace `href="#"` with the actual Band app link.

---

## 2. MOBILE IMPROVEMENTS

### 2.1 Navbar collapses but has no visual cue for current page on mobile
**Issue:** When the navbar is collapsed on mobile, tapping the hamburger shows the menu, but the active state styling (purple highlight) is subtle. Users may not notice which page they're on.

**Fix:** Make the active nav link more visually distinct in mobile view — e.g., add a left border accent or bolder background color.

---

### 2.2 Home page Band App CTA banner layout breaks on small screens
**File:** `webapp/templates/index.html` ~line 15  
**Issue:** The alert uses `<div class="row align-items-center">` with `col` and `col-auto` — on narrow screens, the button doesn't wrap properly and can overflow or squeeze the text.

**Fix:** Use `col-12` for both on mobile with stacking: `<div class="col-12 col-md">` and `<div class="col-12 col-md-auto mt-2 mt-md-0">`.

---

### 2.3 Calendar mobile view is very cramped
**File:** `webapp/templates/calendar.html`  
**Issue:** The mobile calendar shows tiny event badges (V, JV, calendar icon) at 0.6rem font size. Multiple events on the same day are nearly impossible to read. The modal helps, but the badges give almost no context about which event they refer to.

**Fix:** Consider a list view alternative for mobile instead of the grid calendar. Show events as a chronological list with date, title, time, and location clearly visible.

---

### 2.4 PR cards on athlete page can be very small and cramped on mobile
**File:** `webapp/templates/athlete_stats.html`  
**Issue:** PR cards use `col-6` on mobile, which works for shorter event names but causes awkward wrapping for long names like "300m Hurdles" or "Triple Jump". The PR time at 1.75rem can overflow.

**Fix:** Use `col-12 col-sm-6 col-md-4` so PR cards go full-width on very small screens.

---

### 2.5 Plotly charts don't resize well on orientation change
**File:** `webapp/templates/athlete_stats.html`  
**Issue:** Plotly charts inside collapsible cards don't automatically resize when a phone rotates from portrait to landscape. The `responsive: true` config helps on initial load but not always on orientation changes.

**Fix:** Add a `resize` event listener that calls `Plotly.Plots.resize()` on all visible chart elements after orientation change.

---

### 2.6 Season Bests 2025 — results section has no scroll-to behavior
**File:** `webapp/templates/season_bests_2025.html`  
**Issue:** On mobile, after tapping an event card, the results render below the cards, but the user may need to scroll down to see them. There's no auto-scroll to the results section.

**Fix:** Add `document.getElementById('${gender}-results').scrollIntoView({behavior: 'smooth'})` after rendering results in the `selectEvent()` function.

---

### 2.7 Tables have horizontal scroll but no visual indicator
**Issue:** Several pages use `table-responsive` which adds horizontal scrolling, but on mobile there's no visual hint that the table can be scrolled horizontally (no gradient, shadow, or scroll indicator).

**Fix:** Add a subtle gradient shadow on the right edge of `.table-responsive` containers to hint at scrollable content.

---

## 3. CONSISTENCY IMPROVEMENTS

### 3.1 Inconsistent page header patterns
**Issue:** Pages use different header styles:
- **Home/Stats/Communications:** Use `hero-section` (purple gradient banner)
- **Athletes/Events/Calendar/Leaderboard/Team Bests:** Use `<h1>` inside a container with `mt-4`

This creates a jarring visual difference when navigating between pages.

**Fix:** Pick one approach and apply it consistently. Either all pages get a hero section, or none do (the inline `<h1>` approach is simpler and more mobile-friendly).

---

### 3.2 Coaching staff list is duplicated
**File:** `webapp/templates/index.html` and `webapp/templates/communications.html`  
**Issue:** The exact same coaching staff list appears on both home and communications pages. If a coach is added or removed, both places need updating.

**Fix:** Extract the coaching staff into a data source (config file or database) and render it from a single template partial (`{% include 'partials/coaching_staff.html' %}`).

---

### 3.3 Gender badges use inconsistent colors
**Issue:**
- Athletes list: Male = `bg-primary` (blue), Female = `bg-danger` (red)
- Team bests: Boys = `bg-primary`, Girls = `bg-danger`
- Athlete stats page: Male = `bg-primary`, Female = `bg-danger`

The color choice of red (`bg-danger`) for girls has negative connotations. This should use a more neutral color.

**Fix:** Use a consistent, neutral color for gender badges across all pages. Consider `bg-primary` for boys and `bg-purple` (custom) or `bg-info` for girls.

---

### 3.4 Navigation doesn't highlight Stats, Events, or Communications pages
**File:** `webapp/templates/base.html` ~line 470+  
**Issue:** The navbar has active state checks for Home, Calendar, Leaderboard, Athletes, and All Time Records — but the Stats page, Events page, and Communications page are accessible via links but not in the navbar, making them feel disconnected.

**Fix:** Either add these to the nav (possibly in a dropdown "More" menu to avoid overcrowding) or ensure they're prominently linked from relevant pages.

---

### 3.5 Inconsistent card header behavior — some are clickable, some aren't
**File:** `webapp/templates/base.html`  
**Issue:** The base CSS makes `.card-header` have `cursor: pointer` and a hover effect, implying it's clickable. But only the collapsible charts on the athlete page actually have clickable headers. On all other pages, the card headers do nothing when clicked.

**Fix:** Remove `cursor: pointer` and the hover effect from the base `.card-header` style. Apply it only to card headers that are actually interactive (via a `.card-header-collapsible` class or similar).

---

### 3.6 Event card styling in season_bests_2025.html is fully custom, not using base styles
**File:** `webapp/templates/season_bests_2025.html`  
**Issue:** The Leaderboard page defines its own complete CSS for cards, results lists, and buttons inside a `<style>` block, separate from and inconsistent with the base template styles. For example, `.event-card` doesn't use the base `.card` styles at all.

**Fix:** This is a deliberate design choice for this page, but the results list (`.athlete-item`, `.athlete-rank`, etc.) could reuse the base table styling for consistency across the app.

---

### 3.7 Footer is minimal and inconsistent with the rest of the design
**File:** `webapp/templates/base.html`  
**Issue:** The footer only contains a contact email and nothing else. There are no links to major pages, no branding, and it feels disconnected.

**Fix:** Add quick navigation links in the footer (Athletes, Calendar, Leaderboard, Records) and perhaps the school branding.

---

## 4. GENERAL LOOK & FEEL IMPROVEMENTS

### 4.1 Plotly.js is loaded on every page (~3.5MB)
**File:** `webapp/templates/base.html` ~line 20  
**Issue:** Plotly.js is included in the base template, so it loads on EVERY page — even Home, Calendar, Athletes List, etc. — where no charts are ever used. This significantly slows down initial page load, especially on mobile.

**Fix:** Move the Plotly.js `<script>` tag into the `{% block extra_js %}` of only the templates that use it (athlete_stats.html, analytics.html).

---

### 4.2 No loading states or skeleton screens
**Issue:** The season bests page, analytics page, and athlete charts all load data dynamically. While waiting, users see either nothing or "Loading..." text. On slow connections this is jarring.

**Fix:** Add lightweight CSS skeleton/shimmer placeholders that show while data loads.

---

### 4.3 No "back to top" button on long pages
**Issue:** The athlete stats page and event records page can be very long. On mobile, scrolling back to the top or to the navigation requires a lot of swiping.

**Fix:** Add a floating "back to top" button that appears after scrolling past a threshold.

---

### 4.4 Custom scrollbar styling only works in WebKit browsers
**File:** `webapp/templates/base.html`  
**Issue:** The custom scrollbar CSS uses `::-webkit-scrollbar` which doesn't apply to Firefox or other non-WebKit browsers.

**Fix:** Add `scrollbar-color` and `scrollbar-width` CSS properties for Firefox support, or remove the custom scrollbar entirely since it adds little value and is inconsistent cross-browser.

---

### 4.5 No favicon for Apple touch or Android home screen
**Issue:** Only basic favicons are provided. No `apple-touch-icon` or `manifest.json` for progressive web app capabilities.

**Fix:** Add `<link rel="apple-touch-icon">` and a basic `manifest.json` so the site looks good when saved to a phone's home screen.

---

## 5. PRIORITY RECOMMENDATIONS

### High Priority (Bugs/Breaking)
- [x] **1.1** — Fix missing `}` in `.stat-card:hover` CSS *(already correct — closing brace present)*
- [x] **1.2** — Remove `* { transition }` *(already correct — no global `*` transition exists)*
- [x] **1.7** — Fix Place column responsive mismatch *(already fixed — `d-none d-md-table-cell` on both th and td)*
- [x] **1.8** — Fix Band App dead link on home page *(fixed — links to `https://band.us/n/a2afbeUbC5j2G`)*

### Medium Priority (User Experience)
- [x] **2.6** — Auto-scroll to results on leaderboard (mobile UX)
- [x] **4.1** — Move Plotly.js to only pages that need it (page load speed)
- [x] **3.1** — Consistent page headers
- [x] **3.5** — Fix misleading clickable card headers
- [x] **1.6** — Fix stale communications page data and dead `#` links
- [x] **2.2** — Fix Band CTA banner mobile layout

### Lower Priority (Polish)
- [ ] **3.2** — Extract coaching staff into shared data
- [ ] **3.3** — Neutral gender badge colors
- [ ] **2.3** — Mobile calendar list view alternative
- [ ] **4.2** — Loading skeleton screens
- [ ] **4.3** — Back to top button
- [ ] **1.5** — Dynamic grade calculation (hardcoded 2026=12th etc. in 4 places in app.py)
- [ ] **1.3** — Rename `jump_events` to `imperial_events` (misleading variable name)
- [ ] **1.4** — Remove duplicate `import datetime`/`import json` inside `index()` and `calendar()` routes
- [x] **4.5** — Add apple-touch-icon for home screen *(done — uses logo.png)*
