#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""监控日报邮件发送（经 agently-cli / QQ邮箱 Agent 通道, 用户已预先授权每日发送）。
用法: python3 send_daily_email.py <日报.md> [简报文本]
收件人读 config/mail.json ({"to": "..."}), 默认发授权邮箱自身。
自动完成两阶段确认: 先发取得 confirmation_token, 再带 token 正式发送。"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = BASE / "config" / "mail.json"
SYS = BASE / "config" / "system.json"
ATT_NAME_FMT = "公司舆情与法律风险监控日报-{date}"


def get_default_to():
    """默认收件人: config/system.json 的 default_to(发件授权邮箱自身), 未配置则要求 mail.json 必须存在。"""
    if SYS.exists():
        try:
            v = json.loads(SYS.read_text(encoding="utf-8")).get("default_to", "")
            if v:
                return v
        except Exception:
            pass
    return None


def run_send(args, cwd):
    r = subprocess.run(["agently-cli", "message", "+send"] + args,
                       capture_output=True, text=True, cwd=cwd, timeout=120)
    out = r.stdout.strip()
    try:
        env = json.loads(out)
    except json.JSONDecodeError:
        print(f"ERROR: agently-cli 输出无法解析(exit {r.returncode}): {out[:300]} {r.stderr[:200]}")
        sys.exit(1)
    return r.returncode, env


def main():
    if len(sys.argv) < 2:
        print("用法: send_daily_email.py <日报.md> [简报文本] [--subject 自定义主题]")
        return 2
    md = Path(sys.argv[1]).resolve()
    if not md.exists():
        print(f"ERROR: 找不到 {md}")
        return 1
    pdf = md.with_suffix(".pdf")
    pos = [a for a in sys.argv[2:] if not a.startswith("--")]
    brief = pos[0] if pos else ""
    subject = (sys.argv[sys.argv.index("--subject") + 1]
               if "--subject" in sys.argv else None)
    to = get_default_to()
    if CFG.exists():
        try:
            to = json.loads(CFG.read_text(encoding="utf-8")).get("to") or to
        except Exception:
            pass
    if not to:
        print("ERROR: 未配置收件人。请在 config/mail.json 填 {\"to\": \"<邮箱>\"}, "
              "或在 config/system.json 填 default_to(发件授权邮箱自身)。")
        return 1
    date_m = re.search(r"\d{4}-\d{2}-\d{2}", md.stem)
    date_part = date_m.group(0) if date_m else md.stem
    if subject is None:
        subject = f"公司舆情与法律风险监控日报（{date_part}）"
    body = (f"李成律师您好：\n\n{date_part} 监控日报见附件（PDF 版）。\n{brief}\n\n"
            f"原始 PDF 与历史日报已同步至 Google Drive「公司舆情监控」文件夹。"
            f"本邮件由每日 08:30 自动任务发送。本报告为线索发现工具产出，商业数据源信息未经官方核验，"
            f"对外使用前须回官方来源二次核验。")

    # 附件按对外命名生成副本; agently-cli 要求相对路径, 副本临时放 md 同目录, 发送后清理
    att_path = None
    if pdf.exists():
        base_name = subject if subject else ATT_NAME_FMT.format(date=date_part)
        att_name = base_name + pdf.suffix
        att_path = md.parent / att_name
        shutil.copyfile(pdf, att_path)
        args = ["--to", to, "--subject", subject, "--body", body,
                "--attachment", "./" + att_name]
    else:
        args = ["--to", to, "--subject", subject, "--body", body]
    # 阶段1: 取 confirmation_token
    code, env = run_send(args, cwd=md.parent)
    if env.get("ok") and env.get("data", {}).get("confirmation_required"):
        ctk = env["data"]["confirmation_token"]
        # 阶段2: 用户已预先授权本日报的每日发送, 直接确认
        code, env = run_send(args + ["--confirmation-token", ctk], cwd=md.parent)
    if not env.get("ok"):
        err = env.get("error", {})
        print(f"ERROR: 邮件发送失败 [{err.get('type')}]: {err.get('message')}")
        if err.get("type") == "invalid_grant":
            print("NOTE: 邮箱授权已失效, 需在对话中重新执行 agently-cli auth login 授权")
        return 1
    if att_path is not None:
        att_path.unlink(missing_ok=True)  # 发送后清理副本, 避免被 Drive 同步
    if env.get("data", {}).get("queued"):
        att = f", 附件 {att_name}" if att_path else ""
        print(f"OK: 已发送至 {to}{att}")
        return 0
    print(f"WARN: 未预期的返回: {json.dumps(env, ensure_ascii=False)[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
