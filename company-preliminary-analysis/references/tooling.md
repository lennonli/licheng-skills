# 信息采集工具链与降级路径

## 企查查资料包解析

有资料包目录时先跑固化脚本：
```bash
python3 ~/.agents/skills/company-preliminary-analysis/scripts/extract_package.py <目录> [-o 输出.md]
```
脚本覆盖：docx（段落目录+全部表格，合并单元格去重）、xlsx/xls（pandas 全 sheet）。输出一个文本文件，逐段读取。

**docx 提取已知坑**：企查查报告的表格单元格常含合并，`r.cells` 会重复返回合并单元格文本——脚本已做相邻去重；正文段落只读目录结构，实质数据在表格。

## 在线检索 MCP/CLI（无资料包或需补充时）

| 需求 | 首选 | 备选/降级 |
|---|---|---|
| 企业主体核验（多候选） | `get_company_by_query`（企查查）——**多候选必须交用户选定，禁止自动选第一名** | `yuandian_rh_company_info`（元典）、tyc L0 |
| 工商登记/股东/董监高 | `tyc company registration-info` | 元典 `rh_company_info`（一次给全，注意输出大，用 num=2） |
| 实际控制人 | `tyc company actual-controller` | 企查查 `get_actual_controller`（勿自行相乘穿透比例） |
| 股权穿透 | `tyc company equity-tree` | 企查查 `get_beneficial_owners` / `get_external_investments` |
| 对外投资/分支机构/变更 | `tyc company external-investments / branches / change-records` | 元典对应接口 |
| **延伸主体识别——存续分公司** | 天眼查 `get_branches`（含负责人、成立日期、登记状态；`total>fetched` 须翻页取全） | 企查查 `get_branches` → 元典 `rh_company_info` 分支机构段 |
| **延伸主体识别——各级控股子公司** | 天眼查 `get_controlled_companies`（向下穿透实际控制清单，含投资链，首选）+ `get_external_investments`（核一层持股比例与登记状态） | `get_equity_tree direction=down levels=4`；企查查 `get_external_investments`（仅一层直接比例，禁止相乘自算穿透） |
| **延伸主体识别——控股股东** | 天眼查 `get_shareholder_info`（工商登记口径；必要时 `source=2` 取最新公示对照）+ `get_actual_controller`（控制路径第一层即控股股东候选） | 企查查 `get_shareholder_info` + `get_actual_controller`；`tyc company actual-controller` |
| **延伸主体风险分诊（先分诊后下钻）** | 企查查 `get_company_related_risk_scan`（一次扫目标公司全部直接关联方：股东5%+/对外投资5%+/分公司/法定代表人/主要人员/实控人/受益人，7 维附命中主体）→ 命中者 `get_company_risk_scan` 逐家 35 维 → 原子工具取明细 | 天眼查 `get_risk_overview`（自身/周边/历史/预警四档计数）→ `get_risk_detail`（riskId+type）或专项工具（`get_administrative_penalty` / `get_default_event_info` / `get_judicial_assistance` 等） |
| 司法风险 | `tyc risk ...`、企查查 `get_company_risk_scan`（分诊）→ 原子工具下钻明细 | 元典 `rh_enterpriseWritList` |
| 知识产权 | `tyc intellectual_property ...` | 企查查 qcc-ipr 系列 |
| IPO/挂牌审核进度 | 见微 `search_projects`（projectType=ipo，状态表勿与再融资混用） | — |
| 公告检索 | 见微 `search_announcements`（沪深北）/ `search_otc_announcements`（新三板；**转板公司两库都查**） | — |
| 官网 | WebFetch | 失败（SSL/TLS错误常见）→ web_reader；仍失败→WebSearch 找快照/报道 |
| 媒体/融资/舆情 | WebSearch | — |
| 法条原文 | `get_legal_article_detail`（企查查法规库） | 401/报错/积分不足→元典 `yuandian_get_legal_article_detail`（regulation_name + article_number，曾用名 rh_ft_detail）；北大法宝桥恢复后可用 `mcp__pkulaw__` 系列 |
| 类案/问询案例 | ipo-kb skill（本地问询案例库） | `mcp__qcc-legal-case__get_judicial_case_search`、见微 scope=IPO反馈回复 |

