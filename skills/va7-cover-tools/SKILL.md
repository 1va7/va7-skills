---
name: va7-cover-tools
description: va7-video-cover-maker 的脚本包（出图、QA、闸门、裁切建议、抽帧、花字、素材下载）。不单独调用；按 va7-video-cover-maker 的流程使用，开工先跑 scripts/cover_assets.py ensure。
---

# va7-cover-tools

封面技能拆成三部分，因为 Antry 单个技能上架有大小上限（约 93KB），字体和样本图又有 25MB：

- `va7-video-cover-maker`：流程、规则、样本索引（读这个）。
- `va7-cover-tools`（本包）：全部脚本。
- 素材缓存：`scripts/cover_assets.py ensure` 装 Pillow，下载字体和历史封面样本到 `$VA7_COVER_ASSETS`（缺省 `~/.cache/va7-cover-assets`），按 sha256 校验，已就绪时不重复下载。

脚本：`cover_gate.py`（预检/交付闸门）、`render_cover_set.py`（出图）、`qa_cover_set.py`（QA）、`suggest_crop.py`（裁切建议）、`extract_candidates.py` / `extract_avfoundation_frame.swift`（抽帧）、`build_reference_qa_board.py`（参照拼图）、`huazi.py`（开头花字）、`cover_assets.py`（素材）。
