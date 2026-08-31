---
name: wechat-gzh-format
description: 将文章内容排版为微信公众号 HTML 模板（ai.licheng.uk 视觉风格，全内联样式，一键复制粘贴进公众号编辑器）。当用户要求公众号排版、公众号模板、微信推文格式、把文章做成公众号文章时使用。不适用于网站网页页面本身的开发。
---

# 微信公众号排版模板（法律AI工作站风格）

将任意文章内容（本地 md、网页链接或对话中的文字）排成与 ai.licheng.uk 一致的公众号 HTML。成品 = 一个自带「一键复制」按钮的本地 HTML 文件，用户点按钮复制后粘贴进公众号编辑器即完成排版。

## 工作流

1. 取得文章内容（读文件、抓链接或用对话内容），文字不得改写，只做排版。
2. 以 `assets/template.html` 为骨架：保留头部（组件A）、正文区、加微信引导卡（组件J，默认保留）、底部签名条（组件I）和复制按钮脚本（含摘要 `DIGEST` 常量），按内容需要从组件 B–H 中选用并填充。完整成品参照 `assets/example.html`（AI优先开篇）。
3. 组件选择判断：
   - 文中最重要的观点句 → 组件C 金句卡（可多处）；
   - 并列要点清单 → 组件D 绿点列表卡；
   - 全文核心口号/一句话主旨 → 组件E 亮绿渐变横幅（一篇最多 1 个）；
   - 步骤或自问清单 → 组件F 编号卡；
   - 转变/对比/递进关系 → 组件G 箭头列表；
   - 收尾升华句 → 组件H 深绿结尾卡（一篇最多 1 个，放文末）；
   - 加微信引导卡 → 组件J 二维码卡（base64 内嵌 `assets/wechat-qr.jpg`，放签名条上方，默认保留；用户明确说不要时才移除）。
   组件只减不增：内容没有对应形态就不放，不要为凑组件而拆改原文。
4. 保存到当前工作目录，命名：`公众号排版-ABL-YYYYMMDD-VN-【主题】.html`（同对话多版按 V2 递增）。
5. 用 Chrome headless 以手机宽度截图自检后 `open` 给用户：
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --screenshot=/tmp/预览.png --window-size=414,5200 --hide-scrollbars "file://文件路径"`
6. 告知用户：点「一键复制全文」→ 公众号编辑器粘贴。

## 同步生成摘要（默认随排版一起做）

排版正文的同时写好公众号摘要（≤120 字，微信硬限制；不填后台会默认抓正文前 54 字）：

1. 从原文提炼：核心观点/钩子 + 文章解决什么问题 + 系列感（如有），不改原意、不加"本文介绍了""大家好"等套话，直接陈述。
2. 填入成品 HTML 的 `DIGEST` 常量（工具栏「复制摘要」按钮读取），用户点按钮复制后粘贴到公众号后台「摘要」栏。
3. 对话最终回复中同时附上摘要全文（用户可直接核对字数与内容）。

## 同步生成封面（默认随排版一起做）

排版正文的同时，用 `assets/cover-template.html` 生成公众号首图封面（2.35:1，截图后作为图片上传，无内联样式约束）：

1. 复制模板到临时目录，替换两处占位：胶囊标签（系列/栏目名·全大写，如 `AI PRIORITY · 00`）和标题文字。标题保持自然流（不要手动 `<br>`），需要强调的词用 `<span class="em">` 包裹（自动变深绿）。
2. 标题字号由模板内置 JS 按长度自动缩放（72px 起步、下限 34px、最多两行），无需手工调。
3. 截图为 2 倍高清 PNG（实测输出 1800×766，公众号可接受）：
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --force-device-scale-factor=2 --window-size=900,383 --hide-scrollbars --virtual-time-budget=3000 --screenshot=【输出.png】 "file://【填充后的html】"`
4. 保存命名：`公众号封面-ABL-YYYYMMDD-VN-【主题】.png`，截图自检（文字无溢出、无裁切）后用 `open -R "<png路径>"` 直接打开所在文件夹并选中该图片（用户从 Finder 拖进公众号后台），不要用预览打开图片文件。

## 设计规范速查

- 底色 `#f4f7ef`；品牌深绿 `#0e6f3f`；亮绿 `#9fe870`；标题近黑 `#17281d`；正文 `#3c3c43`。
- 头部渐变 `linear-gradient(160deg,#e4f3cf,#eaf4dc 45%,#f4f7ef)`；横幅渐变 `linear-gradient(135deg,#9fe870,#c4f2a0)`。
- 胶囊标签与编号用等宽字体 `'SF Mono',Menlo,Consolas,monospace`；正文 `-apple-system,'PingFang SC','Microsoft YaHei',sans-serif`。
- 字号：主标题 24px / 副题 17px / 金句卡 16px / 正文 15px / 列表 14px / 签名 12px。行高 1.8–1.9，正文两端对齐。
- 卡片圆角 14px，头部圆角 `0 0 24px 24px`；段落间距 20px，组件下间距 24px。

## 公众号硬约束（违反会丢样式）

- 正文所有样式必须写在内联 `style` 属性；`<style>` 标签只允许放预览工具条样式（位于复制范围之外）。
- 不用外部 CSS/JS/字体/图片；不用 `position:fixed/absolute`、`float`、复杂选择器。
- 复制按钮脚本用 `navigator.clipboard` + `ClipboardItem`（text/html + text/plain），复制范围为 `#gzh-content` 的 `outerHTML`。
- 外层用 `section` 嵌套，不用 `div` 做内容容器；间距优先用 `padding`（嵌套 `margin` 可能被公众号合并）。
- 若文章含图片：公众号图片须上传素材库后使用 `data-src` 链接，模板中先留占位 section 并提示用户替换。
- 二维码图片（组件J）以 base64 内嵌：粘贴进公众号编辑器时微信会自动转存为其 CDN 图片，不会丢失。若更换二维码源图：裁成方形、缩至 ≤400px、JPEG 质量 75（约 65KB）后重新 base64，避免 HTML 过大或转存失败。
