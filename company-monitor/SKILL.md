---
name: company-monitor
description: Use this skill when the user asks to set up or run a company public-opinion and legal-risk monitoring system, monitor target companies for litigation, arbitration, administrative penalties, enforcement/dishonesty listings, IPO/exchange inquiry progress, or negative media and social-media sentiment (Weibo, WeChat official accounts, Baidu, Xiaohongshu), generate daily incremental risk digest reports with red/orange/yellow grading, deduplicate findings against a baseline SQLite store, or register a daily cron for company risk monitoring. Triggers include "舆情监控", "公司风险监控", "舆情日报", "负面消息监控", "监控这家公司", " Litigation monitoring", "public opinion monitoring", "daily risk digest".
---
# 公司舆情与法律风险监控 Skill（company-monitor）

定位：**所内自用的线索发现工具，不作法律结论、不作对外交付文件**。产出仅供李成律师内部参考。
监控对象：`config/targets.yaml` 中列明的全部主体（挂牌/上市主体及 IPO 在审主体，首次部署时逐一核验登记信息并录入）。

## 一、合规红线（每次运行均适用）

1. 商业数据源（企查查 MCP）与社媒信息仅作**线索**，进入日报一律标"【待核验】"；如需对外出具，必须回到 A 档官方来源（裁判文书网、执行信息公开网、信用中国、国家企业信用信息公示系统、股转/北交所官网）二次核验，本机可用 court-shixin-query skill 存证。
2. 评论区/社媒内容**只记录数量、平台与倾向概述**，不落原文与账号个人信息；不采集自然人个人信息。
3. 仲裁无全国统一公开库：报告只能写"未检索到公开仲裁信息"，禁止写"不存在仲裁案件"。仲裁间接线索来源：挂牌公司公告、仲裁保全/执行/撤裁案件、新闻报道。
4. 不得编造：把握不准处标【待核验】；渠道抓取失败须在日报"渠道覆盖"节如实记录，禁止以"未发现风险"掩盖"未覆盖渠道"。
5. 本目录外不写文件；不得创建/修改/删除定时任务；除 config/mail.json 指定邮箱外不得对外发送。

## 二、数据源分档

- **A 档（官方，结论依据）**：股转系统官网（neeq.com.cn）信息披露、北交所官网（bse.cn）发行上市审核公示、执行信息公开网、信用中国。工具：`tools/fetch_official.py`（东财新三板公告接口为主通道 + 股转官网 playwright 降级 + 北交所审核状态）。
- **B 档（商业数据，线索发现主力）**：企查查 MCP——`get_company_risk_scan`（35维分诊）→ 命中维度下钻原子工具（诉讼 `get_case_filing_info`/`get_hearing_notice`/`get_judicial_documents`；处罚 `get_administrative_penalty`；执行 `get_judgment_debtor_info`/`get_dishonest_info`/`get_terminated_cases`；冻结出质 `get_equity_freeze`/`get_equity_pledge_info`）；舆情 `get_news_sentiment`（sentiment=消极）。
- **B2 档（见微 MCP，配额敏感）**：新三板公告 `search_otc_announcements`（label=代码）；北交所项目状态 `search_projects`。
- **C 档（社媒，苗头感知）**：微博（playwright→m.weibo.cn API）；**微信公众号（miku_ai 搜索，2026-08-28 替换搜狗通道，返回标题/摘要/公众号名/日期，每家词组：主体名＋投诉＋IPO）**；百度资讯（playwright）。统一走 `tools/fetch_social.py`。
- **微信全文按需读取**（日报 agent 对疑似负面命中深挖时用）：`~/.agent-reach/venvs/wechat-md/bin/python ~/.agent-reach/tools/wechat-article-for-ai/main.py "<文章URL>" -o /tmp/wxmd --no-images`，产出 YAML frontmatter＋正文 Markdown。注意结果 URL 带时效签名，**现搜现读**；去重指纹用标题哈希（fetch_social 已内置 source_id=标题哈希）。
- **小红书**：`tools/fetch_social.py --platform xhs` 或全量运行时自动包含——走 opencli CLI（pipx 工具，桥接本机 Chrome 已登录会话，Cookie 不落盘）。依赖链与容错口径：需 Mac 开机＋Chrome 运行＋OpenCLI 扩展连接＋小红书登录态四者齐备；任一缺失时该渠道报 error 并在日报"渠道覆盖"节注明"小红书当日未覆盖"，不视为风险清零。每日低频纪律：每家主体仅跑主体名＋「主体名+投诉」两个词组、limit≤10、间隔≥5 秒随机延迟；诊断命令 `opencli doctor`。搜到的同名企业噪音（异地同名担保/模具公司等）由研判环节剔除。
- 测试与排查一律用中性词，勿用监控名单反复测试第三方工具。

### 见微降级规则（固化）

见微 MCP 每天调用控制在 **≤4 次**（两家各 1 次公告 + 1 次项目状态，或合并查询）。出现以下任一情况立即切换 A 档官网通道，不得反复重试见微：
- 返回配额/次数超限类报错（如"已用 xx/5000"接近上限、429、额度错误码 1308/1310）；
- 接口异常连续 2 次。
切换后用 `tools/fetch_official.py` 走东财新三板公告接口（日常）或股转官网/北交所官网 playwright（东财也失败时），并在日报"渠道覆盖"节注明"见微配额受限，已切换官网通道"。

