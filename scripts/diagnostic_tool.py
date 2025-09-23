#!/usr/bin/env python3
"""
Smart AI Router 诊断工具
自动检测和诊断系统常见问题
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置编码
import os

if os.name == "nt":  # Windows
    import locale

    try:
        # 尝试设置UTF-8编码
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except:
        # 如果失败，则使用无emoji版本
        pass

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class DiagnosticTool:
    """系统诊断工具"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.issues_found = []
        self.warnings = []
        self.info = []

    def add_issue(
        self, category: str, title: str, description: str, solution: str = ""
    ):
        """添加问题"""
        self.issues_found.append(
            {
                "category": category,
                "title": title,
                "description": description,
                "solution": solution,
                "severity": "error",
            }
        )

    def add_warning(
        self, category: str, title: str, description: str, suggestion: str = ""
    ):
        """添加警告"""
        self.warnings.append(
            {
                "category": category,
                "title": title,
                "description": description,
                "suggestion": suggestion,
                "severity": "warning",
            }
        )

    def add_info(self, category: str, title: str, description: str):
        """添加信息"""
        self.info.append(
            {
                "category": category,
                "title": title,
                "description": description,
                "severity": "info",
            }
        )

    def run_command(self, command: str, timeout: int = 30) -> tuple[bool, str, str]:
        """运行系统命令"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                timeout=timeout,
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def check_file_exists(self, file_path: Path) -> bool:
        """检查文件是否存在"""
        return (self.project_root / file_path).exists()

    def check_environment(self):
        """检查环境配置"""
        print("🔍 检查环境配置...")

        # 检查Python版本
        success, stdout, stderr = self.run_command("python --version")
        if success:
            python_version = stdout.strip()
            self.add_info("environment", "Python版本", python_version)

            # 检查Python版本是否符合要求（3.8+）
            version_parts = python_version.split()[1].split(".")
            major, minor = int(version_parts[0]), int(version_parts[1])
            if major < 3 or (major == 3 and minor < 8):
                self.add_issue(
                    "environment",
                    "Python版本过低",
                    f"当前Python版本: {python_version}，要求3.8+",
                    "升级Python到3.8或更高版本",
                )
        else:
            self.add_issue(
                "environment",
                "Python不可用",
                "无法执行python命令",
                "检查Python安装和PATH配置",
            )

        # 检查uv
        success, stdout, stderr = self.run_command("uv --version")
        if success:
            self.add_info("environment", "uv版本", stdout.strip())
        else:
            self.add_warning(
                "environment",
                "uv不可用",
                "推荐使用uv进行依赖管理",
                "安装uv: pip install uv",
            )

        # 检查虚拟环境
        venv_path = self.project_root / ".venv"
        if venv_path.exists():
            self.add_info("environment", "虚拟环境", "发现.venv目录")
        else:
            self.add_warning(
                "environment",
                "虚拟环境不存在",
                "未发现.venv目录",
                "运行 'uv sync' 创建虚拟环境",
            )

    def check_configuration(self):
        """检查配置文件"""
        print("📋 检查配置文件...")

        # 检查主配置文件
        config_file = Path("config/router_config.yaml")
        if not self.check_file_exists(config_file):
            self.add_issue(
                "configuration",
                "配置文件缺失",
                "config/router_config.yaml 不存在",
                "复制 config/router_config.yaml.template 到 config/router_config.yaml",
            )
            return

        # 验证YAML语法
        try:
            with open(self.project_root / config_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            self.add_info("configuration", "YAML语法", "配置文件语法正确")
        except yaml.YAMLError as e:
            self.add_issue(
                "configuration",
                "YAML语法错误",
                f"配置文件语法错误: {e}",
                "修复YAML语法错误",
            )
            return
        except Exception as e:
            self.add_issue(
                "configuration",
                "配置文件读取失败",
                f"无法读取配置文件: {e}",
                "检查文件权限和编码",
            )
            return

        # 检查必需的配置项
        required_sections = [
            "system",
            "server",
            "providers",
            "channels",
            "routing",
            "tasks",
        ]
        for section in required_sections:
            if section not in config_data:
                self.add_issue(
                    "configuration",
                    f"缺少配置节 {section}",
                    f"配置文件中缺少 {section} 配置节",
                    f"添加 {section} 配置节",
                )

        # 检查渠道配置
        if "channels" in config_data:
            channels = config_data["channels"]
            if not channels:
                self.add_warning(
                    "configuration",
                    "没有配置渠道",
                    "channels列表为空",
                    "添加至少一个渠道配置",
                )
            else:
                enabled_channels = [ch for ch in channels if ch.get("enabled", False)]
                self.add_info(
                    "configuration",
                    "渠道统计",
                    f"总计 {len(channels)} 个渠道，{len(enabled_channels)} 个启用",
                )

                # 检查API密钥
                channels_without_keys = []
                for channel in enabled_channels:
                    if not channel.get("api_key"):
                        channels_without_keys.append(channel.get("id", "unknown"))

                if channels_without_keys:
                    self.add_warning(
                        "configuration",
                        "渠道缺少API密钥",
                        f"以下启用渠道缺少API密钥: {', '.join(channels_without_keys)}",
                        "为启用的渠道添加有效的API密钥",
                    )

        # 检查环境变量文件
        env_file = Path(".env")
        if not self.check_file_exists(env_file):
            self.add_warning(
                "configuration",
                "环境变量文件缺失",
                ".env 文件不存在",
                "复制 .env.example 到 .env 并配置必要的环境变量",
            )

    def check_dependencies(self):
        """检查依赖项"""
        print("📦 检查依赖项...")

        # 检查requirements文件
        pyproject_file = Path("pyproject.toml")
        if self.check_file_exists(pyproject_file):
            self.add_info("dependencies", "项目配置", "发现 pyproject.toml")
        else:
            self.add_warning(
                "dependencies",
                "项目配置缺失",
                "pyproject.toml 不存在",
                "检查项目完整性",
            )

        # 检查核心依赖
        core_imports = [
            ("fastapi", "FastAPI web框架"),
            ("httpx", "HTTP客户端"),
            ("yaml", "YAML解析"),
            ("pydantic", "数据验证"),
            ("aiofiles", "异步文件操作"),
            ("tiktoken", "Token计数"),
        ]

        for module, description in core_imports:
            success, _, _ = self.run_command(f'python -c "import {module}"')
            if success:
                self.add_info("dependencies", f"{module}", f"{description} - 已安装")
            else:
                self.add_issue(
                    "dependencies",
                    f"缺少依赖 {module}",
                    f"{description} 未安装",
                    f"运行 'uv sync' 安装依赖",
                )

    def check_network_connectivity(self):
        """检查网络连接"""
        print("🌐 检查网络连接...")

        # 检查主要API服务
        endpoints = [
            ("api.openai.com", "OpenAI API"),
            ("api.anthropic.com", "Anthropic API"),
            ("api.siliconflow.cn", "SiliconFlow API"),
        ]

        for host, service in endpoints:
            success, _, _ = self.run_command(f"ping -c 1 {host}", timeout=10)
            if success:
                self.add_info("network", f"{service}", f"{host} 可达")
            else:
                self.add_warning(
                    "network",
                    f"{service} 不可达",
                    f"无法ping通 {host}",
                    "检查网络连接或防火墙设置",
                )

        # 检查HTTPS连接
        success, _, _ = self.run_command(
            "curl -s --max-time 10 -I https://api.openai.com/v1/models", timeout=15
        )
        if success:
            self.add_info("network", "HTTPS连接", "OpenAI HTTPS连接正常")
        else:
            self.add_warning(
                "network",
                "HTTPS连接问题",
                "无法建立HTTPS连接到OpenAI",
                "检查网络配置或代理设置",
            )

    async def check_service_health(self):
        """检查服务健康状态"""
        print("🏥 检查服务健康状态...")

        try:
            # 尝试导入核心模块
            from core.json_router import JSONRouter
            from core.yaml_config import get_yaml_config_loader

            # 加载配置
            config_loader = get_yaml_config_loader()
            self.add_info("service", "配置加载", "配置加载成功")

            # 检查路由器
            router = JSONRouter(config_loader)
            self.add_info("service", "路由器初始化", "路由器初始化成功")

            # 检查可用标签
            try:
                available_tags = router.get_all_available_tags()
                self.add_info(
                    "service",
                    "可用标签",
                    f"发现 {len(available_tags)} 个标签: {', '.join(sorted(available_tags)[:10])}",
                )
            except Exception as e:
                self.add_warning(
                    "service",
                    "标签系统问题",
                    f"无法获取可用标签: {e}",
                    "检查模型发现和缓存状态",
                )

        except ImportError as e:
            self.add_issue(
                "service",
                "模块导入失败",
                f"无法导入核心模块: {e}",
                "检查依赖安装和Python路径",
            )
        except Exception as e:
            self.add_issue(
                "service",
                "服务初始化失败",
                f"服务初始化错误: {e}",
                "检查配置文件和日志",
            )

    def check_cache_and_logs(self):
        """检查缓存和日志"""
        print("📁 检查缓存和日志...")

        # 检查缓存目录
        cache_dir = Path("cache")
        if self.check_file_exists(cache_dir):
            cache_files = list((self.project_root / cache_dir).glob("*.json"))
            self.add_info("cache", "缓存目录", f"发现 {len(cache_files)} 个缓存文件")

            # 检查关键缓存文件
            key_cache_files = [
                ("discovered_models.json", "模型发现缓存"),
                ("smart_cache.json", "智能缓存"),
                ("api_key_validation.json", "API密钥验证缓存"),
            ]

            for filename, description in key_cache_files:
                cache_file = cache_dir / filename
                if self.check_file_exists(cache_file):
                    try:
                        with open(
                            self.project_root / cache_file, "r", encoding="utf-8"
                        ) as f:
                            data = json.load(f)
                        self.add_info(
                            "cache", description, f"缓存有效，包含 {len(data)} 个条目"
                        )
                    except Exception as e:
                        self.add_warning(
                            "cache",
                            f"{description}损坏",
                            f"缓存文件读取失败: {e}",
                            "删除缓存文件以重新生成",
                        )
                else:
                    self.add_info(
                        "cache", description, "缓存文件不存在（正常，首次运行会生成）"
                    )
        else:
            self.add_info("cache", "缓存目录", "cache目录不存在（首次运行会创建）")

        # 检查日志目录
        logs_dir = Path("logs")
        if self.check_file_exists(logs_dir):
            log_files = list((self.project_root / logs_dir).glob("*.log"))
            self.add_info("logs", "日志目录", f"发现 {len(log_files)} 个日志文件")

            # 检查主日志文件
            main_log = logs_dir / "smart-ai-router.log"
            if self.check_file_exists(main_log):
                # 检查最近的错误
                success, stdout, _ = self.run_command(
                    f"tail -50 {main_log} | grep -i error | wc -l"
                )
                if success:
                    error_count = stdout.strip()
                    if int(error_count) > 0:
                        self.add_warning(
                            "logs",
                            "发现最近错误",
                            f"最近50行日志中有 {error_count} 个错误",
                            "查看日志文件了解具体错误信息",
                        )
                    else:
                        self.add_info("logs", "日志状态", "最近没有错误记录")
        else:
            self.add_info("logs", "日志目录", "logs目录不存在（首次运行会创建）")

    def check_port_availability(self):
        """检查端口可用性"""
        print("🔌 检查端口可用性...")

        # 检查默认端口7601
        success, stdout, _ = self.run_command("netstat -tuln | grep :7601")
        if success and stdout.strip():
            self.add_warning(
                "port",
                "端口7601被占用",
                "默认端口7601已被使用",
                "修改配置文件中的端口号或终止占用进程",
            )
        else:
            self.add_info("port", "端口7601", "端口可用")

        # 检查是否有Smart AI Router进程运行
        success, stdout, _ = self.run_command(
            "ps aux | grep 'smart-ai-router\\|main.py' | grep -v grep"
        )
        if success and stdout.strip():
            self.add_info("port", "进程状态", "发现Smart AI Router进程正在运行")
        else:
            self.add_info("port", "进程状态", "没有发现运行中的Smart AI Router进程")

    def generate_report(self):
        """生成诊断报告"""
        print("\n" + "=" * 60)
        print("📊 Smart AI Router 诊断报告")
        print("=" * 60)

        # 统计信息
        total_issues = len(self.issues_found)
        total_warnings = len(self.warnings)
        total_info = len(self.info)

        print(f"\n📈 统计信息:")
        print(f"  ❌ 严重问题: {total_issues}")
        print(f"  ⚠️  警告: {total_warnings}")
        print(f"  ℹ️  信息: {total_info}")

        # 显示问题
        if self.issues_found:
            print(f"\n❌ 发现的问题 ({total_issues}):")
            for i, issue in enumerate(self.issues_found, 1):
                print(f"\n{i}. [{issue['category']}] {issue['title']}")
                print(f"   描述: {issue['description']}")
                if issue["solution"]:
                    print(f"   解决方案: {issue['solution']}")

        # 显示警告
        if self.warnings:
            print(f"\n⚠️ 警告 ({total_warnings}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"\n{i}. [{warning['category']}] {warning['title']}")
                print(f"   描述: {warning['description']}")
                if warning["suggestion"]:
                    print(f"   建议: {warning['suggestion']}")

        # 显示信息
        if self.info:
            print(f"\nℹ️ 系统信息 ({total_info}):")
            categories = {}
            for item in self.info:
                cat = item["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)

            for category, items in categories.items():
                print(f"\n  {category.upper()}:")
                for item in items:
                    print(f"    • {item['title']}: {item['description']}")

        # 总结
        print(f"\n🎯 诊断总结:")
        if total_issues == 0:
            if total_warnings == 0:
                print("  ✅ 系统状态良好，没有发现问题！")
            else:
                print("  ✅ 系统基本正常，建议处理警告项以获得更好的体验。")
        else:
            print(f"  ❌ 发现 {total_issues} 个问题需要解决。")
            print("  📋 请按照上面的解决方案逐一处理问题。")

        print(f"\n📚 更多帮助:")
        print("  • 查看故障排除文档: docs/TROUBLESHOOTING.md")
        print("  • 查看开发指南: CLAUDE.md")
        print("  • 提交问题: https://github.com/your-repo/issues")
        print("=" * 60)

        return total_issues == 0

    async def run_full_diagnostic(self):
        """运行完整诊断"""
        print("🔍 Smart AI Router 系统诊断工具")
        print("正在检查系统状态...\n")

        try:
            # 按顺序执行各项检查
            self.check_environment()
            self.check_configuration()
            self.check_dependencies()
            self.check_network_connectivity()
            await self.check_service_health()
            self.check_cache_and_logs()
            self.check_port_availability()

            # 生成报告
            return self.generate_report()

        except KeyboardInterrupt:
            print("\n\n⚠️ 诊断被用户中断")
            return False
        except Exception as e:
            print(f"\n\n❌ 诊断过程中发生错误: {e}")
            traceback.print_exc()
            return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Smart AI Router 诊断工具")
    parser.add_argument(
        "--quick", action="store_true", help="快速检查（跳过网络和服务检查）"
    )
    parser.add_argument(
        "--category",
        choices=[
            "environment",
            "configuration",
            "dependencies",
            "network",
            "service",
            "cache",
            "port",
        ],
        help="只检查特定类别",
    )
    parser.add_argument("--output", help="将报告保存到文件")

    args = parser.parse_args()

    # 创建诊断工具
    diagnostic = DiagnosticTool()

    # 运行诊断
    try:
        success = asyncio.run(diagnostic.run_full_diagnostic())

        # 保存报告
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                # 这里可以实现JSON格式的报告输出
                report_data = {
                    "timestamp": time.time(),
                    "issues": diagnostic.issues_found,
                    "warnings": diagnostic.warnings,
                    "info": diagnostic.info,
                }
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            print(f"\n📄 报告已保存到: {args.output}")

        # 设置退出码
        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
