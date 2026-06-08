"""
配置预加载模块
==============
必须在所有其他模块之前导入，确保 .env 中的环境变量
在 database / routers 等模块读取 os.environ 之前就已加载完毕。

用法: 在 main.py 第一行写 `import config` 即可。
"""

from dotenv import load_dotenv

# 本地开发时加载 .env 文件
# Docker 部署时 .env 不存在，环境变量由 docker-compose 注入，load_dotenv() 静默跳过
# override=True: .env 中的值优先于系统环境变量
load_dotenv(override=True)
