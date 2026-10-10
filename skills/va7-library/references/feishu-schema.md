# Feishu Base Schema Notes

Base:

- `base_token`: `<base_token，见 config.json>`
- URL: <<用户灵感库 URL，见 config.json>>

Tables:

- 原始素材库: `<materials 表 id，见 config.json>`
- 选题库: `<topics 表 id，见 config.json>`
- 成品内容: `<finished 表 id，见 config.json>`
- 内容生产排期: `<schedules 表 id，见 config.json>`
- 爆款选题库: `<viral_topics 表 id，见 config.json>`

Always call the script or `lark-cli base +field-list` before writing. The schema has drifted before.

## Important Live-Schema Facts

- `选题库` currently has no `状态` field. Do not require or write topic status unless the live schema shows it.
- `原始素材库.来源链接` and `爆款选题库.来源链接` are `text` fields with `style.type=url`. For `lark-cli base`, write a plain string URL.
- `认知密度` is a select field. Write only `高`, `中高`, `中`, or `低` when available. Do not write `高（理由...）`.
- `潜力等级` options differ between tables:
  - `选题库`: usually `🔥高潜力`, `⚠️中等潜力`, `💡素材向`.
  - `爆款选题库`: currently uses spaced variants such as `🔥 高潜力`, `⚠️ 中等`, `💡 素材向`.
- Link fields are written as record ID string arrays through `lark-cli base`, for example `["recxxx"]`.
- `成品内容.关联内容排期` links to 内容生产排期 (`<schedules 表 id，见 config.json>`).
- `内容生产排期.平台发布记录` links back to 成品内容 (`<finished 表 id，见 config.json>`).
- For published `成品内容`, treat `口播稿全文`, `选题类型`, and `关联内容排期` as required.
- For TikHub-synced `成品内容`, treat `封面图` and `IP属地` as platform-export recovery fields; do not generate them from scratch. TikHub note detail provides `ip_location` and cover media URLs.
- Current `成品内容.封面图` is an API-writable attachment field (`fldMQh72XC`). The old blocked attachment field is preserved as `封面图旧_MOBILE_ONLY` (`fldBgzwhIV`) for history and should not be used by scripts.
- `封面图URL` is the scripted fallback text field for TikHub cover media URLs. It records the deterministic source URL even when attachment upload needs debugging.

## Useful Commands

```bash
lark-cli doctor

lark-cli base +table-list \
  --base-token <base_token，见 config.json>

lark-cli base +field-list \
  --base-token <base_token，见 config.json> \
  --table-id <materials 表 id，见 config.json>

lark-cli base +field-list \
  --base-token <base_token，见 config.json> \
  --table-id <topics 表 id，见 config.json>

lark-cli base +field-list \
  --base-token <base_token，见 config.json> \
  --table-id <finished 表 id，见 config.json>

lark-cli base +field-list \
  --base-token <base_token，见 config.json> \
  --table-id <schedules 表 id，见 config.json>

lark-cli base +record-search \
  --base-token <base_token，见 config.json> \
  --table-id <topics 表 id，见 config.json> \
  --json '{"keyword":"Agent","search_fields":["选题标题","选题角度"],"select_fields":["选题标题","选题角度","潜力等级"],"limit":5}' \
  --format json
```

## Write Pattern

Use `scripts/inspiration_pipeline.py upload`. If hand-debugging with `lark-cli`, use this shape:

```bash
lark-cli base +record-batch-create \
  --base-token "$BASE_TOKEN" \
  --table-id "$TABLE_ID" \
  --json '{"fields":["选题标题","认知密度"],"rows":[["标题","高"]]}'
```

For row-specific patching:

```bash
lark-cli base +record-upsert \
  --base-token "$BASE_TOKEN" \
  --table-id "$TABLE_ID" \
  --record-id "$RECORD_ID" \
  --json '{"目标平台":["小红书"],"标签":["AI"],"来源素材":["recxxx"]}'
```

Do not use raw pseudo-functions such as `create_record()` in the skill body.
