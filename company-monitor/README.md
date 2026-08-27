# company-monitor — 公司舆情与法律风险监控系统（Agent 可直接安装）

面向法律场景的**企业持续尽调/风险监控 Agent 系统**：对监控清单内的公司，每日自动采集司法监管动态（诉讼、行政处罚、被执行/失信、仲裁线索）、交易所/挂牌公告与 IPO 审核进度、财经媒体质疑、微博/微信公众号/百度/小红书社媒舆情，经 SQLite 指纹去重后产出**红/橙/黄三级增量日报**（PDF → Google Drive → 邮件）。

> 定性：所内**线索发现工具**，不作法律结论。商业数据源与社媒信息日报中一律标【待核验】，对外出具前须回官方来源二次核验。

## 目录结构

```
company-monitor/
├── SKILL.md          # 规则中枢：十步日流程/红橙黄分级/合规红线/降级链（agent 每日按此执行）
├── README.md         # 本文件：安装与初始化指南
├── install.sh        # 一键初始化目录与配置
├── requirements.txt
├── config/
│   ├── targets.example.yaml   # 监控主体清单模板 → 复制为 targets.yaml 填写
│   ├── system.example.json    # Drive 路径/默认收件人模板 → 复制为 system.json
│   └── mail.example.json      # 报告收件邮箱模板 → 复制为 mail.json
├── tools/            # 全部可执行脚本（去重引擎/四通道社媒/官方公告降级/PDF/Drive/邮件）
└── docs/TUTORIAL.md  # 从零搭建完整教程（含 14 条踩坑表，理解原理必读）
```

## 安装（AI Agent 按序执行）

### 第 0 步：与用户确认三个决策点（阻塞项）

1. **监控主体清单**：公司全称、是否挂牌/上市、是否有 IPO 在审进程；
2. **小红书口径**：OpenCLI 半自动（需用户装 Chrome 扩展并登录小红书，见 docs/TUTORIAL.md §8.3）或周度人工抽查；
3. **通知管线**：PDF → Google Drive → 邮件 是否可用（需 Google Drive 桌面版登录、agently-cli 或等效邮件 CLI 已授权）。

### 第 1 步：环境依赖

```bash
python3 -m pip install -r requirements.txt        # playwright + pyyaml
# 系统 Chrome 已装即可(fetch_social/fetch_official/md2pdf 走 channel="chrome")
which pandoc rsync || echo "需要安装 pandoc 与 rsync(brew install pandoc rsync)"
```

可选增强（不装不影响主流程，对应渠道自动容错跳过）：

| 能力 | 依赖 | 说明 |
|---|---|---|
| 小红书 | opencli（`pipx install agent-reach` 后按 docs/TUTORIAL.md §8.3 装 Chrome 扩展＋登录） | 桥接浏览器登录会话，Cookie 不落盘 |
| 微信公众号 | 专用 venv（安装命令见 docs/TUTORIAL.md §8.3 末尾） | miku_ai 搜索＋全文按需读取 |

### 第 2 步：初始化

```bash
bash install.sh                     # 建 state/outbox/summaries/raw 目录 + 拷贝配置模板
```

然后填写三个配置（**含隐私，不要提交到任何仓库**）：

1. `config/targets.yaml`：按模板录入监控主体（先用企业工商 MCP 逐字段核验后录入）；
2. `config/system.json`：Google Drive 同步根目录、默认收件人；
3. `config/mail.json`：报告收件邮箱；邮件发送通道以 agently-cli 为例，需完成一次 `agently-cli auth login` 用户授权。

### 第 3 步：Baseline 首跑（由 Agent 按 SKILL.md §三执行）

核心顺序：35 维风险扫描 → 命中维度下钻 → 消极舆情 → 公告/审核状态 → IPO 媒体专项 WebSearch → `tools/fetch_social.py` → 组装 `outbox/today_items.json` → `tools/dedup.py feed` 入库 → 写基线报告 → `md2pdf.py` → `sync_to_drive.py` → `send_daily_email.py`。**Baseline 日记录全量存量不分级推送，次日起只报增量。**

### 第 4 步：注册每日定时任务（只建一个）

任务提示词模板（按实际路径/主体替换占位符）：

```text
阅读 <skill目录>/SKILL.md 并严格按"每日执行流程"执行，主体清单读 config/targets.yaml。
步骤：init-check 确认模式 → 风险扫描比对 last_scan.json 仅下钻增量维度 → 消极舆情 →
IPO媒体专项WebSearch → 公告/审核状态(见微≤4次,超限降级 fetch_official.py) →
fetch_social.py 四通道 → dedup.py feed 增量 → 红橙黄分级出日报 → md2pdf → sync_to_drive →
send_daily_email。约束：不得手改 state/；渠道失败如实记录；商业数据标【待核验】；
不得编造；汇报≤300字。
```

## 关键设计铁律（详见 docs/TUTORIAL.md）

1. MCP 只拿数据，SKILL.md 定规则，Cron 只触发；一个任务遍历清单，加公司只改 targets.yaml；
2. Baseline 全量一次，此后只报增量（没有增量，第三天日报就废了）；
3. 判断交给 LLM（相关性/分级），记忆交给 SQLite（指纹 = sha1(公司|类型|案号/标题哈希)）；
4. 仲裁无公开统一库：报告只能写"未检索到公开仲裁信息"；
5. 渠道失败必须如实记录，禁止以"未发现风险"掩盖"未覆盖渠道"。

## 合规红线

商业数据与社媒内容仅作线索且须标【待核验】；评论区只统计数量与倾向、不落个人信息；不采集自然人个人信息；带登录态抓取须用户知情同意并自担账号风控；产出定性为线索，不作法律结论，对外出具须回官方来源二次核验。