## 三、每日执行流程

1. `cd company-monitor && python3 tools/dedup.py init-check`（确认 state/monitor.db 就绪；首次无库则初始化并标记当日为 Baseline 模式）。
2. **B 档风险分诊**：对每家公司调 `get_company_risk_scan`，与 state/last_scan.json 中上次各维度计数比对；仅对**计数增加的维度**下钻原子工具取明细。
3. **舆情**：`get_news_sentiment`（sentiment=消极，date_from=上次运行日）。
4. **IPO 财经媒体专项（重点）**：对每家公司用 WebSearch 检索 2–3 组组合——『公司名+IPO+质疑/造假/违规』『公司名+北交所+上会/注册/问询/终止』『公司名+招股书』，重点捕捉挖贝网、云掌财经、新浪证券、凤凰网、每经、财联社、界面、澎湃等财经媒体的质疑与负面报道；`fetch_social.py` 默认查询词已含 IPO/北交所 专项。北交所审核阶段公司（受理/问询/上会/注册）此步骤必做。
5. **B2 档**：见微查 targets.yaml 各主体 otc 公告（近 4 天，label=代码精确）与北交所/IPO 项目状态（在审主体逐家查状态变化；辅导期主体查是否已受理）。触发降级规则即走 fetch_official.py。
6. **C 档**：`python3 tools/fetch_social.py`（微博 m.weibo.cn API+微信公众号 miku_ai+百度+小红书 opencli 四通道，公司名与专项/负面词组合自动执行，输出 outbox/social_items.json；单渠道失败容错继续——微信依赖 venv 环境且底层自带重试，小红书依赖 Mac 开机+Chrome 运行+OpenCLI 扩展+登录态，任一缺失时该渠道单独报错跳过并在日报注明而非当作风险清零）。
7. **去重入库**：把当日全部发现整理为统一条目 JSON（字段见下），`python3 tools/dedup.py feed --file outbox/today_items.json`，得到新增/变化项 outbox/new_items.json。
8. **分级出稿**：按第五节规则对新添项分级，写 `summaries/日报-YYYY-MM-DD.md`（Baseline 日写全量基线报告，格式见第六节）。
9. **管线输出**：`python3 tools/md2pdf.py summaries/日报-*.md` → `python3 tools/sync_to_drive.py` → `python3 tools/send_daily_email.py <md路径> "<摘要>"`。
10. 向用户汇报（300 字内）：红橙事项数、渠道覆盖状态、邮件/Drive 结果。

## 四、条目统一结构与去重指纹

条目字段：company、source（qcc/jianwei/weibo/weixin/baidu）、event_type（诉讼/处罚/执行/失信/冻结/舆情/审核动态/公告）、source_id（案号/文号/公告编号/规范化URL）、title、url、publish_time、severity、evidence（关键摘要）、first_seen。

指纹 `sha1(company + event_type + source_id)`；无稳定 source_id 的舆情用规范化 URL（去 query 参数）作 source_id。`status` 字段：新增/持续/变化/消失——同指纹但 title/金额/进展实质变化时标"变化"。

## 五、分级规则（带响应时限）

- **红（当日报，邮件标题显著标注）**：新增被执行/失信/限高/严重违法；行政处罚决定；刑事立案或人员被采取措施；监管立案调查；北交所审核状态恶化（中止/终止/不予注册/退市风险）；主流媒体实锤负面。
- **橙（三日内跟进）**：新增涉诉（任何角色）或作为被告；经营异常；股权冻结/出质；集中投诉（同话题 ≥3 条）；审核问询新回复或注册进展。
- **黄（周报汇总）**：社媒零星负面；行业性风险波及；中性但值得知悉的公告。
- B、C 档来源条目一律带【待核验】；A 档来源可写实但注明抓取时间。

## 六、日报模板

```
# 公司舆情与法律风险监控日报（YYYY-MM-DD）
## 一、监控总览（表格：公司 | 当日新增红/橙/黄 | 渠道覆盖状态）
## 二、红色事项（当日需处理；每条：事件/来源/链接/抓取时间/建议动作）
## 三、橙色事项（三日内跟进）
## 四、IPO 媒体舆情专项（财经媒体质疑/负面报道盘点＋北交所审核动态＋挂牌公告要点）
## 五、黄色事项（周报汇总口径）
## 六、渠道覆盖与待核验说明（各渠道成功/失败/降级情况）
```
无新增时写"今日无新增"，仍须列渠道覆盖状态。Baseline 报告额外含：各维度存量计数基线表。

## 七、约定

- Baseline 模式：首次运行记录全量存量（不分级推送），次日起只报增量。
- state/monitor.db 与 state/last_scan.json 只能由 tools/dedup.py 维护，agent 不得手改。
- 日报、PDF 同步 Drive 目录"公司舆情监控"（日报/）；邮件发 config/mail.json 指定邮箱，**邮件附件自动重命名为「公司舆情与法律风险监控日报-YYYY-MM-DD.pdf」**（发送脚本从 outbox/ 生成副本，内部存档文件名保持 日报-*.md 不变）。
- 运行时长控制：全流程目标 ≤15 分钟；企查查 MCP 每家 ≤10 次调用（scan 1 + 下钻按需）。
