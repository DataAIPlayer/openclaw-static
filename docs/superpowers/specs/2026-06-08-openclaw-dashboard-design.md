# Openclaw 用户使用数据看板 — 设计文档

- **日期**：2026-06-08
- **作者**：zbchu2 + Claude (brainstorm)
- **PRD 源**：[prd.md](../../../prd.md)

## 1. 目标

为 Openclaw 用户产出一个轻量化的使用数据看板，按**日 / 周 / 月**三个周期统计每个用户的：

- 对话次数
- 消耗的 token 数
- 调用的 skill 及对应次数

看板提供日/周/月切换，每个维度是一个按用量排序的列表，支持升序 / 降序。

### 第一版的非目标

- 不做后端 API、不做 daemon、不做日志变动实时触发。脚本**运行一次 = 聚合一次**，产出一份静态 JSON。
- 不做实时 docker 采集联动。dashboard 聚合脚本默认吃**本地 jsonl 文件 / 目录**，方便无 openclaw 环境开发。
- 不做计费扣费联动。
- 现有 `scripts/openclaw_stats.py`（云端 CLI 表格）保留不动，本设计另起聚合入口。

## 2. 核心发现：OpenClaw 的 skill 在日志里长什么样

PRD 的 Note 指出现有脚本统计出的 "skill" 其实是 `read`/`exec`/`web_search` 等**工具名**，不符合要求。根因（已在真实日志 `examples/example-log.jsonl` 验证）：

- OpenClaw 的 skill **不是**一个独立的 `Skill` 工具调用。skill 是
  `~/.openclaw/workspace/skills/<skill-name>/` 下的一个目录（`SKILL.md` + `scripts/...`）。
- 当 agent 用 `read` / `exec` / `edit` 等工具去**读 / 跑 / 改 `skills/<name>/` 路径下的文件**时，
  即代表用到了该 skill。
- 因此**真正的 skill 名藏在 toolCall 的路径参数里**，工具名本身（read/exec/edit）是噪音。

### skill 识别规则

扫每个 `message.role == "assistant"` 行的 `content[*]`，对 `type == "toolCall"` 的项，
把它的 `arguments` 序列化为字符串后，用正则匹配 workspace skill 目录：

```
\.openclaw/[^"']*?/skills/(?P<name>[A-Za-z0-9_-]+)/
```

- 锚定到 `.openclaw` workspace 路径，避免把无关的 `skills/` 字样误判。
- 命中 → 该 skill 计数 **+1**（按 toolCall 次数累加）。
- 同一 toolCall 命中多个不同 skill 名则各 +1；同名在一个 toolCall 内只算一次。
- 工具名本身（read/exec/edit/web_search…）**不再**当 skill 计数。

**验证**：对 `examples/example-log.jsonl`，该规则得到 `biz-meeting-summary = 13`，无误报。

## 3. 数据源与用户识别

### 数据源

真实部署：每个用户实例内
`~/.openclaw/agents/*/sessions/*.jsonl*`（含 `*.jsonl.reset.*`）。

每行是一条 JSON message，关注 `type == "message"` 的行，结构（摘自真实日志）：

```jsonc
{
  "type": "message",
  "id": "...",
  "timestamp": "2026-05-25T15:02:17.734Z",   // ISO 8601
  "message": {
    "role": "user" | "assistant" | "toolResult",
    "content": [
      { "type": "text", "text": "..." },
      { "type": "toolCall", "id": "...", "name": "read|exec|edit|...",
        "arguments": { "path": "~/.openclaw/workspace/skills/biz-meeting-summary/SKILL.md" } }
    ],
    "model": "gpt-5.4",          // 仅 assistant
    "usage": {                    // 仅 assistant
      "input": 17711, "output": 27, "cacheRead": 0, "cacheWrite": 0,
      "totalTokens": 17738,
      "cost": { "input": 0.315, "output": 0.003, "total": 0.318 }
    }
  }
}
```

### 用户识别

- 真实部署：用户来自容器名 `openclaw-{user}-gateway`，正则 `^openclaw-(?P<user>.+)-gateway$`
  （复用现有 `parser.user_from_container_name`）。
- 本地开发：单文件 / 单目录样例日志没有容器名。聚合脚本支持把一份文件或一个目录归到一个
  **指定 / 默认用户名**（如 `--user weiwu2`，缺省 `unknown`），使无 openclaw 环境也能跑通整条链路。

## 4. 架构

两段式，静态文件对接，**无后端、无数据库**：

```
真实部署机                              本仓库
~/.openclaw/agents/*/sessions/*.jsonl*
        │
        │  (1) Python 聚合脚本  scripts/openclaw_dashboard_stats.py
        ▼
   按 用户 × 周期(日/周/月) × 维度(对话/token/skill) 预聚合
        │
        ▼
   dashboard/public/stats.json     ← 一份静态聚合结果
        │
        │  (2) Vue3 + Vite 前端 fetch 这份 JSON
        ▼
   日/周/月 切换 + 每维度可升降序的排行榜看板
```

- 脚本运行一次产出一份 `stats.json`。开发期把样例日志的聚合结果写进
  `dashboard/public/stats.json`，前端即可跑通，不依赖真实 openclaw。
- **复用现有 `scripts/openclaw_stats_lib`** 的解析骨架（jsonl 逐行解析、token/cost 累加、
  容器→用户提取），新增/修正：① skill 识别改为从路径抽 `skills/<name>/`；② 输出改为
  按 日/周/月 桶预聚合的 dashboard JSON。

## 5. 时间桶与聚合

每行 `timestamp`（ISO 8601）归三个桶：

