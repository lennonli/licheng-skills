# 公司舆情与法律风险监控系统·从零搭建教程（Agent 复刻指南）

> **版本**：V2（20260827）｜**适用读者**：接手维护或在新环境复刻本系统的 AI Agent（ZCode 及同构 CLI 环境）
> **V2 变更**：小红书渠道由"周度人工抽查"升级为 **OpenCLI 半自动通道**（Agent-Reach 工具链桥接浏览器登录会话），新增第 8.3 节接入教程与相关坑表项。
> **隐私声明**：本文为通用教程，不含任何客户名称、证券代码、信用代码、人员姓名与邮箱地址；凡涉具体配置处均以占位符表示，实际值以部署目录内 `config/targets.yaml`、`config/mail.json` 为准，**不得把其中的值誊抄进任何对外文档**。
> **完成标准**：一个每日定时任务自动产出《公司舆情与法律风险监控日报》（PDF），经 Google Drive 同步与邮件送达收件人，且第二天起只报告新增/变化事项。

---

## 0. 开工前必须与用户确认的三个决策点（阻塞项）

不要跳过这些直接动手：

1. **监控主体清单**：公司全称、是否已上市/新三板挂牌、是否有北交所/IPO 在审进程。这决定要不要接公告类数据源与IPO专项监控；
2. **小红书渠道口径**：无全自动合规通道。两个选项——(a) **OpenCLI 半自动**（本章 8.3 节，复用用户本人浏览器的小红书登录会话每日低频检索，依赖 Mac 开机＋Chrome 运行＋登录态）；(b) 周度人工抽查（每周五日报附提醒清单）。无论哪种都要向用户如实交代封号风控的可能性并建议小号；
3. **通知管线**：日报走什么通道送达（本项目方案：本地 PDF → Google Drive 桌面版同步目录 → 邮件；需用户预先授权每日自动发信）。

---

## 1. 架构总览

```
单个 Cron 任务（每天早晨错峰时段，遍历 targets.yaml）
   │
   ▼
SKILL.md 固化流程（规则中枢：取数顺序/分级/红线/模板，逻辑不写在 cron prompt 里重复维护）
   │
   ├─ B 档 企业风险主数据源（商业 MCP）：35 维风险分诊 → 只下钻计数增加的维度
   ├─ B 档 舆情情感过滤（消极）
   ├─ B2 档 公告与审核状态 MCP（每日限调用次数，超限自动降级官方通道）
   ├─ IPO 专项 WebSearch（财经媒体质疑/负面，在审主体必做）
   ├─ C 档 社媒 playwright 三通道（微博移动端 API / 搜狗微信 / 百度资讯）
   │
   ▼
统一条目 JSON（company/source/event_type/source_id/title/url/publish_time/severity/evidence）
   │
   ▼
SQLite 指纹去重（sha1(company|event_type|source_id)）——首次 Baseline 全量入库，之后只报增量
   │
   ▼
红/橙/黄分级（带响应时限）→ 日报 md → PDF → Drive → 邮件
```

四条铁律（全系统的成败关键）：

1. **MCP 只负责拿数据；Skill 负责"怎么查、怎么判、怎么写"；Cron 只负责触发**。不要把业务逻辑散落在定时任务提示词里；
2. **一个定时任务遍历主体清单，绝不一司一任务**。加公司只改 `config/targets.yaml`；
3. **Baseline 全量一次，此后只报增量**。没有这一步，第三天起日报会被存量诉讼淹没而失去阅读价值；
4. **判断交给 LLM（相关性/分级/研判），记忆交给 SQLite**。LLM 不承担"记住昨天查过什么"的职责。

---

## 2. 数据源分档与方法论

| 档位 | 内容 | 角色 | 备注 |
|---|---|---|---|
| A 档 官方 | 裁判文书网、执行信息公开网、信用中国、企业信用公示系统、交易所/股转官网 | **唯一可作结论依据**；日常作为复核通道，工具产出标【待核验】，对外前回到此档二次核验 | 无可靠公开自动化接口，半自动定向访问即可 |
| B 档 商业 MCP | 企业风险 35 维扫描＋原子工具、新闻舆情（带情感标签） | **线索发现主力**，覆盖约 70% 需求 | 每家每次运行的调用预算固定；先 scan 后按需下钻 |
| B2 档 公告/审核 MCP | 公告检索、发行审核项目状态 | 挂牌/上市主体动态跟踪 | 配额敏感：**单日 ≤4 次**，触发限额立即切换 A 档官方通道 |
| C 档 社媒 | 微博、微信公众号搜索、百度资讯、**小红书（OpenCLI 半自动）** | 苗头感知，噪音最大，只做初筛 | 前三者 playwright＋系统 Chrome；小红书走 opencli CLI（见 8.3）。全部候选交研判环节定性 |

