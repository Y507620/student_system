"""
FastAPI 应用入口
================
启动: fastapi dev main.py  或  uvicorn main:app --reload

职责:
    1. 创建 FastAPI 实例
    2. 启动时自动建表
    3. 注册各模块路由
    4. 根路径健康检查
"""

# ----- 环境变量预加载（必须放在所有 import 最前面）-----
import config  # noqa: F401 负责加载 .env，确保后续模块的 os.environ.get() 能拿到值

# ----- FastAPI -----
from fastapi import FastAPI

# ----- 项目模块 -----
from database import async_engine
from models import Base
from routers.students import router           # 学生模块路由
from routers.advice import advice_router      # AI 建议模块路由


app = FastAPI()


# ----- 启动事件: 自动建表 -----
# 根据 models.py 中的模型定义，自动创建不存在的表
# 注意: 只建不修，改了模型需要手动迁移或用 Alembic
@app.on_event("startup")
async def startup():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ----- 注册路由 -----
app.include_router(router)         # /students/...
app.include_router(advice_router)  # /advice/...


# ----- 根路径 -----
@app.get("/")
async def root():
    return {"message": "Hello"}


#乐乐