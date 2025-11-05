from database.models import Base
from database.engine import engine
import asyncio

async def run_migrations():
    """
    Создаёт все таблицы из моделей в базе данных.
    Безопасно для повторного запуска - не пересоздаёт существующие таблицы.
    
    Таблицы:
    - users (новая)
    - questions
    - faq
    - broadcast_interactions (новая)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Миграции успешно применены!")
    print("📋 Таблицы: users, questions, faq, broadcast_interactions")

if __name__ == "__main__":
    asyncio.run(run_migrations())
