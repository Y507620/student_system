"""
数据模型模块
============
定义所有数据库表的结构（SQLAlchemy ORM）。

一个类 = 一张表，一个属性 = 一个列，一个实例 = 一行数据。

表一览:
    students        → 学生基本信息
    advice_records  → AI 生成的学习建议记录
"""

# ----- SQLAlchemy 核心 -----
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ----- 列类型 -----
from sqlalchemy import String, Integer, Text, DateTime, func

# ----- Python 标准库 -----
from datetime import datetime


# ============================================================
# 声明式基类 —— 所有模型的"祖先"
# ============================================================
# Base.metadata 自动收集所有子类的表信息
# Base.metadata.create_all() 一键建表
class Base(DeclarativeBase):
    pass


# ============================================================
# Student —— 学生表
# ============================================================
class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键自增
    name: Mapped[str] = mapped_column(String(50))                          # 姓名，最长50字符
    age: Mapped[int] = mapped_column(Integer)                              # 年龄
    grade: Mapped[str] = mapped_column(String(20), default="大一")          # 年级，默认大一


# ============================================================
# AdviceRecord —— AI 建议记录表
# ============================================================
# 每次调用 DeepSeek 生成建议后，存一条记录到此表
class AdviceRecord(Base):
    __tablename__ = "advice_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键自增
    student_name: Mapped[str] = mapped_column(String(50))                  # 学生姓名
    bio: Mapped[str] = mapped_column(Text, default="")                     # 个人简介，不限长度
    advice: Mapped[str] = mapped_column(Text)                              # AI 生成的建议，不限长度
    # insert_default=func.now(): 插入时自动填当前时间（数据库端执行）
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now())
