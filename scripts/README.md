# scripts/

## openclaw_stats.py — OpenClaw 用户使用统计

在云服务器上运行，扫描所有 `openclaw-*-gateway` 容器内的会话日志
（`/home/node/.openclaw/agents/main/sessions/*.jsonl`），按用户聚合
token 用量、请求次数和 skill 调用，输出表格或 JSON。

### 用法

```bash
# 默认：所有容器，表格输出
python3 scripts/openclaw_stats.py

# JSON 输出
python3 scripts/openclaw_stats.py --format json

# 只统计指定用户
python3 scripts/openclaw_stats.py --user weiwu2 --user bnzhu

# 调整表格里 skill Top N
python3 scripts/openclaw_stats.py --top-skills 10
```

### 依赖

- Python 3.11+（标准库即可，无需 pip 安装）
- 宿主机能执行 `docker ps` 和 `docker exec`

### 设计文档

[docs/superpowers/specs/2026-05-25-openclaw-usage-stats-design.md](../docs/superpowers/specs/2026-05-25-openclaw-usage-stats-design.md)

### 测试

```bash
pytest scripts/tests/ -v
```

## openclaw_dashboard_stats.py — 看板数据聚合

把 OpenClaw 会话 jsonl 按 用户×(日/周/月)×(对话/token/skill) 聚合成
前端看板用的 stats.json。两种数据源:

- **local**(默认): 读本地 jsonl 文件/目录,**无需 openclaw 运行环境**,适合开发。
- **docker**: 在服务器上扫所有 `openclaw-{user}-gateway` 容器,`docker exec` 读容器内
  `/home/node/.openclaw/agents/main/sessions/*.jsonl*`,按容器名提取用户。与
  `openclaw_stats.py` 同样的采集方式。

skill 识别口径：skill = `~/.openclaw/.../skills/<name>/` 目录；统计 agent 用
read/exec/edit 等工具操作该目录的 toolCall 次数（不是把 read/exec 当 skill）。

### 用法

**本地 (local)**

```bash
# 单文件，指定用户，写到前端 public 目录
python3 scripts/openclaw_dashboard_stats.py examples/example-log.jsonl \
    --user weiwu2 --out dashboard/public/stats.json

# 多用户(路径与 --user 一一对应)
python3 scripts/openclaw_dashboard_stats.py \
    /data/weiwu2/sessions /data/bnzhu/sessions \
    --user weiwu2 --user bnzhu --out dashboard/public/stats.json
```

**docker (在服务器上运行)**

```bash
# 扫所有 openclaw-*-gateway 容器,聚合所有用户
python3 scripts/openclaw_dashboard_stats.py --source docker \
    --out dashboard/public/stats.json

# 只采指定用户
python3 scripts/openclaw_dashboard_stats.py --source docker \
    --user weiwu2 --user bnzhu --out dashboard/public/stats.json
```

依赖:宿主机能执行 `docker ps` / `docker exec`(同 `openclaw_stats.py`)。

触发:第一版手动 / cron 定时跑(如每 5 分钟)重新生成 stats.json,前端刷新即可;
未做日志变动实时 watch。cron 例:

```cron
*/5 * * * * cd /path/to/openclaw-static && python3 scripts/openclaw_dashboard_stats.py --source docker --out dashboard/public/stats.json
```

### 前端

见 [dashboard/README.md](../dashboard/README.md)。

### 设计 / 计划

- [docs/superpowers/specs/2026-06-08-openclaw-dashboard-design.md](../docs/superpowers/specs/2026-06-08-openclaw-dashboard-design.md)
- [docs/superpowers/plans/2026-06-08-openclaw-dashboard.md](../docs/superpowers/plans/2026-06-08-openclaw-dashboard.md)
