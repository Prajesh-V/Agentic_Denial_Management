# Frontend + Stitch Design Specification

## 1. Product feel
Build an original healthcare operations workspace with the polish, focus, visual rhythm and responsiveness users associate with Spotify: a persistent dark shell, confident typography, a left navigation rail, clear primary/secondary areas, meaningful motion and low-friction transitions. **Spotify is an inspiration for experience quality, not a visual clone.** Do not use Spotify branding, logos, icons, artwork or exact page composition.

The current app is not a generic healthcare dashboard. It should feel like a premium, carefully art-directed operational instrument: lively, quick and memorable, while keeping evidence legibility and accuracy first.

## 2. Visual direction: “Nocturne Clinical Studio”
- Base surfaces: deep charcoal / near-black, not pure black everywhere.
- Layered panels: subtly lighter graphite with restrained separator lines.
- Accent: vivid but controlled green/teal used for primary actions and positive progression; amber for needs-review; red for denied/conflict/error. Never encode meaning by color alone.
- Typography: clean sans-serif for interface and a legible monospace for claim IDs, FHIR IDs, run IDs and system metadata.
- Big expressive headers only for workspace headings; dense data still uses compact, readable type.
- Selected queue row behaves like a selected item in a media library: clear highlight, not a giant poster card.
- Subtle gradients may be used as a surface accent only when they improve hierarchy. No constant animated gradients, glowing borders, glassmorphism or excessive blur.
- Charts/timelines use consistent axes, labels, units and empty/error states.

## 3. Information architecture
Primary navigation:
- Command Center
- Claims Queue
- Investigations
- Evidence Library
- Appeals & Review
- Audit Trail
- Data Lab (restricted)
- System Status

The queue should feel like a well-organized library, with search and filters always easy to reach. The investigation workspace should be a focused workbench. It should not look like a chat app.

## 4. Core screens to design in Stitch
Every screen needs a real, persistent Stitch artifact/reference before implementation; save IDs/URLs in project notes. If Stitch cannot create or retrieve an artifact, report the exact blocker rather than fabricating one.

### A. Command Center
- Today's actionable workload, assigned-to-me items, cases needing review, overdue dates, system/index health.
- Every metric links to the actual filtered list and is computed from API data.
- Empty state when no claims exist; no fake analytics.

### B. Claims Queue
- Search, filters, sort, pagination, saved views and clear filter chips.
- Claim ID, patient identifier, payer/plan, denial category, service date, denied amount, priority, assignee, deadline and current workflow state.
- Smooth row hover/selection and keyboard navigation.
- Avoid showing patient details not needed for the queue.

### C. Investigation Workspace
- Left rail: claim/denial/service-line context and policy version.
- Main panel: evidence requirements and step-by-step investigation trace.
- Right panel: best retrieved evidence with citations, dates, source type, match rationale and assessment.
- Bounded retry count and terminal reason are visible.
- Evidence state labels: Supported, Partial, Missing, Conflicting, Not evaluated.
- Responsive layouts collapse panels into tabs/drawers on narrow screens.

### D. Evidence Detail
- Actual source text with highlighting limited to terms/segments returned from evidence matching.
- Source resource/document ID, patient scope, encounter/service date, resource type, retrieval method, rank/score and source link.
- Show why the evidence was connected to a requirement; do not treat similarity score as proof.

### E. Appeals & Human Review
- Draft beside a supporting-evidence rail.
- Citations open source evidence; unknown/unvalidated citations are highlighted.
- Edit, compare versions, request revision, approve, reject.
- Approval/rejection is explicit and version-specific. Export appears only for a valid approved version.

### F. Audit Trail
- Chronological events with actor, time, action, claim/run/draft references and expandable details.
- Filters for action type, actor, claim and time range.

### G. Data Lab
- Profile/seed/version inputs, generated data counts, validation report, split summary, corpus/index build progress and rebuild action.
- Destructive namespace reset requires confirmation and clear target display.

### H. System Status
- API, database, model, retrieval index, background worker, last successful index build and recent errors.
- Distinguish ready, degraded and down. Do not fabricate a green status when checks fail.

## 5. Animation system — “motion with meaning”
Use Motion for React (`motion`) for orchestration and CSS transitions for simple properties.

Required patterns where they improve clarity:
- Route changes: short opacity/position transition with stable layout, never a long cinematic scene.
- Queue rows: restrained hover/selection feedback; filter/layout changes animate without making rows hard to track.
- Sidebars/drawers: smooth open/close and focus management.
- Evidence detail: expand/collapse, source navigation and citation focus transitions.
- Investigation state: actual backend events progressively appear in the trace; no fake steps or timer-driven “AI is thinking” progress.
- Search/filter: clear focus state and light result transitions; debounce where appropriate.
- Draft version diff: animate panel transitions lightly, not each word continuously.
- Buttons: press/hover/loading/success feedback, disabled state and accessible labels.
- Skeletons: subtle and brief, replaced by real data or error.
- Toasts: enter/exit animation and keyboard/screen-reader announcement.
- Charts/timelines: animate initial appearance and data changes only when understandable.
- Empty/error states: small transitions only; no distracting illustration loop.

