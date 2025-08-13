from database.models import Base
from database.engine import engine
import asyncio

async def run_migrations():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Миграции успешно применены!")

if __name__ == "__main__":
    asyncio.run(run_migrations())
