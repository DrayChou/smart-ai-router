@echo off
REM Windows批处理脚本 - 运行本地CI检查
REM Windows batch script - run local CI checks

echo [START] 启动本地CI检查...
echo.

cd /d "%~dp0\.."

REM 运行Python脚本
python scripts\local_ci_check.py

REM 保持窗口打开以查看结果
if errorlevel 1 (
    echo.
    echo [FAIL] 检查失败，请修复问题后重试
    pause
) else (
    echo.
    echo [PASS] 所有检查通过！
    pause
)