### Motion quality rules
- Aim for mostly short 120–240 ms interactions; longer transitions require a reason.
- Prefer transform/opacity over expensive layout/blur animations.
- No ambient animation running indefinitely in the work area.
- Respect `prefers-reduced-motion` using Motion's reduced-motion configuration and equivalent CSS rules. Provide opacity/simple state changes instead of large movement when reduced motion is on.
- Keep focus order, keyboard interactions, screen-reader announcements and button state correct throughout transitions.
- Critical data must be instantly readable; don't delay rendering clinical evidence just for visual spectacle.
- Animation must correspond to actual state; never animate from queued to complete if the backend failed.

## 6. Frontend stack
- Next.js App Router + React + TypeScript.
- Tailwind CSS with project-owned CSS variables and design tokens.
- Motion for React (`npm install motion`) for animated transitions and interactions.
- Lucide React icons.
- Radix/shadcn primitives selectively for dialogs, menus, forms and accessibility. Do not use the stock shadcn dashboard as the entire design.
- TanStack Query for request lifecycle/cache/revalidation if justified; TanStack Table for complex tables if needed.
- Recharts or another accessible chart library only for real metrics.
- Playwright for browser workflow tests.
- Avoid adding a library simply because a template uses it; audit size, license, maintenance and compatibility.

## 7. Template and design references
Use templates as starting points, not as the product identity. Review licensing before copying code or assets.

### Best fit for coded components
- **Magic UI** — many animated React/Tailwind components, including free MIT-licensed components. Use a few micro-interactions, not flashy backgrounds throughout the workbench: https://magicui.net/ .
- **Motion Primitives** — open-source animated components built around Motion and Tailwind; useful for transitions and reusable motion patterns: https://motion-primitives.com/docs .
- **Aceternity UI** — React/Next.js/Tailwind/Motion components and templates; check which elements are free versus paid and review the applicable license: https://ui.aceternity.com/components .
- **Motion for React docs** — source of truth for animation implementation and reduced-motion behavior: https://motion.dev/docs/react-accessibility .

### Best fit for operational layout/table patterns
- **Tailwind Plus — Application UI** — production-style sidebars, tables, forms and multi-column layouts; paid license, so check current terms: https://tailwindcss.com/plus/ui-blocks/application-ui .
- **shadcn/ui Blocks** — free/open-source copy-and-paste dashboard/table/sidebar patterns. Take the structural primitives, then apply our own tokens and visual identity: https://ui.shadcn.com/blocks?category=dashboard .
- **Vercel Next.js templates** — useful for repo structure and Next.js conventions; inspect each template's feature assumptions and license: https://vercel.com/templates/next.js/admin-dashboard .

### Best fit for visual research (not necessarily source code)
- **Refero** — shipped interface examples organized by screen, flow and UX pattern: https://refero.design/ .
- **Refero Styles** — AI-readable visual systems / DESIGN.md patterns; use as a reference to write our own design tokens, not as a substitute for the user flows: https://styles.refero.design/ .
- **Mobbin** — web and mobile product screen/flow inspiration: https://mobbin.com/ .
- **Google Stitch** — generate and refine the actual project screens, then keep verified artifacts and export/hand off the design: https://stitch.withgoogle.com/ .
- **Google Stitch SDK reference** — optional automation route if the team intentionally elects to use the SDK and manages its credentials: https://github.com/google-labs-code/stitch-sdk .

### Recommended combination
1. Use Refero/Mobbin to inspect interaction patterns.
2. Use Stitch to create and approve the actual app screens.
3. Use Tailwind Plus or shadcn blocks for solid operational layout ideas.
4. Use Motion Primitives/Magic UI for carefully selected transitions.
5. Implement the complete original design in Next.js using backend-driven data.

## 8. Stitch handoff requirements
- Actual Stitch project ID and screen IDs/URLs must be verified via MCP or the UI.
- Save screen purpose, primary states, responsive behavior and any unresolved differences in the repository.
- Before implementation, export/review the real screens and verify names/count. A project container with zero screens is not design completion.
- Do not claim Stitch code is production-ready; inspect semantics, accessibility, state, API integration and responsiveness.

## 9. Visual acceptance checks
Test 1440 px desktop, tablet and narrow mobile; keyboard-only navigation; reduced-motion enabled; loading/empty/error/permission-denied states; long IDs and large tables; 2,000+ visible row dataset through pagination (not DOM-rendering all rows); draft text overflow; and no frontend mock data replacing live API responses.
