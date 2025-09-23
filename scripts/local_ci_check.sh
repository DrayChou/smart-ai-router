#!/bin/bash
# Linux/macOS脚本 - 运行本地CI检查
# Linux/macOS script - run local CI checks

set -e  # 遇到错误时退出

echo "[START] 启动本地CI检查..."
echo

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 运行Python脚本
python scripts/local_ci_check.py

# 检查退出码
if [ $? -eq 0 ]; then
    echo
    echo "[PASS] 所有检查通过！"
else
    echo
    echo "[FAIL] 检查失败，请修复问题后重试"
    exit 1
fi