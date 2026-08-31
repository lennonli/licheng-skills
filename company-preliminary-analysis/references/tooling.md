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
| 司法风险 | `tyc risk ...`、企查查 `get_company_risk_scan`（分诊）→ 原子工具下钻明细 | 元典 `rh_enterpriseWritList` |
| 知识产权 | `tyc intellectual_property ...` | 企查查 qcc-ipr 系列 |
| IPO/挂牌审核进度 | 见微 `search_projects`（projectType=ipo，状态表勿与再融资混用） | — |
| 公告检索 | 见微 `search_announcements`（沪深北）/ `search_otc_announcements`（新三板；**转板公司两库都查**） | — |
| 官网 | WebFetch | 失败（SSL/TLS错误常见）→ web_reader；仍失败→WebSearch 找快照/报道 |
| 媒体/融资/舆情 | WebSearch | — |
| 法条原文 | `get_legal_article_detail`（企查查法规库） | 401/报错→元典 `yuandian_rh_ft_detail`（fgmc+ftnum）；北大法宝桥恢复后可用 `mcp__pkulaw__` 系列 |
| 类案/问询案例 | ipo-kb skill（本地问询案例库） | `mcp__qcc-legal-case__get_judicial_case_search`、见微 scope=IPO反馈回复 |

## 使用纪律

1. **每次引用写来源**：报告表格"注"行写"来源于×××平台（数据截止×年×月×日）"；
2. **穿透比例禁止自算**：第三方工具返回的穿透/受益比例逐字引用，禁止各层相乘重构；
3. **涉诉个人与主体都查**：董监高个人报告（企查查"董监高投资任职及风险报告"）信息量大于公司主体报告，实控人历史对外投资（已退出的同业公司）常在同业竞争排查中起决定作用；
4. **官方核验兜底**：写入对外文件的主体信息、法条、案号，最终以国家企业信用信息公示系统、国家法律法规数据库、裁判文书网核验为准；MCP 与官方不一致时以官方为准并说明差异；
5. **全面不可得即降级声明**：全部渠道不可用时，不编造——输出"【待核验】+原因+建议人工核验路径"，继续其余部分。

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