## 使用纪律

1. **每次引用写来源**：报告表格"注"行写"来源于×××平台（数据截止×年×月×日）"；
2. **穿透比例禁止自算**：第三方工具返回的穿透/受益比例逐字引用，禁止各层相乘重构；
3. **涉诉个人与主体都查**：董监高个人报告（企查查"董监高投资任职及风险报告"）信息量大于公司主体报告，实控人历史对外投资（已退出的同业公司）常在同业竞争排查中起决定作用；
4. **官方核验兜底**：写入对外文件的主体信息、法条、案号，最终以国家企业信用信息公示系统、国家法律法规数据库、裁判文书网核验为准；MCP 与官方不一致时以官方为准并说明差异；
5. **全面不可得即降级声明**：全部渠道不可用时，不编造——输出"【待核验】+原因+建议人工核验路径"，继续其余部分；
6. **额度意识**：天眼查 CLI（tyc）与天眼查 MCP 共用额度，企查查按积分计费（积分不足报 `credit_balance_insufficient` 时立即切天眼查/元典，不要反复重试）；延伸主体多时先分诊再下钻，不要对每家都跑全部原子工具。

## 延伸主体批量核查流程

《尽调主体清单》的圈定与核查按以下四步固化执行，产出一份中间文件 + 一份核查结论表：

1. **圈定**：目标公司锚定后，依次调分支机构 → 向下穿透控制清单 → 一层对外投资（核比例/状态）→ 股东信息 + 实控人路径；按登记状态字段（存续/在业/开业 纳入；注销/吊销/撤销/迁出 排除并记入历史沿革）过滤；参股公司（≤50%且不控制）单独成列仅列示。
2. **落盘**：写 `/tmp/<项目>-尽调主体清单-<YYYYMMDD>.json`，每条记录字段：`name`（全称）、`type`（target/branch/subsidiary/controlling_shareholder/minority_stake）、`credit_code`、`path`（持股路径如"目标公司→A公司 100%→B公司 60%"，分公司填负责人）、`ratio`（累计/一层持股比例，逐字引用工具返回，不自算）、`reg_status`、`depth`（full/scan/list_only）、`source`（工具名+查询日期）。同一任务内后续步骤只读此文件。
3. **分诊与下钻**：按 SKILL.md 1.2 工作量分级执行；分诊结果（命中维度与条数）直接回填 JSON 的 `scan_hits` 字段；命中维度调原子工具取明细，明细记录涉及主体、案号/文号、金额、日期、来源。
4. **子代理并行**（延伸主体 ≥3 家）：按每代理 1—3 家切分，委派 `company-intel-researcher`，提示词须包含——主体全称与统一社会信用代码（防同名）、须查维度清单、输出格式（通用指令第十三章五段式）、"穿透比例逐字引用禁止自算""同名候选不得自动选定""查不到写【待核验】不得推测"三条纪律；主代理收回后逐条复核再写入报告，子代理结论不作最终法律判断。

**判定口径提醒**：`get_external_investments` 等返回的是一层直接比例，"子公司"判断用 `get_controlled_companies` 的控制口径或逐层比例叠加说明（叠加结果只能描述路径，不得写成精确穿透百分比，精确穿透值以 `get_actual_controller`/`get_beneficial_owners` 服务端聚合值为准）；50% 恰好持股的合营公司、未达50%但有协议控制的，单独写明判断依据。

## 报告生成后自检命令

```bash
soffice --headless --convert-to pdf <报告>.docx --outdir /tmp/check
python3 - <<'EOF'
import fitz, glob
pdf = glob.glob('/tmp/check/*.pdf')[0]
d = fitz.open(pdf)
print('页数:', len(d))
bad = []
for i, pg in enumerate(d):
    blocks = pg.get_text('blocks')
    mx = max((b[2] for b in blocks), default=0)
    if mx > 506: bad.append((i+1, round(mx)))
print('溢出页:', bad or '无')
EOF
```
溢出多因两端对齐行尾英文词或表格列宽超版心：先查溢出文本定位（正文空格混排→去空格；表格→缩列宽）。