**选型纪律**：任何 GitHub 仓库引入前必须 `gh api repos/<owner>/<repo>` 核验 stars / license / archived / pushed_at。实操教训（2026 年实测，引以为鉴）：

- 曾被广泛推荐的微信公众号 RSS 项目**已归档停止维护**，底层接口一旦变动即死，勿再选型；
- 一个知名的一键聚合信息收集工具**主仓库已 404**，只剩零星镜像；
- 多平台爬虫巨兽（数万 star）README 明文**禁止商用**，只能作架构参考；
- 某多 Agent 舆情系统为 **GPL-2.0**——独立部署可用，改码集成会触发开源传染义务，商用场景慎碰；
- star 数个位数、无 license 的个人封装**不得作为生产数据通道**（尤其会把监控名单传给第三方）；
- 企业数据第一层永远优先你已有的、经过授权的商业 MCP，而不是另装第三方 CLI/MCP 重复建设。

---

## 3. 环境前提清单

搭建前逐一确认（缺哪补哪）：

1. ZCode（或同类 CLI agent）＋ MCP 配置就绪：企业风险系列工具、新闻舆情工具、公告/项目检索工具各一套；
2. `python3` ≥3.10；`pandoc`；Google Chrome（playwright 走 `channel="chrome"`，无需额外下载浏览器内核）；`rsync`；
3. Google Drive 桌面版已登录（同步根目录存在 `~/Library/CloudStorage/GoogleDrive-<账号>/我的云端硬盘/`）；建议新建专属文件夹（如「公司舆情监控」，下分 `日报/`、`PDF/` 子目录）；
4. 邮件发送通道：agently-cli（或等效 CLI），已完成用户授权，收件邮箱写入 `config/mail.json`（仅存本地）；
5. sqlite3（Python 内置模块即可）。

---

## 4. 目录结构（照此建好）

```
company-monitor/
├── SKILL.md                      # 规则中枢（第二节流程+第五节分级+第六节模板+第七节约定全写在这里）
├── TUTORIAL-*.md                 # 本教程
├── config/
│   ├── targets.yaml              # 监控主体池＋别名＋负面词表（加公司只改这个文件）
│   └── mail.json                 # {"to": "<收件邮箱>"} 仅本地存放
├── state/
│   ├── monitor.db                # SQLite 去重库（只准由 dedup.py 读写）
│   └── last_scan.json            # 上次运行日＋各公司风险维度计数快照（供次日 diff）
├── outbox/                       # 中间产物（gitignore/不同步 Drive）
│   ├── today_items.json、extra_items.json、new_items.json
│   ├── social_items.json、social_raw/*.txt、official_items.json
├── summaries/                    # 日报存档（日报-YYYY-MM-DD.md/pdf）
├── raw/                          # 留存原件（同步至 Drive/PDF）
└── tools/
    ├── dedup.py                  # SQLite 指纹去重（init-check/feed/stats 三命令）
    ├── fetch_social.py           # 社媒四通道（微博m.weibo.cn API＋搜狗微信＋百度资讯＋小红书opencli）
    ├── fetch_official.py         # 官方公告降级通道（东财JSON API→股转官网→北交所公示）
    ├── md2pdf.py                 # pandoc gfm→HTML＋Chrome 无头打印（中文 CSS 优化）
    ├── sync_to_drive.py          # rsync 同步 summaries 与 raw 到 Drive（注意 --ignore-existing）
    ├── send_daily_email.py       # 两阶段确认发信；附件按对外规范名重命名
    └── build_baseline.py         # Baseline 首日一次性数据组装（跑完即归档）
```

若在本项目已有实例上工作，`tools/` 五个脚本**直接复用现有文件即可**，不要重写；只有换语言环境时才需要按下文第 9 节要点重实现。

---

## 5. 第一步：主体核验（反编造红线先行）

