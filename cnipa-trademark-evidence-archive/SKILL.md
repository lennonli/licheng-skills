---
name: cnipa-trademark-evidence-archive
description: Export and organize evidence PDFs from the CNIPA 商标网上检索系统. Use when asked to核查商标, collect Chinese trademark detail/process evidence, query trademarks by applicant name or application/registration number, or archive CNIPA trademark pages as PDFs for legal due diligence or IP evidence files.
---

# CNIPA Trademark Evidence Archive

## Goal

Create local evidence folders for Chinese trademark records from the CNIPA 商标网上检索系统, with separate PDFs for the trademark detail page and trademark process page.

## Inputs

Confirm or infer:

- `applicant_name`: trademark applicant/company name.
- `trademark_numbers`: one or more application/registration numbers when known.
- `output_root`: default to `~/Downloads/<applicant_name>`.
- `pages`: default to `商标详情` and `商标流程`.

Do not store credentials, OTPs, cookies, or private account/session details in the skill output or summaries. If the site requires login or verification, ask the user to complete it in their browser.

## Workflow

1. Open the CNIPA trademark search site in Chrome:
   - `https://wcjs.sbj.cnipa.gov.cn/home`
   - Use the user's existing browser session when login state or verification matters.

2. Enter comprehensive search:
   - Click `商标综合查询` / `商标综合检索`.
   - Search by `applicant_name` if collecting all marks for a company.
   - Search by `trademark_number` if the task is for a known mark.

3. Open each target record:
   - From the result list, open the detail page for the target trademark.
   - Verify the visible `申请/注册号`, `国际分类`, and `申请人名称（中文）`.
   - Record only the workflow shape in responses; do not expose sensitive client details beyond what the user needs.

4. Export the trademark detail page:
   - Stay on or switch to `商标详情`.
   - Use the page `打印` button if available; otherwise use Chrome print.
   - Enable Chrome's built-in `Headers and footers` / `页眉和页脚`; the exported PDF must show
     date, page title, URL, page number, and total page count.
   - In Chrome print preview, choose `保存` / Save as PDF.
   - Create/select folder `<output_root>/商标-<trademark_number>/`.
   - Save as `商标详细内容-1.pdf` unless the user asks for clearer names such as `商标详情.pdf`.

5. Export the trademark process page:
   - Click the `商标流程` tab/link or the `商标流程` row's `点击查看` link.
   - Confirm the process view shows columns such as `申请/注册号`, `业务名称`, `环节名称`, `结论`, and `日期`.
   - Enable Chrome's built-in `Headers and footers` / `页眉和页脚`; the exported PDF must show
     date, page title, URL, page number, and total page count.
   - Print and save to the same folder as `商标详细内容-2.pdf` unless the user asks for clearer names such as `商标流程.pdf`.

6. Repeat for all target marks:
   - Return to the result list or next detail page.
   - Repeat detail and process exports per trademark number.
   - Keep each trademark in a separate `商标-<trademark_number>` folder under the applicant folder.

7. Validate:
   - Confirm each `商标-<trademark_number>` folder exists.
   - Confirm each folder contains both expected PDFs.
   - Confirm each PDF contains Chrome header/footer information: date, title, URL, page number,
     and total pages (for example `1/1` or `1/2`, `2/2`).
   - If a page fails to save, is unavailable, or is blocked by verification, note the issue instead of inventing a result.
   - Report the final root folder and list the trademark folders/files created.

## Scripted Chrome Path

When the user asks to process by script, use the Chrome plugin and the helper script at
`scripts/export-cnipa-trademark-pdfs.mjs`.

Prerequisites:

- The user has an open Chrome tab on the CNIPA `商标检索结果` page.
- The result page belongs to the intended applicant or target search.
- The Chrome plugin session can access the user's existing CNIPA login/session state.

The script:

- Claims the current `商标检索结果` tab.
- Reads `sessionStorage.params.dataList` when available; if not, builds a minimal record list
  from the visible result table.
- Opens detail pages by real-clicking the visible application/registration number link on the
  result page. Do not navigate to `/detail` by only writing `sessionStorage` and assigning
  `location.href`; that path can leave Chrome CDP in a paused document response state and can
  make the process tab load only a header.
- Exports the detail page with Chrome DevTools `Page.printToPDF`, with Chrome's built-in
  headers and footers enabled. Do not provide custom `headerTemplate` or `footerTemplate`
  unless the user explicitly asks for a non-Chrome layout.
- Clicks the official visible `商标流程` tab/link, then exports the process page.
- Treats the process PDF as usable only after confirming actual flow rows for the target
  application/registration number. If the process page shows only headers such as `业务名称`
  and `环节名称`, do not report it as a complete process archive.

Example Node REPL invocation:

```js
const { exportCnipaTrademarkPdfs } = await import("/Users/licheng/.codex/skills/cnipa-trademark-evidence-archive/scripts/export-cnipa-trademark-pdfs.mjs");
const result = await exportCnipaTrademarkPdfs({
  applicantName: "深圳潜行创新科技有限公司",
  trademarkNumbers: ["87649562", "86982451"],
  outputRoot: "/Users/licheng/Downloads/深圳潜行创新科技有限公司"
});
nodeRepl.write(JSON.stringify(result, null, 2));
```

## Practical Notes

- The site states that data is for reference and may lag; preserve the page exactly as displayed for evidence management.
- Prefer the Chrome plugin and semantic UI targets (`商标综合查询`, `查询`, result-row
  application number links, `商标流程`) over coordinates. Do not use Computer Use unless the
  user explicitly asks for it.
- If using the scripted Chrome path, prefer `sessionStorage.params.dataList` over scraping table
  text when it exists because it contains the exact record object the Vue app passes into
  `/detail`; fall back to table rows when the current result page stores only query params.
- The save panel may default to `商标详细内容`; append or replace the suffix deliberately before saving.
- If the user prefers clearer output names, use `商标详情.pdf` and `商标流程.pdf`; otherwise follow the demonstrated convention `商标详细内容-1.pdf` and `商标详细内容-2.pdf`.
- For legal due diligence, do not edit the exported PDF contents after saving.

## Lessons From Failed Runs

- Standalone Playwright may be blocked by CNIPA with `403 Forbidden`; use the user's existing
  Chrome session through the Chrome plugin.
- Do not rely on old `商标检索结果` tabs. Verify the result page contains the intended applicant
  name before exporting; if it does not, rerun `商标综合检索`.
- Programmatic value assignment may not trigger Vue state. If a search button click does not
  open results, fill the applicant field with a real browser input action and click `查询`.
- Directly setting `sessionStorage.params` and navigating to `/detail` can produce stuck
  Chrome states and incomplete process pages. The robust route is: result page -> real click
  target application number -> new detail tab -> print detail -> click `商标流程` -> print flow.
- Chrome built-in headers and footers are produced by `displayHeaderFooter: true`. They include
  date, title, URL, and page number/total pages. This is a required output condition for
  trademark evidence PDFs; avoid custom templates for ordinary evidence exports.
- Validate every exported PDF with text extraction: detail PDFs must contain the target
  application number and applicant; process PDFs must contain `业务名称`, `环节名称`, and at least
  one flow row for the same target number.
