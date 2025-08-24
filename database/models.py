from sqlalchemy import Column, Integer, String, Boolean, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

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