1. 对每家监控对象调企业工商核验工具，逐字段记录：全称、统一社会信用代码、登记状态、成立日期、注册资本、实缴资本、法定代表人、所属地区、国标行业、人员规模/参保人数；
2. **核实资本市场身份**（这步有著名陷阱）：
   - 用发行审核项目库（如见微 search_projects）查 IPO 进程轨迹；
   - **陷阱：尚未获受理的公司在 IPO 项目库查不到属于正常现象，不是数据缺失**。正确做法是用网络检索交叉确认其证券简称与代码，再查挂牌（OTC）公告库与其最新公告印证申报阶段（辅导备案/受理/问询/过会/提交注册）；
   - 挂牌公司同时记住：代码＋简称查询要精确匹配，模糊词可能 0 命中。
3. 把以上事实连同简历式 `aliases`（历史名、简称、地域性称呼）一并写入 `targets.yaml`。在 aliases 里诚实列出常见误命中项（同业同名企业），供后续降噪。

---

## 6. 第二步：写 `config/targets.yaml`（模板）

```yaml
companies:
  - name: <公司全称>
    short: <证券简称或四字短名>
    neeq_code: "<挂牌代码>"        # 如适用
    credit_code: "<统一社会信用代码>"
    region: <省市>
    industry: <行业一句话>
    legal_rep: <法定代表人姓名>     # 内部配置文件可存；严禁誊入日报正文以外的外发物
    bse_track: <当前北交所/IPO阶段一句话>
    aliases: [<简称>, <习惯称谓>]
    risk_extra: []
```

附两组词表（中文逗号分隔的数组）：

- `negative_keywords`：诉讼 仲裁 处罚 立案 调查 被执行 失信 冻结 查封 破产 欠薪 拖欠 裁员 维权 投诉 曝光 举报 质量 事故 违约 退货 售后 骗 整改 警示 问询 中止 终止 —— 以及**在审主体的专属组：IPO 北交所 辅导 注册 问询**；
- `red_keywords`（命中即红色）：刑事 被执行 失信 限高 严重违法 立案调查 移送 终止上市。

---

## 7. 第三步：写 `SKILL.md`（规则中枢，六节必写）

### 7.1 合规红线（逐字写入，不可删减）

1. 商业数据源与社媒信息仅作**线索**，进入日报一律标"【待核验】"；对外出具必须回 A 档官方来源二次核验；
2. 评论区/社媒内容**只记录数量、平台与倾向概述**，不落原文与账号个人信息；不采集自然人个人信息；
3. 仲裁无全国统一公开库：报告只能写"**未检索到公开仲裁信息**"，禁止写"不存在仲裁案件"。间接线索来源：公告、仲裁保全/执行/撤裁案件、报道；
4. 渠道抓取失败必须在日报"渠道覆盖"节如实记录；**禁止以"未发现风险"掩盖"未覆盖渠道"**；
5. 本目录外不写文件；不得创建/修改/删除定时任务；除授权邮箱外不得对外发送。

### 7.2 数据源分档与降级规则（固化成文字）

- 各档定位按第 2 节表格写明；重点写死**降级链**：B2 档公告 MCP 单日预算（≤4 次）→ 触发配额报错/连续 2 次异常 → 立即改走 `tools/fetch_official.py announcements`（零浏览器 JSON API）→ 再失败走 `neeq-web`（股转官网 playwright）→ 审核状态另有 `bse-status` 尽力而为子命令。降级须在日报注明。

### 7.3 每日执行流程（十步 SOP）

1. `python3 tools/dedup.py init-check` 确认 Baseline/增量模式；
2. 35 维风险扫描 → 读 `state/last_scan.json` 比对各维度计数 → **只对计数增加的维度**下钻明细工具；
3. 舆情情感过滤（sentiment=消极，date_from=上次运行日）；
4. **IPO 财经媒体专项（在审主体必做）**：WebSearch『主体名+IPO+质疑/造假/违规/信披』『主体名+北交所+上会/注册/受理/终止』各 2–3 组；
5. B2 档公告＋审核状态（遵守降级规则）；
6. `python3 tools/fetch_social.py`（失败渠道容错继续，绝不中断整体）；
7. 组装当日条目 `outbox/today_items.json` → `python3 tools/dedup.py feed --file ...` 得增量；
8. 按 7.4 分级出稿 `summaries/日报-YYYY-MM-DD.md`；
9. 管线三连：md2pdf → sync_to_drive → send_daily_email；
10. 向用户汇报 ≤300 字（红橙黄新增数、渠道覆盖与降级、邮件/Drive 结果）。

运行时长控制 15 分钟内，超时优先保"风险分诊＋出稿"。

### 7.4 分级规则（红橙黄＋响应时限）

