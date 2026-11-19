---
name: va7-xhs-brand-deck
description: Build brand-facing HTML decks for technology Xiaohongshu creators using Pugongying audience data and va7-library content analysis.
---

# VA7 XHS Brand Deck

Create or refresh a single-file, brand-facing HTML presentation for a technology-focused Xiaohongshu creator. Use this skill when the request combines creator analytics, historical published-content analysis, and a polished partner-facing deck.

## Workflow

1. **Discovery and authorization**
   - Confirm the output path and whether this is a new deck or a revision. Preserve the newest existing HTML when revising.
   - For Pugongying, use the already-open, user-authenticated Chrome tab through Computer Use. Read visible page data only; do not change account settings, submit forms, or transmit data.
   - Locate the va7-library finished/published table using local files or the configured structured source. Prefer a structured export over a browser UI.
   - Record source dates, update timestamps, missing fields, and platform labels before interpreting results.

2. **Normalize and analyze**
   - Capture Pugongying fields when available: follower count, likes/collections, price display, median exposure/reading/engagement, peer-percentile comparisons, active-follower share, reading-follower share, interaction-follower share, order-follower share, gender, age, region, device, traffic source, and recent note metrics.
   - For each published record, retain title, date, summary/body, platform URL, and numeric metrics. Treat null or absent metrics as missing, never as zero.
   - Cluster by interpretable editorial themes using title, summary, body keywords, and hashtags. Start with a small set such as `Agent engineering / Harness`, `Enterprise AI transformation`, and `AI entrepreneurship / decision-making`, then adapt when the corpus clearly supports different categories.
   - For each cluster report count, measured count, sums where meaningful, median interaction (`likes + collections + comments + shares`), and representative titles. Do not compare cross-record interaction rates unless a common exposure denominator exists.

3. **Frame commercial value honestly**
   - Translate platform proxies into brand language: active behavior, action intent, decision-stage relevance, professional context, cross-region reach, and evidence-backed product education.
   - Use “高商业价值受众” or equivalent proxy language. Never state that followers are wealthy, high-net-worth, or financially successful unless the source directly proves it.
   - Separate verified facts, reasonable inferences, and recommendations. Put limitations in the deck, not only in the handoff message.

4. **Build the HTML deck**
   - Produce one editable HTML master. Use the fixed 1920x1080 stage, uniform viewport scaling, and `.active`/`.visible` slide switching described in the frontend-slides contract.
   - Include the full `viewport-base.css` contents in the document and preserve reduced-motion support.
   - Apply the Yibi guidebook system from [references/design-guidebook.md](references/design-guidebook.md): warm newsprint paper, ink typography, `#DC580E` orange accent, restrained gold, Chinese serif display type, Inter body type, JetBrains Mono metadata, editorial rules, and square/low-radius components.
   - Use a reading-first partner deck by default: concise evidence tables, clear source labels, one conclusion per slide, and no overflow or overlapping panels.
   - Include `data-editable` on user-authored text. Add an external toolbar with Edit, Save to browser, Save As HTML, and PDF controls. Save As HTML must serialize the current DOM with a fresh deck instance id and no runtime `contenteditable` or stage transform leakage.
   - Add keyboard navigation (arrows, space, PageUp/PageDown), touch swipe, wheel navigation, a progress indicator, reveal animations, and `prefers-reduced-motion` handling.

5. **Verify**
   - Run `node --check` on the inline script.
   - Check the slide count, editable-node count, fixed stage dimensions, exactly-one-visible-slide behavior, and absence of `display:none` slide switching.
   - Open the HTML locally in Chrome when possible. Inspect a desktop and phone-sized viewport for clipping, overflow, or overlap. If browser security blocks a local preview, report that limitation and still complete file-level checks.
   - Verify that the deck includes source dates and data limitations, and that no unsupported wealth claim appears.

## References

- Read [references/data-method.md](references/data-method.md) when collecting or aggregating creator data.
- Read [references/design-guidebook.md](references/design-guidebook.md) when styling or revising the deck.
- For fixed-stage/editable implementation details, use the installed `frontend-slides` skill's `viewport-base.css`, `html-template.md`, and `editable-html-contract.md` as authoritative references.
