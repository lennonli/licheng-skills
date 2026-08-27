#!/usr/bin/env bash
# company-monitor 一键初始化: 建运行目录 + 拷贝配置模板 + 脚本自检
set -e
cd "$(dirname "$0")"
mkdir -p state outbox/social_raw summaries raw config
for f in targets.yaml system.json mail.json; do
  src="config/$(echo $f | sed 's/yaml/example.yaml/;s/json/example.json/')"
  [ -f "config/$f" ] || { [ -f "$src" ] && cp "$src" "config/$f" && echo "已生成 config/$f (请填写)"; }
done
echo "--- 脚本语法自检 ---"
for py in tools/*.py; do python3 -m py_compile "$py" && echo "OK $py"; done
echo "--- 依赖检查 ---"
python3 -c "import playwright" 2>/dev/null && echo "OK playwright" || echo "缺 playwright: python3 -m pip install -r requirements.txt"
command -v pandoc >/dev/null && echo "OK pandoc" || echo "缺 pandoc"
command -v rsync  >/dev/null && echo "OK rsync"  || echo "缺 rsync"
ls /Applications/Google\ Chrome.app >/dev/null 2>&1 && echo "OK Chrome" || echo "缺系统 Chrome"
echo "完成。下一步: 填写 config/targets.yaml / system.json / mail.json, 然后按 README 第 3 步做 Baseline 首跑。"
