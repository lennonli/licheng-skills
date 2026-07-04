import asyncio
import os
import argparse
import datetime
import sys
import re

# Add the modules directory to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(BASE_DIR, "modules")
sys.path.append(MODULES_DIR)

PLATFORMS = {
    "chinatax": {"script": "chinatax_search.py", "mode_flag": "headful"},
    "court": {"script": "court_search.py", "mode_flag": "headless", "supports_id_num": True},
    "creditchina": {"script": "creditchina_search.py", "mode_flag": "headful"},
    "csrc": {"script": "csrc_search.py", "mode_flag": "headful", "supports_id_num": True},
    "customs": {"script": "customs_search.py", "mode_flag": "headless"},
    "procuratorate": {"script": "procuratorate_search.py", "mode_flag": "headful"},
    "safe": {"script": "safe_search.py", "mode_flag": "headful", "requires_uscc": True},
    "samr": {"script": "samr_search.py", "mode_flag": "headful"},
    "sz-amr": {"script": "sz_amr_search.py", "mode_flag": "headful"},
    "baidu": {"script": "baidu_search.py", "mode_flag": "headless"},
    "sse": {"script": "sse_search.py", "mode_flag": "headless"},
}

def looks_like_uscc(value):
    return bool(value and re.fullmatch(r"[0-9A-Z]{18}", value.strip().upper()))

def has_chinese(value):
    return bool(value and re.search(r"[\u4e00-\u9fff]", value))

def build_command(platform_name, company_name, headless, uscc=None, id_num=None):
    platform = PLATFORMS[platform_name]
    script_file = os.path.join(MODULES_DIR, platform["script"])
    if not os.path.exists(script_file):
        raise FileNotFoundError(f"Script for '{platform_name}' not found at {script_file}.")

    if platform.get("requires_uscc"):
        code = uscc or (company_name if looks_like_uscc(company_name) else None)
        if not code:
            raise ValueError(
                "SAFE requires a unified social credit code. "
                "Pass --uscc when running safe/all checks for a Chinese company name."
            )
        cmd = [sys.executable, script_file, code, company_name]
    else:
        cmd = [sys.executable, script_file, company_name]
        if platform.get("supports_id_num") and id_num:
            cmd.append(id_num)

    mode_flag = platform["mode_flag"]
    if headless and mode_flag == "headless":
        cmd.append("--headless")
    elif not headless and mode_flag == "headful":
        cmd.append("--headful")

    return cmd

async def run_platform(platform_name, company_name, headless, uscc=None, id_num=None, output_dir=None):
    if platform_name not in PLATFORMS:
        print(f"Error: Platform '{platform_name}' not recognized.")
        return False

    try:
        cmd = build_command(platform_name, company_name, headless, uscc=uscc, id_num=id_num)
    except ValueError as exc:
        print(f"Skipping {platform_name}: {exc}")
        return True
    except Exception as exc:
        print(f"Error preparing {platform_name}: {exc}")
        return False

    print(f"\n>>> Starting Network Check: {platform_name.upper()} for '{company_name}' <<<")

    env = os.environ.copy()
    if output_dir:
        output_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(output_dir, exist_ok=True)
        env["NETWORK_CHECK_OUTPUT_DIR"] = output_dir

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=BASE_DIR,
        env=env,
    )

    stdout, stderr = await process.communicate()

    if stdout:
        print(stdout.decode(errors="replace"))
    if stderr:
        print(f"Errors/Warnings from {platform_name}:\n{stderr.decode(errors='replace')}")

    ok = process.returncode == 0
    status = "Finished" if ok else f"Finished with exit code {process.returncode}"
    print(f">>> {status} {platform_name.upper()} <<<\n")
    return ok

async def main():
    parser = argparse.ArgumentParser(description="Network Check Unified Master Skill (V3)")
    parser.add_argument("company_name", nargs="?", help="The company name to search for")
    parser.add_argument("--platform", choices=list(PLATFORMS.keys()) + ["all"], default="all",
                        help="Select a specific platform or 'all' (default)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--uscc", help="Unified social credit code. Required for SAFE checks when company_name is not a USCC.")
    parser.add_argument("--id-num", help="Identity/certificate number for platforms that require one, such as CSRC.")
    parser.add_argument("--output-dir", default=os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"),
                        help="Directory for generated PDFs (default: ~/Downloads)")
    parser.add_argument("--list-platforms", action="store_true", help="List supported platform keys and exit")
    args = parser.parse_args()

    if args.list_platforms:
        print("Supported platforms:")
        for key in PLATFORMS:
            print(f"- {key}")
        return

    if not args.company_name:
        parser.error("company_name is required unless --list-platforms is used")

    platforms_to_run = []
    if args.platform == "all":
        platforms_to_run = list(PLATFORMS.keys())
    else:
        platforms_to_run = [args.platform]

    print(f"====================================================")
    print(f" Unified Network Check System (V3)")
    print(f" Company: {args.company_name}")
    print(f" Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Browser Mode: {'headless' if args.headless else 'headful'}")
    print(f" Output Dir: {os.path.abspath(os.path.expanduser(args.output_dir))}")
    print(f"====================================================")

    failures = []
    for platform in platforms_to_run:
        ok = await run_platform(
            platform,
            args.company_name,
            args.headless,
            uscc=args.uscc,
            id_num=args.id_num,
            output_dir=args.output_dir,
        )
        if not ok:
            failures.append(platform)

    print("====================================================")
    if failures:
        print(f" Completed with failures: {', '.join(failures)}")
        sys.exit(1)
    print(" All selected checks completed.")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(main())
