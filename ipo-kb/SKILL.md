---
name: ipo-kb
version: 2.0.0
display_name: 证券业务法律问询案例和证券法规检索
display_name_en: Securities Inquiry Cases & Regulations Search
description_zh: 检索证券业务审核问询案例与证券法规知识库（14 库：IPO 问询四年度 1,636 家、再融资四年度 875 家、并购重组四年度 74 家、投行法规库、补充法律意见书库 824 份）。MCP 语义检索优先，本地克隆直查兜底；支持按公司、代码、板块、律所、轮次等筛选，可读案例与法规原文，用于问询回复口径对比、同类案例检索与监管关注要点参考。
description_en: Search securities-review inquiry cases and regulations across 14 knowledge bases (IPO inquiry 2023-2026, 1,636 companies; refinancing 875; M&A 74; investment-banking regulations; 824 supplementary legal opinions). MCP semantic search first, local clone as fallback; filter by company, ticker, board, law firm or round; read full case and regulation texts.
description: |
  证券业务审核问询案例与证券法规检索（本地私有知识库，14 个库）。
  当用户办理或研究 IPO/新三板挂牌、再融资（定增/可转债/配股）、并购重组项目，
  遇到具体审核法律问题——如股权代持还原、对赌清理、关联交易公允性、同业竞争、
  募集资金用途与补流、财务性投资、业绩承诺与补偿、商誉、重组上市认定等——需要
  查找同类案例的问询要点、回复论证口径、证据链构建思路与执业提示，或检索投行
  法规原文、补充法律意见书先例时使用。14 库已全部接入 MCP（legal-knowledge 服务），
  也可本地克隆直查，网页版全库在线阅读。
---

# 证券业务问询案例和证券法规检索

14个知识库已全部接入 MCP（`legal-knowledge` 服务，工具 `search` / `read_source` / `search_kb` / `search_fulltext`，参数 `kb` 指定库），同时托管于单体仓库 `github.com/lennonli/ipo-inquiry-kb` 与网站 ai.licheng.uk。

## 一、知识库总览（kb 参数取值）

### 审核问询案例库（一司一文：问询要点—回复与核查要点—核查意见—执业提示）

| kb 参数 | 库 | 家数/规模 | 网页 |
| --- | --- | --- | --- |
| `ipo` | IPO/挂牌问询 2026 年度 | 250+ 家 | /kb/ |
| `ipo2025` | IPO/挂牌问询 2025 年度 | 430 家 | /kb2025/ |
| `ipo2024` | IPO/挂牌问询 2024 年度 | 386 家 | /kb2024/ |
| `ipo2023` | IPO/挂牌问询 2023 年度 | 570 家 | /kb2023/ |
| `refi2026` | 再融资问询 2026 年度（定增/可转债） | 192 家 | /refi2026/ |
| `refi2025` | 再融资问询 2025 年度 | 186 家 | /refi2025/ |
| `refi2024` | 再融资问询 2024 年度 | 107 家 | /refi2024/ |
| `refi2023` | 再融资问询 2023 年度 | 390 家 | /refi2023/ |
| `ma2026` | 并购重组问询 2026 年度 | 17 家 | /ma2026/ |
| `ma2025` | 并购重组问询 2025 年度 | 39 家 | /ma2025/ |
| `ma2024` | 并购重组问询 2024 年度 | 11 家 | /ma2024/ |
| `ma2023` | 并购重组问询 2023 年度 | 7 家 | /ma2023/ |

### 法规与底稿库

| kb 参数 | 库 | 规模 |
| --- | --- | --- |
| `rules` | 投行法规知识库（发行审核/再融资/并购重组/公司债券等监管规则原文） | 按目录分类 |
| `supplement` | 补充法律意见书库（2001-2024） | 824 份 |

家数为编制时点数，各案例库按周自动增量入库，持续增长。

## 二、检索方法（按优先级）

