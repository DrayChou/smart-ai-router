# 本地 CI 检查工具

本工具允许你在推送代码前，在本地运行与 GitHub CI 相同的检查，确保代码质量。

## 🎯 功能特性

- **完全复制 GitHub CI**: 运行与`.github/workflows/ci.yml`中相同的检查命令
- **多平台支持**: Windows、Linux、macOS
- **彩色输出**: 清晰的成功/失败状态显示
- **详细报告**: 显示所有检查结果和修复建议
- **快速反馈**: 避免推送后发现 CI 失败
- **双版本支持**: 完整版和简化版，适应不同环境需求

## 📦 可用版本

### 🔧 完整版 (`local_ci_check.py`)
- **完整CI检查**: Black, isort, Ruff, MyPy 全部检查
- **虚拟环境依赖**: 需要 `uv` 和正常的虚拟环境
- **完全兼容CI**: 与 GitHub CI 100% 一致

### ⚡ 简化版 (`simple_ci_check.py`)
- **基础检查**: Python语法检查和核心模块导入测试
- **系统Python**: 使用系统安装的Python和工具
- **环境友好**: 在虚拟环境有问题时可用
- **快速验证**: 基本功能验证和语法检查

## 📋 检查项目

### 代码质量检查 (完整版 - 与 GitHub CI 相同)

- **Black**: 代码格式化检查
- **isort**: 导入排序检查
- **Ruff**: 代码质量和风格检查 (排除 scripts/)
- **MyPy**: 静态类型检查

### 基础功能测试

- **模块导入**: 验证核心模块可以正常导入
- **语法检查**: 确保没有语法错误

## 🚀 使用方法

### Windows

```batch
# 方法1: 双击运行
scripts\local_ci_check.bat

# 方法2: 命令行运行
cd D:\Code\smart-ai-router
scripts\local_ci_check.bat
```

### Linux/macOS

```bash
# 方法1: 直接运行
./scripts/local_ci_check.sh

# 方法2: 或者
cd /path/to/smart-ai-router
bash scripts/local_ci_check.sh
```

### Python 直接运行

```bash
# 完整版本（需要虚拟环境正常工作）
cd /path/to/smart-ai-router
python scripts/local_ci_check.py

# 简化版本（在虚拟环境有问题时使用）
python scripts/simple_ci_check.py
```

## 📊 输出示例

```
🚀 开始本地CI检查...
项目路径: D:\Code\smart-ai-router

📦 检查依赖环境
🔍 UV包管理器
✅ UV包管理器 - 通过

🎯 代码质量检查 (与GitHub CI相同)
🔍 Black代码格式化检查
✅ Black代码格式化检查 - 通过

🔍 isort导入排序检查
✅ isort导入排序检查 - 通过

🔍 Ruff代码质量检查
✅ Ruff代码质量检查 - 通过

🔍 MyPy类型检查
✅ MyPy类型检查 - 通过

🧪 基础功能测试
🔍 核心模块导入测试
✅ 核心模块导入测试 - 通过

📊 本地CI检查结果摘要
==================================================
✅ 通过的检查 (6项):
  • UV包管理器
  • Black代码格式化检查
  • isort导入排序检查
  • Ruff代码质量检查
  • MyPy类型检查
  • 核心模块导入测试

🎉 所有检查通过！可以安全推送到GitHub

总耗时: 12.3秒

✅ 本地CI检查全部通过！
📤 可以安全推送到GitHub进行正式CI检查
```

## 🔧 问题修复建议

如果检查失败，脚本会提供具体的修复建议：

### Black 格式化问题

```bash
uv run black .  # 自动修复格式问题
```

### isort 导入排序问题

```bash
uv run isort .  # 自动修复导入排序
```

### Ruff 代码质量问题

```bash
uv run ruff check . --fix  # 自动修复部分问题
```

### MyPy 类型检查问题

需要手动修复类型注解问题

## ⚡ 工作流建议

1. **开发时**: 经常运行本地检查
2. **提交前**: 必须运行本地检查
3. **推送前**: 确保所有检查通过
4. **CI 失败时**: 先在本地重现和修复问题

## 🎛️ 自定义配置

如需修改检查命令，编辑 `scripts/local_ci_check.py` 中的 `run_code_quality_checks()` 方法。

## 🚨 注意事项

- 确保已安装 `uv` 包管理器
- 在项目根目录运行
- 某些检查可能需要网络连接
- Windows 用户注意路径分隔符
- 如遇到虚拟环境文件锁定问题，使用简化版本 `simple_ci_check.py`

## 📝 与 CI 同步

本工具与 `.github/workflows/ci.yml` 保持同步，如果 CI 配置更新，请相应更新本地检查脚本。
