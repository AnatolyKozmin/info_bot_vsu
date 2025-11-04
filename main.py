import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import user_handlers, broadcast_handlers
from config import settings

bot = Bot(token=settings.TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def register_handlers():
    dp.include_router(user_handlers.router)
    dp.include_router(broadcast_handlers.router)


async def main():
    register_handlers()
    print("Работает")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
