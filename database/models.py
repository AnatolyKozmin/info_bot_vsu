from sqlalchemy import Column, Integer, String, Boolean, BigInteger, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)  # Для возможности исключить из рассылки


class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String, nullable=True)
    question = Column(String, nullable=False)
    is_anon = Column(Boolean, default=True)
    group_message_id = Column(BigInteger, nullable=True)
    answer = Column(String, nullable=True)
    answer_user_id = Column(BigInteger, nullable=True)
    answer_username = Column(String, nullable=True)


class FAQ(Base):
    __tablename__ = 'faq'
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
