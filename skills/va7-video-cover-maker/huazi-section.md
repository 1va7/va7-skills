## 开头花字（放在封面流程「文案确认」之后）

花字是视频开头前 3 秒叠在画面上的字，不是封面。版式以 VA7 的样本图为准（横屏 1920×1080）：
- 左上：白字两行，情绪或问题句（样本：「FDE 太卷 / 被压价」）。
- 右下：黄字两行，关键词，右对齐（样本：「城市/赛道 / 主动选择」）。

输入：口播稿第一句；已确认的封面主副标题。

规则（由 ../va7-cover-tools/scripts/huazi.py check 强制）：
- 候选至少 2 套，每套 tl（左上）和 br（右下）各正好 2 行，附一句理由。
- 每行不超过 7 个字（样本最长 6 个）。
- 不得与封面标题任何一行完全相同。
- 含数字必须给 number_source。
- 含义对应开头第一句；脚本只给提示，人确认。

流程：
1. 写 huazi_candidates.json（见 huazi_candidates.sample.json）。
2. `python3 ../va7-cover-tools/scripts/huazi.py check --candidates huazi_candidates.json`，通过才继续；不通过退出码 2。
3. 人选定第几套。
4. 二选一：
   - 无人值守：`python3 ../va7-cover-tools/scripts/huazi.py render --choose N --out huazi.png`，得到 1920×1080 透明底 PNG，拖进剪映即可。没有通过的预检结果，或预检结果是旧格式，render 拒绝运行。
   - 有人在剪映里做：只交文字，不生成 PNG。

标准是样本：字号约占画面高度 13%、行距约 15.7%、白字纯白、黄字取样本色 (250,220,75)、字体用 Noto Sans SC Bold（2026-11-16 王诗梦看并排对比图后选定，以此为标准；Medium 偏细、Black 偏重，不用）。这些数是从样本图量出来的，不需要你们报数字，只需要看并排对比图说「行 / 不行」。