- **红（当日报，邮件标题显著标注）**：新增被执行/失信/限高/严重违法；行政处罚决定；刑事立案或人员被采取措施；监管立案调查；审核状态恶化（中止恶化/终止/不予注册）；主流媒体实锤负面；
- **橙（三日内跟进）**：新增涉诉或作为被告；经营异常；股权冻结/出质；集中投诉（同话题≥3 条）；审核问询新回复或注册进展；
- **黄（周报汇总）**：社媒零星负面；中性但知悉性公告；行业性风险波及。

### 7.5 条目结构与指纹规则

条目字段固定九项：company / source / event_type / source_id / title / url / publish_time / severity / evidence。指纹 = `sha1(company + event_type + source_id)`；**诉讼用案号**、公告用编号、舆情用规范化 URL（去 query 参数）作 source_id；无稳定 id 时退化为"no-id-"+随机哈希但须人工审读。同指纹标题实质变化 → status=变化。

### 7.6 日报模板与全局约定

模板（无新增也须输出渠道覆盖表；周五自动附小红书人工抽查清单）：监控总览表 → 红色事项 → 橙色事项 → IPO 媒体舆情专项＋审核动态 → 黄色事项 → 渠道覆盖与待核验说明。
约定三件事：state 库只由脚本维护；Baseline 日记录全量基线不分级推送；**内部存档文件名 `日报-日期.md`，邮件附件由发送环节自动重命名为「公司舆情与法律风险监控日报-日期.pdf」副本放在 outbox/（不入 Drive 同步目录）**。

---

## 8. 第四步：B 档与 C 档采集实现要点

### 8.1 去重引擎 `dedup.py`

- schema：items 表（fingerprint UNIQUE, …first_seen/last_seen/last_title）＋ meta 表；
- `init-check`：库空则输出 MODE:BASELINE 提示做全量；非空输出 MODE:INCREMENT；
- `feed --file X.json`：逐条比对指纹，新增插入并计入输出 new_items.json；旧条目标题实质变化计 status=变化并保留 first_seen；其余只更新 last_seen；
- `stats`：公司×类型计数（自查用）；
- **交付前自测法**：追加一条 TEST 行 feed 一遍应得"新增 1 条"，再 feed 一遍应得 0——幂等通过后删除测试行。

### 8.2 社媒采集 `fetch_social.py`（本系统最硬的骨头，三条血泪教训）

1. **微博不能用桌面搜索页**（s.weibo.com 无登录态 100% 弹反爬）。正解：走 `m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D<URL编码词>&page_type=searchall` JSON API，iPhone UA＋视口；**且必须先用 page.goto 导航到 m.weibo.cn 同域后再 page.evaluate 发起 fetch**，否则浏览器上下文跨域直接 `Failed to fetch`；
2. **微博候选不做负面词过滤**——IPO 质疑话术（"数据打架""业绩真实性""拷问毛利率"）不含硬负面词会被误杀清空。微博结果只按主体名匹配即保留，负面与否交研判环节；
3. 组合词（主体名+投诉）在微博常 0 结果，**单查主体名反而有效**；百度/搜狗反之吃组合词。channels：搜狗微信 `weixin.sogou.com/weixin?type=2&query=`；百度资讯 `www.baidu.com/s?rtt=4&tn=news&word=`。

通用设计：启发式初筛（行长 10–220、命中主体名/别名、命中负面词、前 80 字符签名去重、单查询截断 15 条）；原始页面文本全部落盘 `outbox/social_raw/` 留存核查；错误逐条收集进 errors 数组单渠道失败不中断；请求间 1.5–3 秒随机延迟。**antispider 特征页检测**：返回体短于阈值且含"验证码/安全验证"字样即判定拦截，记 error。

### 8.3 小红书通道（Agent-Reach ＋ OpenCLI，半自动）

**工具链选型结论**：GitHub 项目 `Panniantong/Agent-Reach`（引入前照例 `gh api` 核验：数万 star、MIT、活跃）。它本质是**工具路由器**——替 Agent 选型、安装、体检各平台上游 CLI，不是爬虫本身。其小红书路线＝OpenCLI 浏览器桥接：**复用用户本人 Chrome 里已有的小红书登录会话**读取内容，不代登录、Cookie 不上传不落盘，合规设计在同类方案中最克制（对比：带 cookie 注入的第三方爬虫属平台协议禁止项，勿碰）。

安装四步（后两步只能由用户本人完成）：

