# VA7 Cover Style Notes

This file covers visual execution. For semantic title/subtitle decisions, read `cover-copy-patterns.md`; for finished historical examples, use `cover-case-library/index.md`.

For crop construction and mandatory post-render comparison, read `composition-and-reference-qa.md`. “Preserve the source” means preserve real visual content and color, not preserve the source framing. Recompose all three ratios, including 16:9, with explicit crop boxes.

Use the approved 0713 Skills Sync v4 title/subtitle geometry as the default placement baseline: main title in the upper-left content zone, subtitle in the lower-left, subtitle slightly more inset than the title, and neither block touching the canvas edge or face.

## Current Default Title Treatment

Use the accepted 0612 Token消耗 title treatment as the default for VA7口播 covers:

- Main title preset in `../va7-cover-tools/scripts/render_cover_set.py`: `va7-main-title-clear`.
- Main fill: bright yellow around RGB `(255,245,0)`.
- Main title fake-bold: `weight=2`.
- Shadow: light soft shadow only; no visible stroke or same-color outline.
- Ratio defaults:
  - `16:9`: `font_size=248`, `line_gap=18`, `shadow={offset:[8,10], alpha:115, blur:1.4, weight:1}`
  - `4:3`: `font_size=224`, `line_gap=18`, `shadow={offset:[8,10], alpha:115, blur:1.4, weight:1}`
  - `3:4`: `font_size=186`, `line_gap=16`, `shadow={offset:[7,9], alpha:120, blur:1.4, weight:1}`

This replaces the earlier heavier title starting point. The old `weight=4` main title plus `shadow.weight=3` combination can make yellow glyphs look clumped, blurred, or like they have a yellow outline. Use heavier settings only after previewing and getting explicit approval.

## Lessons From The 0611 创业信仰 Cover

Content-type warning: this is the only audited `故事线` / 观点表达类 cover. Its conflict-led copy is a useful typography and crop reference, but it must not define the copy default for VA7's predominantly professional knowledge content.

Final accepted concept:

- Frame: a handsome outdoor close-up from the original MOV, selected by the user from alternatives.
- Copy:
  - Main title: `买英伟达 / 不如 / 投自己`
  - Subtitle: `早期创业者 / 别分心`
- Color: bright yellow main title, white subtitle.
- Text: very large, bold, no outline, soft shadow.
- Specs:
  - `16:9`: accepted earlier and left unchanged.
  - `4:3`: accepted earlier and left unchanged.
  - `3:4`: required repeated tuning; final issue was balancing big, readable text with not over-thickening the glyphs.

Important final parameters from that project:

- Source selected still: `frame_048p5s.jpg` from `48.5s`.
- Source frame size: `3840x2160`.
- Final vertical crop: `(980, 0, 2600, 2160)` into `1620x2160`.
- Main font: Hiragino Sans GB TTC, index `2`, size about `232px`.
- Subtitle font: same font, size about `184px`.
- Accepted final extra thickening for that specific cover: main title about `4px`, subtitle about `3px`.
- Previous too-heavy thickening: main title `7px`, subtitle `5px`; it looked blurry/clumped.
- Main fill: bright yellow around RGB `(255,245,0)`.
- Subtitle fill: white.
- Shadow: needed for readability, but should be soft. No visible stroke.

Treat these as historical context, not the current default. Start from `va7-main-title-clear` unless a reference cover or user feedback calls for heavier type.

## Inputs Needed

Minimum:

- Source video or frame.
- Topic/title direction.
- Output ratios.
- At least one previous reference cover, unless the style is already established in the same project.

Better:

- 3-5 reference covers from the same creator.
- `口播终稿` or final script text.
- User's preferred frame from a candidate sheet.
- User's preferred copy variant.

## Output Location

Final user-facing cover files belong in the original source folder, inside a `cover/` subfolder. Workspace `outputs/` is acceptable for temporary previews, but not as the only final location.

Example final folder:

```text
~/Desktop/0611 创业信仰/cover/
```

Keep all final ratios and the final preview board there.

## What Must Be Human-Confirmed

Human review is not optional for VA7 covers.

Ask for confirmation at these points:

1. Frame candidate selection.
2. Copy/title selection.
3. Draft layout, especially vertical crop and text size.
4. Final acceptance if major revisions were made.

Do not assume the agent can pick the final screenshot alone. It can narrow the set, but the user's taste decides.

## Common Pitfalls

### Skipping Alternatives

Mistake: generate a final image directly and present it as done.

Better: show screenshot alternatives and copy alternatives first. Only build polished covers after user selection.

### HDR/SDR Washout

Mistake: extract a raw frame from iPhone HDR footage and use it directly. The image can become pale, gray, or over-bright.

Better: test raw vs SDR conversion, inspect visually, and use the conversion that preserves the original appearance. In the 0611 project, a `colorspace`-style conversion looked closest.

### Too Many Text Blocks

Mistake: add extra tags or topic labels such as `早期创业者` as a third small block without approval.

Better: keep the expected structure: one main title and one subtitle unless the user explicitly asks for more.

### Wrong Line Breaks

Mistake: ignore an explicit line break request and compress into fewer lines.

Better: preserve requested breaks exactly. For example, if the user says:

```text
买英伟达
不如
投自己
```

use three lines.

### Vertical Crop Too Loose

Mistake: show the ear when reference vertical covers hide it, leave too much air above the hair, or make the face too small.

Better: for `3:4`, crop tighter. Push the face right, keep the hair top near the upper edge, and remove the ear if requested.

### 4:3 Face Placement

Mistake: center the person or leave the face floating in the middle.

Better: for VA7口播 covers, the person often belongs clearly in the right half, leaving the left side for big title text.

### Text Too Small

Mistake: make the vertical cover text proportional to horizontal covers. It will look timid and unreadable as a thumbnail.

Better: make vertical text dramatically larger. Compare against references, not against the agent's first draft.

### Font Weight vs Font Size

Mistake: solve thin text by only increasing size or by over-applying fake bold.

Better: use a genuinely bold font face first. For yellow main titles, start from `va7-main-title-clear` (`weight=2`) and preview before increasing thickness. Too much offset makes glyphs blur together.

### Heavy Shadow Or Fake Stroke

Mistake: use hard, black, offset shadows or visible outlines. The result feels stiff and unlike previous VA7 covers.

Better: no stroke. Use a soft, slightly offset shadow only for legibility. If text still lacks contrast, tune shadow opacity/blur before adding outline.

## Practical Design Heuristics

Frame selection:

- Prefer open eyes, confident expression, sharp face, flattering angle.
- Avoid mouth shapes that look awkward when frozen.
- Avoid frames where glasses glare hides the eyes unless the expression is otherwise strong.
- Prefer frames with usable negative space for text.

Text placement:

- Main title should read first at thumbnail size.
- Subtitle is still large and bold, not a tiny footnote.
- Keep text away from eyes, glasses, nose, mouth, and face edge.
- Do not use decorative boxes unless reference covers use them.

Color:

- Yellow/orange main title and white subtitle are strong defaults.
- Test on the actual frame; bright glass/building backgrounds may need more shadow.
- Avoid adding random purple/orange blocks unless they are part of the approved reference style.

Versioning:

- Save iterations with clear version suffixes.
- When user accepts most of a version, branch from that version.
- Keep a preview board for comparing the three ratios.

## Suggested Output Checklist

Before final response:

- Show the final image or preview board inline.
- Link final files from the source folder's `cover/` folder.
- State what changed in the latest revision.
- Mention any ratios left unchanged.
- Avoid over-explaining unless the user asked for a process recap.
