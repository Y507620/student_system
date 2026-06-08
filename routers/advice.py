"""
AI 学习建议路由模块
===================
调用 DeepSeek 大模型，根据学生档案生成个性化学习建议。

API 接口:
    POST /advice/generate         →  传入学生档案，AI 生成学习建议（一次性返回）
    POST /advice/generate/stream  →  同上，但流式输出（逐字推送，SSE 格式）
    GET  /advice/history          →  查询最近 20 条建议记录

技术栈: DeepSeek API (OpenAI 兼容接口) + SQLAlchemy 异步
"""

# ----- 标准库 -----
import os

# ----- FastAPI -----
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

# ----- JSON -----
import json

# ----- SQLAlchemy -----
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# ----- OpenAI SDK（兼容 DeepSeek）-----
from openai import OpenAI

# ----- 项目模块 -----
from database import get_db, AsyncSessionLocal
from models import AdviceRecord

# ----- 从 students 模块导入共享的数据模型 -----
from routers.students import StudentProfile, AdviceResponse

from fastapi import HTTPException


# ============================================================
# 路由实例
# ============================================================
advice_router = APIRouter(prefix="/advice", tags=["学习建议"])


# ============================================================
# DeepSeek 客户端
# ============================================================
# DeepSeek 提供了与 OpenAI 兼容的 API，所以直接用 openai 库调用。
#
# api_key: 从环境变量读取，不要硬编码在代码里！
#   设置方式（终端执行）:
#     Windows: set DEEPSEEK_API_KEY=你的key
#     Linux/Mac: export DEEPSEEK_API_KEY=你的key
#
# base_url: DeepSeek 的 API 地址（兼容 OpenAI 格式）
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)


# ============================================================
# POST /advice/generate —— AI 生成学习建议
# ============================================================
@advice_router.post("/generate", response_model=AdviceResponse)
async def generate_advice(
    profile: StudentProfile,                # 学生档案（姓名/年龄/年级/简介）
    db: AsyncSession = Depends(get_db)      # 数据库会话
):
    """传入学生档案，调用 DeepSeek 生成个性化学习建议

    请求示例:
        POST /advice/generate
        {
            "name": "张三",
            "age": 20,
            "grade": "大二",
            "bio": "数学基础薄弱，喜欢编程"
        }

    响应:
        {
            "student_name": "张三",
            "advice": "1. 每天刷一道算法题...\n2. 加入编程社团..."
        }
    """

    # ----- 第一步: 构造 Prompt（提示词）-----
    # 把学生信息嵌入到提示词模板中，告诉 AI 它的角色和任务
    # bio 为空时显示"无"，避免 AI 乱猜
    prompt = f"""
        你是一位经验丰富的大学辅导员，请根据以下学生信息，给出3-5条具体、个性化的学习建议。

        学生姓名: {profile.name}
        年龄: {profile.age}
        年级: {profile.grade}
        个人简介: {profile.bio if profile.bio else "无"}

        请直接给出建议，不要客套话，每条建议用一句话说清楚。
    """

    # ----- 第二步: 调用 DeepSeek API -----
    # chat.completions.create: 发送对话请求
    #   model="deepseek-chat": DeepSeek 的通用对话模型
    #   messages: 对话历史（这里只有一条用户消息）
    #   stream=False: 等完整响应再返回（改为 True 可实现流式输出）
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        # 提取 AI 的回复文本
        advice_text = response.choices[0].message.content
    except Exception as e:
        # API 调用失败 → 返回 500 错误
        # 可能原因: key 没设置、网络不通、余额不足、模型限流
        raise HTTPException(status_code=500, detail=f"AI服务调用失败: {str(e)}")

    # ----- 第三步: 记录到数据库 -----
    # 把每次调用结果存下来，方便后续查看历史
    record = AdviceRecord(
        student_name=profile.name,
        bio=profile.bio,
        advice=advice_text
    )
    db.add(record)
    await db.commit()

    # ----- 第四步: 返回结果 -----
    # 注意: 数据库也存了，但这里直接返回 AI 的原始响应
    # 客户端如果丢了结果，可以从 /advice/history 找回
    return AdviceResponse(student_name=profile.name, advice=advice_text)


# ============================================================
# POST /advice/generate/stream —— AI 生成学习建议（流式输出）
# ============================================================
@advice_router.post("/generate/stream")
async def generate_advice_stream(profile: StudentProfile):
    """流式输出版本 —— 调用 DeepSeek，逐字返回 AI 建议（SSE 格式）

    和 /generate 接口的区别：
        /generate         → 等 AI 全部写完，一次性返回 JSON
        /generate/stream  → AI 写一个字就推一个字，前端实时显示

    客户端接收示例：
        fetch('/advice/generate/stream', {
            method: 'POST',
            body: JSON.stringify({name: '张三', age: 20, grade: '大二', bio: '...'})
        })
        const reader = response.body.getReader()
        // 逐块读取...
    """

    # ----- 构造 Prompt -----
    prompt = f"""
        你是一位经验丰富的大学辅导员，请根据以下学生信息，给出3-5条具体、个性化的学习建议。

        学生姓名: {profile.name}
        年龄: {profile.age}
        年级: {profile.grade}
        个人简介: {profile.bio if profile.bio else "无"}

        请直接给出建议，不要客套话，每条建议用一句话说清楚。
    """

    async def event_stream():
        """异步生成器 —— 逐块 yield SSE 事件"""
        full_text = ""
        try:
            # ----- 调用 DeepSeek API（stream=True）-----
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                stream=True       # 🔑 关键：开启流式
            )

            # ----- 逐块读取 -----
            for chunk in response:
                # delta.content 是当前这一小块文本（几个字）
                delta = chunk.choices[0].delta
                if delta.content:
                    content = delta.content
                    full_text += content
                    # SSE 格式: "data: JSON字符串\n\n"
                    yield f"data: {json.dumps({'content': content})}\n\n"

            # ----- 流结束时保存到数据库 -----
            async with AsyncSessionLocal() as session:
                record = AdviceRecord(
                    student_name=profile.name,
                    bio=profile.bio,
                    advice=full_text
                )
                session.add(record)
                await session.commit()

            # 发送完成信号
            yield f"data: {json.dumps({'done': True, 'student_name': profile.name})}\n\n"

        except Exception as e:
            # 出错时也以 SSE 格式返回错误
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # 禁用 Nginx 缓冲
        }
    )


# ============================================================
# GET /advice/history —— 查询建议历史
# ============================================================
@advice_router.get("/history")
async def get_history(db: AsyncSession = Depends(get_db)):
    """查询最近 20 条建议记录，按时间倒序

    请求示例:
        GET /advice/history

    响应:
        [
            {
                "id": 5,
                "student_name": "张三",
                "bio": "...",
                "advice": "...",
                "create_time": "2026-06-06T12:00:00"
            },
            ...
        ]
    """

    # order_by(create_time.desc()): 按创建时间倒序 → 最新的排最前
    # limit(20): 只取最近 20 条，防止一次返回太多数据
    result = await db.execute(
        select(AdviceRecord).order_by(AdviceRecord.create_time.desc()).limit(20)
    )

    # 返回 ORM 对象列表，FastAPI 自动转 JSON
    records = result.scalars().all()
    return records
