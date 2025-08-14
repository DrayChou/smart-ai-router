#!/usr/bin/env python3
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取数据库URL
db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./smart_ai_router.db")
print(f"数据库URL: {db_url}")

# 提取SQLite文件路径
if "sqlite" in db_url:
    db_file = db_url.split("://")[-1].lstrip("/")
    if db_file.startswith("./"):
        db_file = db_file[2:]

    print(f"数据库文件路径: {db_file}")

    # 检查文件是否存在
    if Path(db_file).exists():
        print(f"数据库文件存在，大小: {Path(db_file).stat().st_size} bytes")

        # 连接数据库检查表
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        print(f"数据库中的表: {[t[0] for t in tables]}")

        # 检查alembic版本
        try:
            cursor.execute("SELECT version_num FROM alembic_version")
            version = cursor.fetchone()
            print(f"Alembic版本: {version[0] if version else '无'}")
        except:
            print("没有alembic_version表")

        conn.close()
    else:
        print("数据库文件不存在！")
else:
    print("不是SQLite数据库")
