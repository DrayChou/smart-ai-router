#!/usr/bin/env python3
"""
Smart AI Router 诊断工具 - 简化版本（无emoji）
自动检测和诊断系统常见问题
"""

import asyncio
import json
import logging
import subprocess
import sys
import traceback
from pathlib import Path

import yaml

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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

    def add_info(self, category: str, title: str, info: str):
        """添加信息"""
        self.info.append(
            {"category": category, "title": title, "info": info, "severity": "info"}
        )

    def run_command(self, command: str, timeout: int = 10) -> tuple[bool, str, str]:
        """运行系统命令"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.project_root,
            )
            return True, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "命令超时"
        except Exception as e:
            return False, "", str(e)

    def check_file_exists(self, path: Path) -> bool:
        """检查文件或目录是否存在"""
        return (self.project_root / path).exists()

    def check_environment(self):
        """检查环境配置"""
        print("检查环境配置...")

        # 检查Python版本
        python_version = sys.version.split()[0]
        self.add_info("environment", "Python版本", f"Python {python_version}")

        # 检查虚拟环境
        if hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ):
            self.add_info("environment", "虚拟环境", "正在使用虚拟环境")
        elif (self.project_root / ".venv").exists():
            self.add_info("environment", "虚拟环境", "发现.venv目录")
        else:
            self.add_warning(
                "environment",
                "虚拟环境",
                "建议使用虚拟环境",
                "运行: python -m venv .venv",
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

    def check_configuration(self):
        """检查配置文件"""
        print("检查配置文件...")

        # 检查主配置文件
        config_file = Path("config/router_config.yaml")
        if self.check_file_exists(config_file):
            try:
                with open(self.project_root / config_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                self.add_info("configuration", "YAML语法", "配置文件语法正确")

                # 检查渠道配置
                channels = config.get("channels", [])
                enabled_channels = [ch for ch in channels if ch.get("enabled", True)]
                self.add_info(
                    "configuration",
                    "渠道统计",
                    f"总计 {len(channels)} 个渠道，{len(enabled_channels)} 个启用",
                )

            except yaml.YAMLError as e:
                self.add_issue(
                    "configuration",
                    "YAML语法错误",
                    f"配置文件语法错误: {e}",
                    "检查YAML语法，特别是缩进和特殊字符",
                )
            except Exception as e:
                self.add_issue(
                    "configuration", "配置文件读取失败", str(e), "检查文件编码和权限"
                )
        else:
            self.add_issue(
                "configuration",
                "配置文件不存在",
                f"找不到 {config_file}",
                "复制配置模板并进行配置",
            )

    def check_dependencies(self):
        """检查依赖项"""
        print("检查依赖项...")

        # 检查项目配置
        if self.check_file_exists("pyproject.toml"):
            self.add_info("dependencies", "项目配置", "发现 pyproject.toml")
        elif self.check_file_exists("requirements.txt"):
            self.add_info("dependencies", "项目配置", "发现 requirements.txt")
        else:
            self.add_warning(
                "dependencies",
                "项目配置",
                "未找到依赖配置文件",
                "创建 pyproject.toml 或 requirements.txt",
            )

        # 检查关键依赖
        key_dependencies = [
            ("fastapi", "FastAPI web框架"),
            ("httpx", "HTTP客户端"),
            ("yaml", "YAML解析"),
            ("pydantic", "数据验证"),
            ("aiofiles", "异步文件操作"),
            ("tiktoken", "Token计数"),
        ]

        for module, description in key_dependencies:
            try:
                __import__(module)
                self.add_info("dependencies", module, f"{description} - 已安装")
            except ImportError:
                self.add_issue(
                    "dependencies",
                    f"{module}缺失",
                    f"{description}未安装",
                    f"运行: pip install {module}",
                )

    def check_network_connectivity(self):
        """检查网络连接"""
        print("检查网络连接...")

        # 检查DNS和连接
        test_hosts = [
            ("api.openai.com", "OpenAI API"),
            ("api.anthropic.com", "Anthropic API"),
            ("api.siliconflow.cn", "SiliconFlow API"),
        ]

        for host, name in test_hosts:
            # 尝试ping
            success, stdout, stderr = self.run_command(f"ping -n 1 {host}")
            if not success or "100% 丢失" in stdout or "请求超时" in stdout:
                self.add_warning(
                    "network",
                    f"{name} 不可达",
                    f"无法ping通 {host}",
                    "检查网络连接或防火墙设置",
                )

        # 检查HTTPS连接
        try:
            import httpx

            with httpx.Client(timeout=5) as client:
                response = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": "Bearer test"},
                )
                # 401是预期的，说明连接正常
                if response.status_code == 401:
                    self.add_info("network", "HTTPS连接", "OpenAI API可达")
                else:
                    self.add_warning(
                        "network",
                        "API连接异常",
                        f"OpenAI API返回: {response.status_code}",
                        "检查API服务状态",
                    )
        except Exception:
            self.add_warning(
                "network",
                "HTTPS连接问题",
                "无法建立HTTPS连接到OpenAI",
                "检查网络配置或代理设置",
            )

    async def check_service_health(self):
        """检查服务健康状态"""
        print("检查服务健康状态...")

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
        print("检查缓存和日志...")

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
                            self.project_root / cache_file, encoding="utf-8"
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
        else:
            self.add_info("logs", "日志目录", "logs目录不存在（首次运行会创建）")

    def check_port_availability(self):
        """检查端口可用性"""
        print("检查端口可用性...")

        # 检查默认端口7601
        success, stdout, _ = self.run_command("netstat -an | findstr :7601")
        if success and stdout.strip():
            self.add_warning(
                "port",
                "端口7601被占用",
                "默认端口已被其他进程使用",
                "停止其他服务或更改配置中的端口",
            )
        else:
            self.add_info("port", "端口7601", "端口可用")

        # 检查是否有Smart AI Router进程在运行
        success, stdout, _ = self.run_command("tasklist | findstr python")
        if success and "python" in stdout:
            self.add_info("process", "进程状态", "发现Python进程在运行")
        else:
            self.add_info("process", "进程状态", "没有发现运行中的Smart AI Router进程")

    def print_report(self):
        """打印诊断报告"""
        total_issues = len(self.issues_found)
        total_warnings = len(self.warnings)
        total_info = len(self.info)

        print("\n" + "=" * 60)
        print("Smart AI Router 诊断报告")
        print("=" * 60)

        print("\n统计信息:")
        print(f"  ERROR 严重问题: {total_issues}")
        print(f"  WARN  警告: {total_warnings}")
        print(f"  INFO  信息: {total_info}")

        if self.issues_found:
            print(f"\nERROR 发现的问题 ({total_issues}):\n")
            for i, issue in enumerate(self.issues_found, 1):
                print(f"{i}. [{issue['category']}] {issue['title']}")
                print(f"   描述: {issue['description']}")
                if issue["solution"]:
                    print(f"   解决方案: {issue['solution']}")
                print()

        if self.warnings:
            print(f"WARN 警告 ({total_warnings}):\n")
            for i, warning in enumerate(self.warnings, 1):
                print(f"{i}. [{warning['category']}] {warning['title']}")
                print(f"   描述: {warning['description']}")
                if warning["suggestion"]:
                    print(f"   建议: {warning['suggestion']}")
                print()

        print(f"INFO 系统信息 ({total_info}):\n")
        current_category = None
        for info in self.info:
            if info["category"] != current_category:
                current_category = info["category"]
                print(f"  {current_category.upper()}:")
            print(f"    - {info['title']}: {info['info']}")

        print("\n诊断总结:")
        if total_issues == 0:
            print("  OK 系统状态良好，未发现问题。")
        else:
            print(f"  ERROR 发现 {total_issues} 个问题需要解决。")
            print("  请按照上面的解决方案逐一处理问题。")

        print("\n更多帮助:")
        print("  - 查看故障排除文档: docs/TROUBLESHOOTING.md")
        print("  - 查看开发指南: CLAUDE.md")
        print("  - 提交问题: https://github.com/your-repo/issues")
        print("=" * 60)

        return total_issues == 0

    async def run_full_diagnostic(self):
        """运行完整诊断"""
        print("Smart AI Router 系统诊断工具")
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

            # 打印报告
            success = self.print_report()
            return success

        except KeyboardInterrupt:
            print("\n诊断被用户中断")
            return False
        except Exception as e:
            print(f"诊断过程中发生错误: {e}")
            traceback.print_exc()
            return False


def main():
    """主函数"""
    try:
        diagnostic = DiagnosticTool()
        success = asyncio.run(diagnostic.run_full_diagnostic())

        if success:
            print("\n诊断完成：系统状态良好")
            sys.exit(0)
        else:
            print("\n诊断完成：发现问题，请查看上述报告")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR 运行失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
