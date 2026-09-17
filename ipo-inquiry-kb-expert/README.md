# IPO问询案例专家（WorkBuddy 专家包）

IPO / 新三板挂牌审核问询案例与证券法规检索专家。基于公开知识库 `lennonli/ipo-inquiry-kb`：

- **IPO问询案例库**：2023–2026 四年度、1,600+ 份案例，一司一文，每问含「问询要点 → 回复与核查要点 → 执业提示」；
- **证券法规知识库**（`rules/`）：15 大类、1,000+ 部投行法规与自律规则，含官方附件全文与来源溯源。

知识库持续定期更新，主仓为唯一数据源。

## 包结构

```
ipo-inquiry-kb-expert/
├── .codebuddy-plugin/plugin.json   # 专家配置与市场展示信息
├── agents/ipo-kb-expert.md         # Agent 定义（frontmatter + 系统提示词）
├── skills/ipo-kb/                  # 预加载技能：SKILL.md + kb_search.py（本地检索脚本）
├── avatars/expert.png              # 512×512 头像
└── README.md
```

## 工作原理

专家预加载 `ipo-kb` 技能。会话开始时执行 `python3 skills/ipo-kb/kb_search.py list`：
本机没有知识库会**自动克隆**到 `~/ipo-inquiry-kb`（约百余 MB，需可访问 github.com），
之后所有检索都在本地文件上完成（无网络依赖、无配额）；`kb_search.py update` 同步最新内容。
法规库通过系统内置的 Grep/Read 直接检索 `rules/` 目录。

## 可选：声明远程 MCP 依赖

远程 MCP `legal-knowledge`（`https://mcp.licheng.uk/mcp`）提供五个知识库（含 `rules`）的加权检索。
本包**默认不声明**该依赖：一是专家本地即可完整工作（WorkBuddy 文档建议仅在必须依赖时声明），
二是该服务为自托管，可能间歇不可用，声明后会成为进入对话前的强制连接步骤。

如希望启用（用户召唤专家时弹出 Token 填写卡片，连接后可直接调用 MCP 工具），在包根目录新增
`.mcp.json` 并在 `plugin.json` 加 `"dependencies": { "mcpServers": "./.mcp.json" }`：

```json
{
  "mcpServers": {
    "legal-knowledge": {
      "type": "http",
      "url": "https://mcp.licheng.uk/mcp",
      "headers": { "Authorization": "Bearer ${LEGAL_KB_TOKEN}" },
      "x-workbuddy": {
        "displayName": { "zh": "法律知识库 MCP", "en": "Legal Knowledge MCP" },
        "description": { "zh": "连接后可检索IPO问询案例库（四年度）与证券法规知识库。", "en": "Search IPO inquiry cases (2023-2026) and securities rules." },
        "icon": "./avatars/expert.png",
        "auth": {
          "type": "token",
          "tokenSchema": {
            "title": { "zh": "配置知识库访问 Token", "en": "Configure Knowledge Base Token" },
            "description": { "zh": "请输入库所有者提供的访问 Token。", "en": "Enter the access token provided by the knowledge base owner." },
            "docUrl": "https://ai.licheng.uk/kbskill/",
            "docLabel": { "zh": "如何获取 Token?", "en": "How to get a token?" },
            "fields": [
              {
                "key": "LEGAL_KB_TOKEN",
                "label": { "zh": "访问 Token", "en": "Access Token" },
                "placeholder": { "zh": "请输入 Token", "en": "Enter token" },
                "type": "password",
                "required": true,
                "description": { "zh": "将写入 Authorization Header", "en": "Written into the Authorization header" }
              }
            ]
          }
        }
      }
    }
  }
}
```

> 按 WorkBuddy 规范，专家包内**严禁硬编码真实 Token**，务必使用 `${LEGAL_KB_TOKEN}` 占位由用户填写。

## 数据纪律

案例与法规内容均系公开披露文件与官方规则的提炼整理；正式对外文件援引前须回见微数据、
交易所官网或官方法规库核对原文；「执业提示」系整理者个人心得，仅供参考。