| 周期 | bucket key | label |
|---|---|---|
| day | `YYYY-MM-DD` | `YYYY-MM-DD` |
| week | 该周周一 `YYYY-MM-DD`（ISO 周一为周首） | `YYYY-Www` |
| month | `YYYY-MM` | `YYYY-MM` |

聚合口径：

| 维度 | 计算 |
|---|---|
| 对话次数 conversations | `message.role == "assistant"` 的行数 |
| token | sum `usage.input` / `usage.output` / `usage.totalTokens` |
| skill | 按 §2 规则，对命中 `skills/<name>/` 的 toolCall 计数（用该 toolCall 所在行的时间归桶） |

时间戳解析失败的行：token/skill 不归桶，但不致命（计入告警计数）。

## 6. 聚合输出 stats.json 结构

脚本预聚合好三个周期；前端只管选桶 + 排序（升降序在前端做，JSON 不预排死）。
每个时间桶同时提供两份视图：

- `users`：供「对话次数 / Token」维度排序（每行一个用户）。
- `skills_ranking`：供「Skill」维度排序（每行一个具体 skill，可展开看用户明细）。

```jsonc
{
  "generated_at": "2026-06-08T00:00:00Z",
  "periods": {
    "day": [
      {
        "bucket": "2026-05-25",
        "label": "2026-05-25",
        "users": [
          {
            "user": "weiwu2",
            "conversations": 33,
            "tokens": { "input": 1200000, "output": 50300, "total": 1250300 },
            "skills": [ { "name": "biz-meeting-summary", "count": 13 } ]
          }
        ],
        "skills_ranking": [
          {
            "name": "biz-meeting-summary",
            "count": 13,
            "by_user": [ { "user": "weiwu2", "count": 13 } ]
          }
        ]
      }
    ],
    "week":  [ /* 同结构 */ ],
    "month": [ /* 同结构 */ ]
  }
}
```

## 7. 前端交互（Vue 3 + Vite + 原生 CSS）

```
┌────────────────────────────────────────────────────┐
│  Openclaw 使用看板            generated_at: ...      │
│  周期:  [日] [周] [月]            桶: [2026-05-25 ▾]  │
│  维度:  [对话次数] [Token] [Skill]      排序: [↓ / ↑] │
├────────────────────────────────────────────────────┤
│  (对话次数 / Token 维度 → 每行一个用户)              │
│  #  用户        对话    Token       Top skill         │
│  1  weiwu2       33   1,250,300    biz-meeting…       │
│                                                      │
│  (Skill 维度 → 每行一个具体 skill，可展开)           │
│  #  Skill                   使用次数   ⌄              │
│  1  biz-meeting-summary        13      ▶             │
│       └ weiwu2   13            （展开后按次数排）     │
└────────────────────────────────────────────────────┘
```

- **周期切换**：日/周/月三个 tab。切换后「桶」下拉列出该周期所有时间桶，默认选最近一个。
- **维度切换**：对话次数 / Token / Skill 三选一。
  - 对话次数 / Token → 列表主体是**用户**，按选中维度数值排序。
  - Skill → 列表主体是**具体 skill**，按 skill 总使用次数排序；点开某行展示
    该 skill 被哪些用户使用、各用了多少次（按次数排）。
- **排序**：升 / 降序切换（PRD 要求倒序 + 顺序）。
- 纯前端计算排序，数据来自 `fetch('./stats.json')`。无路由、无状态库。
- 组件拆分：`App.vue` + `PeriodTabs` / `MetricTabs` / `RankingTable` 三个小组件。

## 8. 文件布局

```
scripts/
  openclaw_dashboard_stats.py        # 新增：聚合脚本入口（产出 dashboard JSON）
  openclaw_stats_lib/
    parser.py                        # 改：skill 识别从路径抽 skills/<name>/
    buckets.py                       # 新增：时间桶 + 按 用户×周期 聚合
    dashboard_render.py              # 新增：输出 stats.json 结构
  tests/
    test_skill_detection.py          # 新增：用 example-log.jsonl 断言 biz-meeting-summary=13
    test_buckets.py                  # 新增：日/周/月归桶
dashboard/                           # 新增：Vue3 + Vite 前端
  index.html
  vite.config.js
  package.json
  public/stats.json                  # 脚本产物（开发期先放样例聚合）
  src/
    App.vue
    components/{PeriodTabs,MetricTabs,RankingTable}.vue
    api.js                           # fetch stats.json
examples/example-log.jsonl           # 已有，作测试 fixture
docs/superpowers/specs/2026-06-08-openclaw-dashboard-design.md  # 本文档
```

## 9. 测试

- **脚本侧（pytest，TDD：先写测试）**：用真实 `examples/example-log.jsonl` 断言
  - skill 识别：`biz-meeting-summary` = 13，且 read/exec/edit **不**出现在 skill 统计里；
  - 对话次数：assistant 行数 = 33；
  - token 累加正确；
  - 日 / 周 / 月归桶正确（该样例同属一天 `2026-05-25` / 同一 ISO 周 / 同月 `2026-05`）。
- **前端侧（轻量）**：给 `stats.json` 喂样例，手动验证三周期切换、三维度排序、升降序展开；
  不引入 e2e 框架，保持轻量。

## 10. 健康规则

- JSON 解析失败 → 跳过该行，错误计数累加，最后告警汇总。
- assistant 行无 `usage` → token 不累加，但对话次数仍 +1。
- 时间戳解析失败 → 该行不归桶，计入告警，但不中断。
- 无 sessions / 空目录 → 用户保留，所有数为 0。
