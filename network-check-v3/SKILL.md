---
name: network-check-v3
description: Use this skill when the user asks Codex to perform Chinese enterprise network due diligence, company risk checks, credit checks, regulatory penalty searches, enforcement record checks, tax dishonesty checks, Credit China report downloads, customs credit checks, SAFE foreign-exchange penalty checks, CSRC dishonesty searches, SAMR or Shenzhen AMR administrative penalty searches, or Baidu risk keyword searches. This skill should trigger for Chinese legal due diligence workflows, IPO/legal memo background checks, contract counterparty risk checks, and requests like "网络核查", "主体核查", "企业信用核查", "风险检索", "行政处罚查询", "失信记录查询", or "帮我查一下这家公司".
---

# Network Check V3

This skill runs a modular Chinese enterprise network-check suite and saves PDF evidence files for legal due diligence and risk-review work.

## When To Use

Use this skill for Chinese company or person risk checks across public web platforms, especially when the user needs source PDFs that can support a legal memo, transaction diligence report, litigation background check, IPO project check, or counterparty review.

Do not treat the generated PDFs as a legal conclusion. They are source evidence snapshots. After running checks, summarize what was searched, what files were generated, and which platforms failed or need manual verification.

## Setup

From this directory:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

If the task is being run in Codex Desktop and a platform has CAPTCHA or bot checks, prefer headful mode so the user can intervene in the browser window:

```bash
python3 run_check.py "深圳市精诚达电路科技股份有限公司" --platform all --output-dir ./outputs
```

For unattended smoke tests or platforms that work without manual CAPTCHA, use headless mode:

```bash
python3 run_check.py "深圳市精诚达电路科技股份有限公司" --platform baidu --headless --output-dir ./outputs
```

## Main Command

```bash
python3 run_check.py "<company name or search term>" [--platform PLATFORM] [--headless] [--uscc USCC] [--id-num ID_NUM] [--output-dir DIR]
```

Options:

- `--platform`: one platform key or `all`. Default is `all`.
- `--headless`: run Chromium without a visible browser. Default is headful because several official sites use CAPTCHA.
- `--uscc`: unified social credit code. Required for SAFE checks if the first argument is a Chinese company name.
- `--id-num`: identity or certificate number for platforms that require it, such as CSRC.
- `--output-dir`: directory for generated PDF reports. Default is `~/Downloads`.
- `--list-platforms`: list supported platform keys.

## Supported Platforms

- `customs`: China Customs enterprise credit information.
- `baidu`: Baidu keyword searches for administrative penalties, illegal conduct, former CSRC staff shareholding, and sudden pre-IPO shareholding.
- `chinatax`: major tax violation dishonesty records.
- `creditchina`: Credit China search and credit report download.
- `samr`: SAMR administrative penalty decision disclosure site.
- `safe`: SAFE foreign-exchange administrative penalty information. Requires a unified social credit code.
- `csrc`: CSRC securities and futures market dishonesty record platform. Provide `--id-num` when available.
- `procuratorate`: 12309 China Procuratorate public search.
- `court`: China Court enforcement information public platform.
- `sz-amr`: Shenzhen AMR administrative penalty disclosure.

## Recommended Legal Workflow

1. Confirm the exact subject name and, where possible, unified social credit code.
2. Run the relevant platforms first instead of always running `all` when the user asks for a narrow check.
3. Use headful mode for platforms with CAPTCHA or download verification.
4. Save outputs to a task-specific folder using `--output-dir`.
5. Report results by platform: success, no record shown, failed, skipped, or manual verification required.
6. Do not state that a company has no risk record unless the platform search succeeded and the generated PDF shows that result.

## Platform Notes

- SAFE cannot search by company name. If `--platform safe` is requested without a USCC, ask the user for the USCC or mark SAFE as not checked.
- CSRC may require a complete identity/certificate number. If unavailable, report the limitation instead of relying on placeholder values.
- Customs and court checks often require manual CAPTCHA handling.
- Credit China downloads may require verification; if a download does not complete, distinguish page-level search results from a locally saved PDF.
- Several official sites change selectors frequently. If a module fails, inspect the saved screenshot/debug output and re-run that platform only.

## Safety And Evidence Handling

The scripts open public web pages and write generated PDFs to the output directory. They do not request credentials and should not access cookies, browser profiles, SSH keys, or cloud credentials.

Keep generated PDF evidence in the matter workspace. Do not reuse downloaded reports across unrelated clients or matters.
