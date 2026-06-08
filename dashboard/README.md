# Openclaw 使用看板（前端）

读取 `public/stats.json` 渲染的轻量看板。stats.json 由
`scripts/openclaw_dashboard_stats.py` 生成。

## 开发

```bash
# 1) 生成/更新数据（在仓库根执行）
python3 scripts/openclaw_dashboard_stats.py examples/example-log.jsonl \
    --user weiwu2 --out dashboard/public/stats.json

# 2) 启动（在 dashboard/ 目录执行）
npm install
npm run dev
```

## 构建

```bash
npm run build   # 产物在 dist/
npm run preview # 本地预览 dist/
```

## 交互

- 周期：日 / 周 / 月切换 + 时间桶下拉（默认选最近一个桶）
- 维度：对话次数 / Token（按用户排）、Skill（按 skill 排，点击行展开看用户明细）
- 排序：升 / 降序切换