1. **MCP 语义检索（首选）**：`search(kb=<库>, query=<自然语言问题>)`，命中后用 `read_source(kb, path)` 核验原文。日常问题直接用语义检索；需按公司/代码找文件用 `search_kb`；关键词兜底用 `search_fulltext`。path 口径：案例库为 `cases/xxx.md`，rules/supplement 为含年份或子目录的相对路径。
2. **本地克隆直查**：仓库 `~/Documents/Macbook-pro项目/19-IPO问询案例知识库`（monorepo，各库子目录 `{库}/cases/{代码}-{简称}.md` + `{库}/scripts/index.json` + `{库}/reports/{年度}年度总结.md`）。
   - **先筛后查**：读 index.json。IPO 库字段 file/company/code/board/listing_date/lawyer/tags；再融资库另有 refi_type(定向增发|可转债|配股)/pay_method/deal_amount/status(注册生效|提交注册|终止撤回|审核中)/questions；MA 库有 deal_type/pay_method/registered_date。
   - **全文兜底**：`grep -l "关键词" {库}/cases/*.md`。
   - **年度总结**：宏观问题先看 `{库}/reports/{年度}年度总结.md`（高频问题分布、监管趋势、代表性案例）。
3. **网页**：ai.licheng.uk 对应栏目（支持站内搜索与跨年度对比）。
4. **随库脚本**：本目录附带 `kb_search.py`（首次运行自动克隆知识库，支持四年度 IPO 库的统一检索/元数据筛选/原文阅读，`python3 kb_search.py update` 同步）；再融资/并购/法规/补充意见书库以 MCP 与本地直查为准。

## 三、跨库检索建议

- 同一法律问题跨年度对比（如财务性投资扣除口径、破净资产定增、827 新规前后）：分别查各年度再融资库的同主题案例，输出对比表；
- 再融资高频问题：募集资金用途与补流比例（18 号文）、财务性投资与类金融、前次募集资金使用、产业政策（立项/环评/能评/用地）、发行对象与定价（控股股东认购/借款认购）、限售安排；
- 并购重组高频问题：交易必要性、评估定价、业绩承诺与补偿、商誉、重组上市认定、支付方式；
- 法规原文：先 `rules` 库语义检索，再回交易所/证监会官网核对效力状态。

## 四、输出要求

- 引用案例注明：公司简称、代码、板块、轮次、问题编号（再融资库加注 refi_type 与审核状态）；
- 对比类问题输出表格（各案问询要点 vs 回复口径 vs 证据链差异）；
- 提醒用户：内容基于公开披露文件提炼，正式援引前回交易所/股转官网核对原文。

## 五、维护

- **周度增量（已自动化，automation-16dae601 每周五20:00）**：IPO/挂牌跑 `python3 2026/scripts/ingest_new.py`（底稿来自周一问询回溯任务）；refi 经见微"再融资反馈回复"找新增入库（每周≤5家，index 追加式更新）；ma 从 ma-legal-digest 周报提炼入库（每周≤3家，跑 ma{年}/scripts/build-index.py）→ 19 号克隆 commit/push（须 `-c http.version=HTTP/1.1`）→ `~/kb-data/ipo-inquiry-kb` git pull → kickstart v02 服务。rules 由每周五 17:00 法规同步任务维护，勿重复。
- **手动新增单篇**：复制模板填好放入 `{库}/cases/`，运行 `python3 {库}/scripts/build-index.py`（再融资用 `tools/build_refi_index_year.py {年}`），commit 后 push，网站每日自动同步。
- **MCP**：legal-knowledge-mcp 直读本地克隆 `~/kb-data/ipo-inquiry-kb`，推送后需该克隆 `git pull`（或等 10 分钟索引 TTL 自动刷新），新增库需在 `server.mjs` 的 KBS 注册并 kickstart，且运行版改动必须推回 `lennonli/legal-knowledge-mcp` 仓库。