```bash
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip   # 本体
agent-reach install --env=auto --system --channels=opencli,xiaohongshu     # 装上游与 skill
# ③ 用户在 Chrome 安装 OpenCLI 扩展(Chrome Web Store 搜 OpenCLI), 唯一无法代劳的一步
opencli doctor          # 见 "Extension: connected (vX)" 即桥接成功
# ④ 用户在 Chrome 里登录 xiaohongshu.com(扫码/验证码, 只能本人操作)
```

命令用法与解析要点：

```bash
opencli xiaohongshu search "<关键词>" --limit 10 -f json
# JSON 数组字段: rank/title/author/likes/published_at/url —— published_at 可直接进增量去重
```

工程接入要点：

1. **依赖链四件套**：Mac 开机＋Chrome 进程＋扩展连接＋登录态。任一缺失即失败——脚本须单渠道容错记录 errors 并在日报注明"当日未覆盖"，绝不视为风险清零；
2. **低频纪律**：每家主体每日仅跑「主体名」＋「主体名+投诉」两个词组、limit≤10、查询间隔 ≥5 秒随机延迟（该平台风控敏感，官方亦自警示有账号限制可能）；
3. **噪音特征**：会命中异地同名企业（担保公司、模具厂等），研判环节按地域/行业剔除；
4. **测试纪律**：排查与联调用中性词（如日常消费品词），**不要拿监控名单反复打第三方工具**——名单只应出现在正式监控运行里；
5. 账号建议：向用户说明风险后由其选择主号或小号。

### 8.4 官方公告降级通道 `fetch_official.py`

- `announcements`：东方财富新三板公告 JSON API（`np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=50&...&stock_list=<代码>`，Referer 带官网域名即可直连，零浏览器、最稳），按 days 参数过滤近 N 天；
- `neeq-web`：股转官网披露页 playwright 兜底（正文正则抽"日期+标题"行）；
- `bse-status`：北交所审核公示页尽力而为，主体名逐行匹配。

### 8.5 交付管线三脚本（可从姊妹项目整体复制改配）

- `md2pdf.py`：pandoc gfm→HTML5 ＋ 系统 Chrome `--headless --print-to-pdf`；CSS 注意中文字体栈（PingFang SC 等）与表格 word-break；
- `sync_to_drive.py`：rsync 到 Drive 同步目录（summarries→日报/，raw→PDF/）；**raw 目录用 `--ignore-existing`**——Drive 文件提供器对已存在文件做内容比对会超时挂起，这是实测坑；
- `send_daily_email.py`：agently-cli 两阶段协议（首轮取 confirmation_required→带 confirmation_token 重发）；收件人读 `config/mail.json`；invalid_grant 报错时明确提示"授权失效需人工重新授权"，不得尝试自行绕过；附件重命名副本生成于 outbox/（见 7.6）。

---

## 9. 第五步：Baseline 执行 SOP（首日一次性）

严格按序执行并把每步事实落到台账：

1. 工商核验（第 5 节）→ 写入 targets.yaml；
2. 35 维风险扫描两家主体 → **只对有条目的维度下钻**明细工具 → 逐条录入（案号为王，金额/日期/当事人/结果保全）；
3. 舆情情感查询（消极）→ 财经媒体报道逐条记（日期/媒体/标题）；
4. B2 档：近期公告（近 30 天用于基线更稳）＋审核项目状态轨迹；
5. IPO 专项 WebSearch 补时间线（受理/问询轮次/中止恢复/上会/注册节点）与新报道；
6. `fetch_social.py` 全量跑一遍（也是对脚本的三通道联测）；
7. `build_baseline.py` 思路组装 `today_items.json` → `dedup.py feed` 入库 → `stats` 对账（条目数应等于各源之和）；
8. `last_scan.json` 记录上次运行日＋各维度计数快照＋当前审核阶段（次日起 diff 的基准）；
9. 写 Baseline 报告（特有四件套：**审核时间线、维度存量基线表、渠道覆盖表、待核验清单**），走管线三连发邮件；
10. 注册定时任务（下一节），然后把本次工程沉淀写入 memory。

---

## 10. 第六步：注册定时任务（只有这一个）

