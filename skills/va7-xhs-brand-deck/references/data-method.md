# Data Method

## Pugongying snapshot

Capture the visible account identity, update date, follower count, likes/collections, current displayed prices, audience indicators, peer comparisons, traffic sources, and recent-note metrics. Preserve the platform's exact wording for labels such as “下单粉丝占比” and “优于同类博主”. A platform metric is evidence of a platform-defined behavior, not proof of income or assets.

Recommended partner-facing translations:

| Source signal | Permitted interpretation |
|---|---|
| Active-follower share | Audience is not passive; useful for education and consideration campaigns |
| Order-follower share | Platform-reported action-intent proxy |
| Apple/device mix | Platform-labeled consumption-power proxy; do not call it wealth proof |
| Age/region/city | Demographic and scenario context |
| Peer percentile | Relative platform performance at the displayed comparison scope |
| Search/video recommendation share | Discoverability and content-format implication |

## Finished-content table

For every record retain title, date, intro/body, tags, URL, and any numeric fields. Normalize numeric strings to numbers only when the unit is clear. Keep `null` for missing values. Use:

`interaction = likes + collections + comments + shares`

Use medians for skewed content-performance summaries. If exposure is absent or inconsistent, report interaction volume but do not label it an engagement rate.

## Clustering

Use explainable, manually auditable thematic clusters. A record should have one primary cluster unless the user explicitly requests multi-label classification. Show the rule in the appendix, for example: “按标题、摘要、正文关键词与话题标签人工校准”. Include measured count and missing-data notes per cluster.
