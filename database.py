"""
数据库配置模块
==============
- 异步引擎: 管理 MySQL 连接池，执行 SQL
- 会话工厂: 批量生产"会话"对象
- get_db(): FastAPI 依赖注入函数，请求进来给会话，请求结束自动 commit/rollback/close

技术栈: SQLAlchemy 异步 + aiomysql 驱动
"""

# ----- 导入 -----
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


# ----- 标准库 -----
import os

# ----- 数据库连接地址 -----
# 格式: mysql+aiomysql://用户:密码@主机:端口/库名?charset=utf8mb4
# 优先从环境变量读取（Docker Compose 会注入），没有就用本地默认值
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://root:root123456@localhost:3306/student_db?charset=utf8mb4"
)


# ----- 异步引擎（连接池核心）-----
# echo: 打印每条 SQL。开发环境默认开启，生产环境通过环境变量关闭
# 设置 SQL_ECHO=false 即可静默
SQL_ECHO = os.environ.get("SQL_ECHO", "true").lower() in ("true", "1", "yes")
async_engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO)


# ----- 异步会话工厂 -----
# expire_on_commit=False: commit 后对象属性不清空，FastAPI 标配
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# ----- 依赖注入: get_db() -----
# 每次 API 请求调用它获取一个临时会话:
#   yield session  → 路由用
#   commit()       → 成功则提交
#   rollback()     → 异常则回滚
#   close()        → 不管怎样都关闭
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