- **频率与时点**：每天一次，选在与用户既有任务错峰的清晨时段（示例 `30 8 * * *`）；
- **Prompt 自包含性核对清单**：工作目录绝对路径｜指到 SKILL.md 按流程执行｜当前主体概要｜十步流程的关键参数（比对文件、去重文件名、分级口径、降级条件、管线命令序列）｜**禁止改动其他定时任务**｜外发限制（仅授权邮箱）｜兜底要求（渠道失败如实记录、不得编造、仲裁表述）｜汇报格式与时长控制；
- 若环境支持 Keep awake 设置则打开（睡眠期任务不触发也不补跑，属预期行为须向用户交代）；
- 自查要点：绝不在 prompt 里写客户的敏感身份信息之外的冗余——其余全部细节由 SKILL.md 与 targets.yaml 承载，避免两处漂移。

---

## 11. 第七步：收尾检查清单（10 项全勾才算完工）

- [ ] `dedup.py` 幂等自测通过（TEST 行两次 feed 结果 1→0，随后清除）；
- [ ] 三社媒通道各有留存 raw 文件且 errors 为空或如实记录；
- [ ] 小红书通道 `--platform xhs` 烟测通过（若用户选择 OpenCLI 半自动口径）；
- [ ] 见微降级链演练：人为限定状态下确认东财通道可独立出数据；
- [ ] Baseline 报告 PDF 生成成功（体积 >100KB 且非空白）；
- [ ] Drive 日报/PDF 两目录可见当日文件；
- [ ] 测试邮件到达收件箱，附件名为「公司舆情与法律风险监控日报-日期.pdf」；
- [ ] targets.yaml 与 SKILL.md 中无一处编造的法条/文号；所有【待核验】项已在日报尾注列明；
- [ ] last_scan.json 快照写好，`init-check` 已转为 INCREMENT 模式；
- [ ] 定时任务 prompt 经 300 字压缩后仍可独立执行；
- [ ] memory 更新：目录路径、automation id、接口坑一览。

---

## 12. 坑表速查（前一世代实践的全部学费）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | 微博搜任何词都"触发反爬" | s.weibo.com 桌面页无登录态强反爬 | 改 m.weibo.cn JSON API |
| 2 | 微博 API 报 `Failed to fetch` | evaluate 里发起的 fetch 跨域被 CORS 拦 | 先 goto m.weibo.cn 同域导航再发 fetch |
| 3 | 微博返回正常却 0 候选 | 初筛负面词过滤误杀质疑类话术 | 微博只按主体名保留，负面判定交研判 |
| 4 | 组合查询 0 结果 | 平台召回特性差异 | 微博用单独主体名；百度/搜狗用组合词 |
| 5 | 搜狗微信噪音大 | 招聘 JD 中"投诉处理"等词汇误命中 | 初筛宽进、研判严出，噪音在日报剔除 |
| 6 | 系统内查不到某公司 IPO 记录 | **未获受理属正常，不是缺数** | 网络＋OTC 公告交叉核实其代码/阶段 |
| 7 | 见微频繁撞额度 | 大批量抓取须走交易所官网 | 单日 ≤4 次，超限即降级 fetch_official.py |
| 8 | `feed` 显示 0 新增但库里其实写了 | 输出文件被重复执行覆盖 | 以库内 first_seen 为准，显示层不误信 |
| 9 | Drive 同步卡住挂起 | 文件提供器对已存在文件内容比对慢 | raw 目录加 `--ignore-existing` |
| 10 | 命令行嵌中文含双引号字符串报语法错 | heredoc 引号边界冲突 | 数据组装写成 .py 文件，字符串统一单引号定界 |
| 11 | 首份邮件附件名与内部存档不一致 | 对外命名与内部存储需求冲突 | 发送环节生成 outbox 重命名副本，内部不动 |
| 12 | opencli 报 unknown option '-n' | 新版语法变化 | 搜索限数用 `--limit N`；输出格式 `-f md/json/yaml` |
| 13 | Extension: not connected | Chrome 扩展未装/未启用 | `opencli doctor` 诊断＋daemon restart；仍不通让用户从 Chrome Web Store 装 OpenCLI |
| 14 | 小红书搜出大量同名企业 | 简称无唯一性 | 初筛按主体名宽保留、研判按地域+行业剔除，不靠加词硬过滤 |

## 13. 定性与合规备忘（写给所有使用者）

本系统产出的定性是"**所内线索发现工具**"而非尽调结论。日报里每一格 B/C 档信息都带着【待核验】；只有当有人真的回到裁判文书网、执行信息公开网、官方法规库把原文摆在桌面上，它才能变成给客户的确定性意见。工具越省心，越要记得这句话。

（完）
