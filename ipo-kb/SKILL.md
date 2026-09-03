---
name: ipo-kb
description: |
  IPO与挂牌审核问询案例库检索（本地私有知识库，2023-2026四个年度共1,628份）。
  当用户办理或研究北交所/科创板/创业板/沪深主板IPO、新三板挂牌项目，遇到具体审核
  法律问题——如股权代持还原、对赌清理、关联交易公允性、同业竞争、劳务派遣超标、
  未批先建、环保处罚、红筹拆除、实控人认定、一致行动、土地房产权属瑕疵等——需要
  查找同类案例的问询要点、回复论证口径、证据链构建思路与执业提示时使用。也可按
  板块、律所、代码、上市日期等维度筛选案例。不依赖 MCP 即可全量检索。
---

# IPO问询案例库检索

纯 Markdown 知识库，**本地克隆 + 按年度子目录**（与 GitHub 主仓 `lennonli/ipo-inquiry-kb`
同源，一司一文），网页版 `https://ai.licheng.uk/kb/`。
结构固定：frontmatter（公司/代码/板块/律所/tags）→ 一、概况 → 二、法律问题总览表 →
三、重点法律问题详述（每问含**问询要点**/**回复与核查要点**/**执业提示**）。

知识库根目录解析顺序：环境变量 `IPO_KB_ROOT` → `~/Documents/Macbook-pro项目/19-IPO问询案例知识库`
→ `~/ipo-inquiry-kb`。未有克隆时执行：`git clone https://github.com/lennonli/ipo-inquiry-kb.git ~/ipo-inquiry-kb`。

| kb | monorepo 子目录 | 规模 |
| --- | --- | --- |
| ipo（2026年度） | `2026` | 242份 |
| ipo2025 | `2025` | 430份 |
| ipo2024 | `2024` | 386份 |
| ipo2023 | `2023` | 570份 |

## 检索方法（首选本地脚本 kb_search.py，无需 MCP）

脚本位置：`~/.agents/skills/ipo-kb/kb_search.py`（下称 `$S`）。MCP `legal-knowledge`
可用时结果等价，但本地脚本无配额、离线可用，日常直接用它。

```bash
S=~/.agents/skills/ipo-kb/kb_search.py

# 0. 先拉新保持同源（四仓 git pull）
python3 $S update

# 1. 统一检索：元数据+正文加权排序，带命中摘录（对应 MCP search）
python3 $S search "股权代持 还原" --board 北交所 --limit 8

# 2. 按元数据筛案例（对应 MCP search_kb）
python3 $S meta --tag 同业竞争 --board 北交所 --year 2024
python3 $S meta --lawyer 国枫 --kb ipo2025

# 3. 正文全文检索，多关键词须同文命中（对应 MCP search_fulltext）
python3 $S full "未批先建 处罚" --kb ipo2023

# 4. 读命中案例原文（对应 MCP read_source；path 用检索结果给的 cases/xxx.md）
python3 $S read ipo2023 "cases/301373-凌玮科技.md"

# 5. 兜底：直接 grep（结构未变时等价；$KB 为知识库根目录）
grep -l "竞业禁止" $KB/20*/cases/*.md
```

检索策略建议：先用 `search` 试 2-4 个同义词关键词（如"股权代持 股权清晰 还原"），
命中过多时加 `--board`/`--year` 收窄；需要全库穷尽某一问题时用 `full`（注意多关键词
是 AND 关系，可拆开各查一次再取交集）。

## 输出要求

1. 命中案例逐个给出：**公司（代码·板块·上市日期）→ 相关问题的问询要点摘录 →
   回复论证思路（证据链构成）→ 执业提示**，注明来源 kb 与文件名；
2. 多案例命中时优先同板块、问题同类的，并对比论证口径差异；
3. 用户起草问询回复/核查计划时，把命中案例的"回复与核查要点"转成可迁移的论证框架
   与证据清单，并提示用户补充本项目事实。

## 纪律

- 案例内容基于公开披露文件提炼；**对外文件正式援引问询回复口径前，须回见微数据
  或交易所官网核对公告原文**，不得仅凭本库转述；
- "执业提示"系个人心得，仅供内部参考；
- 库中 lawyer 字段为空 = 原文未载明律所，不得推测填充；
- 新案例入库流程见仓库 README（模板在 templates/）；GitHub 更新后本地跑
  `python3 $S update` 即同步，无需重克隆。
