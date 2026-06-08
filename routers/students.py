"""
学生管理路由模块
================
API 接口:
    POST   /students/          → 创建学生
    GET    /students/          → 学生列表（Redis 缓存）
    GET    /students/{姓名}     → 按姓名查学生

技术栈: FastAPI + SQLAlchemy 异步 + Redis 缓存
"""

# ----- FastAPI -----
from fastapi import APIRouter, Depends

# ----- SQLAlchemy -----
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# ----- 项目模块 -----
from database import get_db
from models import Student

# ----- Pydantic -----
from pydantic import BaseModel

# ----- Redis & JSON & OS -----
import redis
import json
import os

from fastapi import HTTPException


# ============================================================
# Redis 连接
# ============================================================
# decode_responses=True: 取出来的数据自动转字符串，不用手动 decode
# protocol=2: 指定 Redis 协议版本（兼容性好）
# 优先从环境变量读取（Docker Compose 会注入），没有就用本地默认值
r = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True,
    protocol=2
)


# ============================================================
# 路由实例
# ============================================================
router = APIRouter(prefix="/students", tags=["学生管理"])


# ============================================================
# Pydantic 模型 —— API 的输入/输出格式
# ============================================================

class StudentCreate(BaseModel):
    """创建学生请求体"""
    name: str
    age: int
    grade: str = "大一"


class StudentResponse(BaseModel):
    """学生信息响应体"""
    id: int
    name: str
    age: int
    grade: str


class StudentProfile(BaseModel):
    """学生档案（供 advice 模块调用，多了个 bio 字段）"""
    name: str
    age: int
    grade: str = "大一"
    bio: str = ""


class AdviceResponse(BaseModel):
    """AI 建议响应体（供 advice 模块使用）"""
    student_name: str
    advice: str


class StudentUpdate(BaseModel):
    """修改学生信息"""
    name: str | None = None     #可选,不传就不改
    age: int | None = None
    grade: str | None = None


# ============================================================
# POST /students/ —— 创建学生
# ============================================================
@router.post("/", response_model=StudentResponse)
async def create_student(
    student: StudentCreate,
    db: AsyncSession = Depends(get_db)
):
    """新增学生，同时清除 Redis 缓存"""

    # 1. 构建 ORM 对象
    new_student = Student(
        name=student.name,
        age=student.age,
        grade=student.grade
    )

    db.add(new_student)

    # 2. 先删缓存 → 再提交数据库
    #    顺序很重要: 缓存先干掉（失败也没事），数据提交在后
    #    这样即使 Redis 挂了，数据不会脏
    try:
        r.delete("all_students")
    except Exception:
        pass

    # 3. 提交 + 刷新（拿自增 id）
    await db.commit()
    await db.refresh(new_student)

    return new_student


# ============================================================
# GET /students/ —— 学生列表（带 Redis 缓存）
# ============================================================
@router.get("/", response_model=list[StudentResponse])
async def list_students(db: AsyncSession = Depends(get_db)):
    """查询所有学生，优先走 Redis 缓存"""

    # ---- 第一步: 查 Redis 缓存 ----
    try:
        cached = r.get("all_students")
        if cached:
            # 命中缓存，直接返回，不用查 MySQL
            return json.loads(cached)#缓存里面的是一串json格式的字符串,无法直接操作,json.loads()把他转换成python对象,和json.dumps()是一对
    except Exception:
        pass  # Redis 挂了 → 降级，走数据库

    # ---- 第二步: 缓存未命中，查 MySQL ----
    result = await db.execute(select(Student))
    students = result.scalars().all()

    # ---- 第三步: 结果写入 Redis，60 秒过期 ----
    # ORM 对象不能直接存 Redis，先转成 dict 列表，再 json.dumps
    students_data = [
        {"id": s.id, "name": s.name, "age": s.age, "grade": s.grade}
        for s in students
    ]
    try:
        r.set("all_students", json.dumps(students_data), ex=60)
    except Exception:
        pass

    return students_data


# ============================================================
# GET /students/{student_name} —— 按姓名查学生
# ============================================================
@router.get("/{student_name}", response_model=StudentResponse)
async def get_student(
    student_name: str,
    db: AsyncSession = Depends(get_db)
):
    """根据姓名查单个学生，找不到返回 404"""

    # WHERE name = :student_name（自动防 SQL 注入）
    result = await db.execute(
        select(Student).where(Student.name == student_name)
    )

    # scalar_one_or_none: 找到返回对象，没找到返回 None
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    return student


@router.delete("/{student_id}")
async def delete_student(student_id: int, db: AsyncSession = Depends(get_db)):
    #1.先查询学生是否存在
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    #2.不存在,返回404
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    
    #3.存在,删除
    await db.delete(student)
    await db.commit()

    #4.删除缓存
    try:
        r.delete("all_students")
    except Exception:
        pass


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(student_id: int, data: StudentUpdate, db: AsyncSession=Depends(get_db)):
    #1.先查学生存不存在
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    #2.不存在,返回404
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    #3.存在,逐个字段判断:前端传了就更新,没传就保持原样
    if data.name is not None:
        student.name = data.name
    if data.age is not None:
        student.age = data.age
    if data.grade is not None:
        student.grade = data.grade

    await db.commit()
    await db.refresh(student)

    #4.删除缓存
    try:
        r.delete("all_students")
    except Exception:
        pass

    return student 