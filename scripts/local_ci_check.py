#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地CI检查脚本 - 在推送前本地运行与GitHub CI相同的检查
Local CI verification script - run the same checks as GitHub CI before pushing
"""

import subprocess
import sys
import time
from pathlib import Path

# 设置Windows控制台编码
if sys.platform == "win32":
    import os

    os.system("chcp 65001 >nul 2>&1")


class Colors:
    """终端颜色"""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class LocalCIChecker:
    """本地CI检查器"""

    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.parent
        self.failed_checks = []
        self.passed_checks = []

    def run_command(self, cmd: str, description: str) -> bool:
        """运行命令并返回是否成功"""
        print(f"\n{Colors.BLUE}[CHECK] {description}{Colors.RESET}")
        print(f"{Colors.YELLOW}Command: {cmd}{Colors.RESET}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,  # 5分钟超时
            )

            if result.returncode == 0:
                print(f"{Colors.GREEN}[PASS] {description} - 通过{Colors.RESET}")
                self.passed_checks.append(description)
                if result.stdout and result.stdout.strip():
                    print(f"输出: {result.stdout.strip()}")
                return True
            else:
                print(f"{Colors.RED}[FAIL] {description} - 失败{Colors.RESET}")
                self.failed_checks.append(description)
                if result.stdout and result.stdout.strip():
                    print(f"标准输出:\n{result.stdout}")
                if result.stderr and result.stderr.strip():
                    print(f"错误输出:\n{result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"{Colors.RED}[FAIL] {description} - 超时{Colors.RESET}")
            self.failed_checks.append(f"{description} (超时)")
            return False
        except Exception as e:
            print(f"{Colors.RED}[FAIL] {description} - 异常: {e}{Colors.RESET}")
            self.failed_checks.append(f"{description} (异常)")
            return False

    def check_dependencies(self) -> bool:
        """检查依赖是否安装"""
        print(f"{Colors.BOLD}[DEPS] 检查依赖环境{Colors.RESET}")

        # 检查uv是否可用
        uv_available = self.run_command("uv --version", "UV包管理器")

        if uv_available:
            # 检查虚拟环境是否存在
            venv_path = self.project_root / ".venv"
            if venv_path.exists():
                print(
                    f"{Colors.GREEN}[PASS] 虚拟环境已存在，跳过依赖安装{Colors.RESET}"
                )
                return True
            else:
                # 安装依赖
                return self.run_command("uv sync", "安装项目依赖")
        else:
            print(f"{Colors.YELLOW}[WARN] UV不可用，尝试使用系统Python{Colors.RESET}")
            return True

    def run_code_quality_checks(self) -> bool:
        """运行代码质量检查 - 与CI中的code-quality job相同"""
        print(f"\n{Colors.BOLD}[QUALITY] 代码质量检查 (与GitHub CI相同){Colors.RESET}")

        # 检查虚拟环境是否正常工作
        venv_test = self.run_command("uv run python --version", "虚拟环境测试")

        if not venv_test:
            print(f"{Colors.YELLOW}[WARN] 虚拟环境有问题，尝试系统工具{Colors.RESET}")
            # 使用系统工具作为备选
            checks = [
                ("black --check --diff .", "Black代码格式化检查 (系统)"),
                ("isort --check-only --diff .", "isort导入排序检查 (系统)"),
                ("ruff check . --exclude scripts/", "Ruff代码质量检查 (系统)"),
                (
                    "mypy . --ignore-missing-imports --no-strict-optional",
                    "MyPy类型检查 (系统)",
                ),
            ]
        else:
            # 使用uv工具
            checks = [
                ("uv run black --check --diff .", "Black代码格式化检查"),
                ("uv run isort --check-only --diff .", "isort导入排序检查"),
                ("uv run ruff check . --exclude scripts/", "Ruff代码质量检查"),
                (
                    "uv run mypy . --ignore-missing-imports --no-strict-optional",
                    "MyPy类型检查",
                ),
            ]

        all_passed = True
        for cmd, desc in checks:
            if not self.run_command(cmd, desc):
                all_passed = False

        return all_passed

    def run_basic_tests(self) -> bool:
        """运行基础功能测试"""
        print(f"\n{Colors.BOLD}[TEST] 基础功能测试{Colors.RESET}")

        # 测试核心模块导入
        test_import_cmd = '''python -c "
import sys
try:
    from core.yaml_config import YAMLConfigLoader
    from core.json_router import JSONRouter
    from api.admin import create_admin_router
    print('核心模块导入成功')
except Exception as e:
    print(f'导入失败: {e}')
    sys.exit(1)
"'''

        return self.run_command(test_import_cmd, "核心模块导入测试")

    def print_summary(self) -> None:
        """打印检查结果摘要"""
        print(f"\n{Colors.BOLD}[SUMMARY] 本地CI检查结果摘要{Colors.RESET}")
        print("=" * 50)

        if self.passed_checks:
            print(
                f"{Colors.GREEN}[PASS] 通过的检查 ({len(self.passed_checks)}项):{Colors.RESET}"
            )
            for check in self.passed_checks:
                print(f"  - {check}")

        if self.failed_checks:
            print(
                f"\n{Colors.RED}[FAIL] 失败的检查 ({len(self.failed_checks)}项):{Colors.RESET}"
            )
            for check in self.failed_checks:
                print(f"  - {check}")

            print(f"\n{Colors.YELLOW}[TIPS] 修复建议:{Colors.RESET}")
            if any("Black" in check for check in self.failed_checks):
                print("  - 运行: uv run black . 自动修复格式问题")
            if any("isort" in check for check in self.failed_checks):
                print("  - 运行: uv run isort . 自动修复导入排序")
            if any("Ruff" in check for check in self.failed_checks):
                print("  - 运行: uv run ruff check . --fix 自动修复部分问题")
        else:
            print(
                f"\n{Colors.GREEN}[SUCCESS] 所有检查通过！可以安全推送到GitHub{Colors.RESET}"
            )

        print("\n" + "=" * 50)

    def run_all_checks(self) -> bool:
        """运行所有检查"""
        start_time = time.time()

        print(f"{Colors.BOLD}[START] 开始本地CI检查...{Colors.RESET}")
        print(f"项目路径: {self.project_root}")

        # 检查依赖
        if not self.check_dependencies():
            print(f"{Colors.RED}[FAIL] 依赖检查失败，停止后续检查{Colors.RESET}")
            return False

        # 运行代码质量检查
        quality_passed = self.run_code_quality_checks()

        # 运行基础测试
        tests_passed = self.run_basic_tests()

        # 打印摘要
        self.print_summary()

        elapsed = time.time() - start_time
        print(f"总耗时: {elapsed:.1f}秒")

        return len(self.failed_checks) == 0


def main() -> None:
    """主函数"""
    checker = LocalCIChecker()

    if checker.run_all_checks():
        print(
            f"\n{Colors.GREEN}{Colors.BOLD}[SUCCESS] 本地CI检查全部通过！{Colors.RESET}"
        )
        print(f"{Colors.GREEN}[READY] 可以安全推送到GitHub进行正式CI检查{Colors.RESET}")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}[ERROR] 本地CI检查发现问题{Colors.RESET}")
        print(f"{Colors.RED}[FIX] 请修复上述问题后再推送{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
