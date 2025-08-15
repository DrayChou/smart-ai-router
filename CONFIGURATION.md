# Smart AI Router - 配置文件管理指南

## 📁 配置文件分类

### ✅ 提交到版本控制的文件
这些文件包含模板和默认配置，**不包含敏感信息**：

```
config/
├── router_config.yaml.template     # 👈 YAML配置模板 (提交)
├── example.yaml                    # 👈 示例配置 (提交)
├── model_groups.yaml              # 👈 模型组定义 (提交)
├── pricing_policies.yaml          # 👈 价格策略 (提交) 
├── providers.yaml                 # 👈 Provider定义 (提交)
└── system.yaml                    # 👈 系统配置 (提交)
```

### ❌ 不提交到版本控制的文件
这些文件包含API密钥或用户数据，**被.gitignore忽略**：

```
config/
├── router_config.yaml             # 👈 用户实际配置 (包含API密钥)
├── channels_config.json           # 👈 导出的渠道配置 (包含密钥)
├── simple_config.json             # 👈 JSON配置 (可能包含密钥)
├── unified_config.json            # 👈 统一配置 (可能包含密钥)
└── *_backup.yaml                  # 👈 备份配置文件

# 根目录
├── .env                           # 👈 环境变量文件
├── imported_channels.json         # 👈 导入的渠道数据
├── runtime_state.json             # 👈 运行时状态
├── api_keys.json                  # 👈 API密钥文件
└── smart_router.db                # 👈 SQLite数据库
```

## 🔧 配置文件使用流程

### 1. 初始设置
```bash
# 复制模板文件
cp config/router_config.yaml.template config/router_config.yaml

# 编辑配置，填入API密钥
vim config/router_config.yaml
```

### 2. 安全检查
编辑配置文件时，确保：
- ✅ API密钥不要意外提交
- ✅ 敏感的URL和端点信息保密
- ✅ 用户数据和统计信息不泄露

### 3. 备份策略
```bash
# 备份当前配置 (备份文件会被自动忽略)
cp config/router_config.yaml config/router_config_backup.yaml

# 压缩备份多个配置文件
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/router_config.yaml .env
```

## 🛡️ 安全最佳实践

### API密钥管理
1. **从不提交真实API密钥到Git**
2. **使用模板文件提供示例格式**
3. **定期轮换API密钥**
4. **为不同环境使用不同的密钥**

### 文件权限
```bash
# 设置配置文件为仅用户可读
chmod 600 config/router_config.yaml
chmod 600 .env

# 设置配置目录权限
chmod 700 config/
```

### 简单备份
```bash
# 备份当前配置 (备份文件会被自动忽略)
cp config/router_config.yaml config/router_config_backup.yaml
```

## 📋 .gitignore 规则说明

### 配置文件规则
```gitignore
# 用户配置文件 (包含API密钥)
config/router_config.yaml      # 用户的实际配置
config/channels_config.json    # 导出的渠道数据
config/simple_config.json      # JSON格式配置
config/unified_config.json     # 统一配置文件
config/*_backup.yaml          # 备份文件

# 运行时文件
runtime_state.json
channel_stats.json
cost_tracking.json

# 敏感数据文件
api_keys.json
.env
imported_channels.json        # 导入的数据
smart_router.db              # 数据库文件
```

### 数据库和缓存
```gitignore
# 数据库文件
*.db
*.sqlite
*.sqlite3
smart_router.db

# 导入的数据
imported_channels.json
```

## 🔄 配置文件迁移

### 从旧版本升级
```bash
# 1. 备份现有配置
cp config/old_config.yaml config/old_config_backup.yaml

# 2. 使用新模板
cp config/router_config.yaml.template config/router_config.yaml

# 3. 迁移设置
# 手动复制API密钥和自定义配置到新文件
```

### 批量更新配置
```bash
# 创建配置更新脚本
cat > update_configs.sh << 'EOF'
#!/bin/bash
for env in dev prod test; do
    if [ -f "config/router_config_${env}.yaml" ]; then
        echo "更新 ${env} 环境配置..."
        # 在这里添加配置更新逻辑
    fi
done
EOF

chmod +x update_configs.sh
```

## ⚠️ 注意事项

### 常见错误
1. **意外提交API密钥** - 使用`git log --grep="key"`检查
2. **配置文件权限过宽** - 定期检查文件权限
3. **明文存储密钥** - 考虑使用密钥管理服务

### 恢复策略
```bash
# 如果意外提交了敏感信息
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config/router_config.yaml' \
  --prune-empty --tag-name-filter cat -- --all

# 强制推送清理后的历史
git push origin --force --all
git push origin --force --tags
```

### 个人使用建议
1. **定期备份配置文件**到安全位置
2. **记录API密钥来源**，便于续费和管理
3. **测试配置变更**后再保存
4. **保持配置文件简洁**，避免无用配置

## 📚 相关文档

- [README.md](README.md) - 项目总体说明
- [TODO.md](TODO.md) - 开发进度追踪
- [config/router_config.yaml.template](config/router_config.yaml.template) - 配置模板

---

**重要提醒**: 配置文件包含敏感信息，请妥善保管，避免泄露API密钥！