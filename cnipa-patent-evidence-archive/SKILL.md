---
name: cnipa-patent-evidence-archive
description: Export and organize evidence PDFs from the CNIPA "中国及多国专利审查信息查询" system. Use whenever asked to collect Chinese patent/application review information, save CNIPA case-detail pages as PDFs, create patent due-diligence working-paper evidence, batch print CNIPA panels with URL/date headers, or archive patent evidence by company/applicant name and patent/application number.
---

# CNIPA Patent Evidence Archive

## Goal

Create a clean local evidence folder for Chinese patent/application records from the CNIPA "中国及多国专利审查信息查询" detail page, with separate Chrome-print PDFs for important information panels and a final folder named with the applicant/company and patent/application number.

The preferred output is not a self-made summary PDF. For legal due-diligence working papers, preserve CNIPA page fidelity: each PDF should be a Chrome-style print of the actual CNIPA detail page/panel, with the browser header/footer showing print date, page title, detail-page URL, and page numbers.

## Inputs

Confirm or infer:

- `company_name`: applicant/company name.
- `patent_number`: patent/application number when known; otherwise search by company and select the target record.
- `sections`: default to `申请信息`, `费用信息`, `发文信息`, `专利权质押`, and `实施许可备案`; include other visible panels if the user requests them or they contain material evidence.
- `output_root`: default to `~/Downloads/<company_name>`.
- `batch_size`: when many records are involved, first run a small pilot (default: 2 patents) end-to-end before running the full batch.

Never store credentials, OTPs, cookies, or private account details in the skill output or summaries. If CNIPA login is required, ask the user to complete login in their browser.

## Workflow

1. Open the logged-in CNIPA query site in Chrome using the user's existing Chrome session:
   - `https://cpquery.cponline.cnipa.gov.cn/chinesepatent/index`
   - If redirected to the unified identity login page, pause for user login.
   - Use the Chrome browser-control skill and its browser-client / CDP capabilities when available, because CNIPA is session-dependent.

2. Find the target case:
   - If a direct `patent_number` search returns no result, do not stop. CNIPA's exact application-number and full-company-name searches can be inconsistent.
   - Search by a stable applicant keyword (for example, a distinctive short name extracted from `company_name`) and then filter the returned records by exact applicant/company text.
   - For batch work, collect or reuse the applicant search JSON/list results, then select the target records by `zhuanlisqh` and applicant text.
   - On the detail page, verify the applicant/company and patent/application number from the visible `申请信息` fields before exporting.

3. Prefer scripted export rather than manual print dialogs:
   - Use `scripts/cnipa-evidence-pdf-automation.js` as the implementation template.
   - In the CNIPA list page, identify the Vue list component that has `routerPush(record)` and `dataList`.
   - Capture the detail-page URL by temporarily intercepting `window.open`, calling `routerPush(record)`, and restoring `window.open`.
   - Navigate the controlled tab to the captured `/detail/index?...` URL.
   - For each section, select the tree item/panel, then call Chrome DevTools Protocol `Page.printToPDF`.
   - Set `displayHeaderFooter: true` so the resulting PDF includes Chrome-style print date, page title, URL, and page numbers.
   - Use A4 portrait defaults unless the user requests otherwise:
     - `paperWidth: 8.27`, `paperHeight: 11.69`
     - `marginTop: 0.55`, `marginBottom: 0.55`, `marginLeft: 0.35`, `marginRight: 0.35`
     - `printBackground: true`
   - Use a print cleanup style only to hide non-evidence floating UI such as Quasar drawer/backdrop/notification overlays and page-sticky buttons; do not edit CNIPA content.

4. Export each target panel:
   - Expand or select one target panel at a time.
   - Use scripted Chrome PDF printing when possible.
   - If automation is unavailable, use the browser print command from the page context or Chrome menu, and in Chrome print preview choose `保存` / Save as PDF. Ensure Chrome's header/footer option is enabled so the PDF shows date and URL.
   - Save each PDF as `中国及多国专利审查信息查询-<section>.pdf`.
   - For the first save, create or select `~/Downloads/<company_name>` as the destination.
   - If a panel has no substantive records but is part of the requested evidence set, still export the panel as displayed unless the user instructs otherwise. This preserves negative evidence such as no pledge/license information.

5. Archive by case:
   - After exporting all target PDFs, create a case folder:
     `<output_root>/<company_name>-<patent_number>/`
   - Move the exported PDFs into that folder.
   - Prefer shell/Finder file operations for deterministic moves; use Computer Use only when the UI state itself must be verified.
   - For batch work, also write a `运行日志.json` at the batch root with patent number, detail URL, exported sections, file paths, byte sizes, and any unavailable panels.

6. Validate:
   - Confirm the final folder exists.
   - Confirm it contains one PDF per requested section.
   - Confirm filenames are intelligible and no temporary or duplicate failed-save files are included.
   - Run `pdfinfo` or equivalent on generated PDFs to confirm they are readable, unencrypted PDFs and to capture page counts.
   - Render at least one representative PDF page with Poppler (`pdftoppm`) when layout matters. Check that the header/footer includes date, title, URL, and page numbers.
   - Report the final folder path and list the exported PDFs.

## Practical Notes

- The CNIPA page is session-dependent. Use the user's existing browser session when login state matters.
- Do not save or print `ACCESS_TOKEN`, cookies, OTPs, account details, or raw authentication headers. It is acceptable for the script to read the current page's token at runtime solely to perform same-session CNIPA actions, but it must not write those secrets to disk or summaries.
- CNIPA detail links use an encrypted `zhuanlisqh` query value generated by the front-end. Do not guess this encryption. Capture the URL through the page's own `routerPush(record)` logic.
- The print-save panel may default to `中国及多国专利审查信息查询`; append `-<section>` before saving.
- If a panel is empty or unavailable, do not fabricate a PDF label. Note that the section was unavailable and continue with the rest.
- If multiple patents are involved, repeat the workflow per patent number and keep each case in a separate `<company_name>-<patent_number>` folder.
- For legal due diligence work, preserve source fidelity: export the page as displayed and avoid editing the PDF contents after save.
- Before running a large batch, run a pilot of 1-2 patents across all requested sections and visually inspect a sample PDF. Only then scale to the full set.
