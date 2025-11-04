from sqlalchemy.future import select
from database.engine import get_session
from database.models import User
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from config import settings
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

ADMINS = settings.ADMINS

# --- FSM состояния для рассылки ---
class Broadcast(StatesGroup):
    choosing_content_type = State()
    waiting_for_content = State()
    choosing_broadcast_type = State()
    confirming = State()


# --- Клавиатуры ---
def get_content_type_kb():
    """Клавиатура выбора типа контента"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data="bcast_type_text")],
            [InlineKeyboardButton(text="🖼 Картинка", callback_data="bcast_type_photo")],
            [InlineKeyboardButton(text="🖼📝 Картинка + текст", callback_data="bcast_type_photo_text")],
            [InlineKeyboardButton(text="🎥 Видео", callback_data="bcast_type_video")],
            [InlineKeyboardButton(text="🎵 Аудио", callback_data="bcast_type_audio")],
            [InlineKeyboardButton(text="⭕️ Кружок", callback_data="bcast_type_video_note")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bcast_cancel")]
        ]
    )


def get_broadcast_type_kb():
    """Клавиатура выбора типа рассылки (тест или все)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Тестовая рассылка (админам)", callback_data="bcast_test")],
            [InlineKeyboardButton(text="📢 Рассылка всем пользователям", callback_data="bcast_all")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bcast_cancel")]
        ]
    )


def get_confirm_kb():
    """Клавиатура подтверждения рассылки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="bcast_confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="bcast_cancel")]
        ]
    )


cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
    one_time_keyboard=True
)


# --- Команда /rass (только для админов) ---
@router.message(Command("rass"))
async def start_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔️ Доступ запрещён! Только для администраторов.")
        return
    
    await msg.answer(
        "📢 <b>Панель рассылки</b>\n\n"
        "Выберите тип контента для рассылки:",
        parse_mode="HTML",
        reply_markup=get_content_type_kb()
    )
    await state.set_state(Broadcast.choosing_content_type)


# --- Отмена рассылки ---
@router.callback_query(F.data == "bcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


@router.message(F.text == "❌ Отмена")
async def cancel_broadcast_text(msg: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state and current_state.startswith("Broadcast:"):
        await state.clear()
        await msg.answer("❌ Рассылка отменена.")


# --- Выбор типа контента ---
@router.callback_query(F.data.startswith("bcast_type_"), Broadcast.choosing_content_type)
async def choose_content_type(callback: CallbackQuery, state: FSMContext):
    content_type = callback.data.replace("bcast_type_", "")
    await state.update_data(content_type=content_type)
    
    # Определяем текст подсказки в зависимости от типа
    prompts = {
        "text": "📝 Отправьте текст сообщения для рассылки:",
        "photo": "🖼 Отправьте фото для рассылки:",
        "photo_text": "🖼📝 Отправьте фото с подписью (текст будет в описании фото):",
        "video": "🎥 Отправьте видео для рассылки:",
        "audio": "🎵 Отправьте аудио для рассылки:",
        "video_note": "⭕️ Отправьте видео-кружок для рассылки:"
    }
    
    await callback.message.edit_text(
        prompts.get(content_type, "Отправьте контент:"),
        reply_markup=None
    )
    await callback.answer()
    await state.set_state(Broadcast.waiting_for_content)


# --- Получение контента ---
@router.message(Broadcast.waiting_for_content)
async def receive_content(msg: Message, state: FSMContext):
    data = await state.get_data()
    content_type = data.get("content_type")
    
    # Валидация контента в зависимости от типа
    if content_type == "text":
        if not msg.text:
            await msg.answer("❗️ Пожалуйста, отправьте текстовое сообщение.")
            return
        await state.update_data(text=msg.text)
    
    elif content_type == "photo":
        if not msg.photo:
            await msg.answer("❗️ Пожалуйста, отправьте фото.")
            return
        await state.update_data(photo_id=msg.photo[-1].file_id, caption=msg.caption)
    
    elif content_type == "photo_text":
        if not msg.photo:
            await msg.answer("❗️ Пожалуйста, отправьте фото с текстом.")
            return
        if not msg.caption:
            await msg.answer("❗️ Пожалуйста, добавьте текст к фото (подпись).")
            return
        await state.update_data(photo_id=msg.photo[-1].file_id, caption=msg.caption)
    
    elif content_type == "video":
        if not msg.video:
            await msg.answer("❗️ Пожалуйста, отправьте видео.")
            return
        await state.update_data(video_id=msg.video.file_id, caption=msg.caption)
    
    elif content_type == "audio":
        if not msg.audio and not msg.voice:
            await msg.answer("❗️ Пожалуйста, отправьте аудио.")
            return
        if msg.audio:
            await state.update_data(audio_id=msg.audio.file_id, caption=msg.caption)
        else:
            await state.update_data(voice_id=msg.voice.file_id, caption=msg.caption)
    
    elif content_type == "video_note":
        if not msg.video_note:
            await msg.answer("❗️ Пожалуйста, отправьте видео-кружок.")
            return
        await state.update_data(video_note_id=msg.video_note.file_id)
    
    # Переходим к выбору типа рассылки
    await msg.answer(
        "✅ Контент получен!\n\n"
        "Выберите тип рассылки:",
        reply_markup=get_broadcast_type_kb()
    )
    await state.set_state(Broadcast.choosing_broadcast_type)


# --- Выбор типа рассылки (тест или все) ---
@router.callback_query(F.data.in_(["bcast_test", "bcast_all"]), Broadcast.choosing_broadcast_type)
async def choose_broadcast_type(callback: CallbackQuery, state: FSMContext):
    broadcast_type = callback.data.replace("bcast_", "")
    await state.update_data(broadcast_type=broadcast_type)
    
    # Получаем количество получателей
    async for session in get_session():
        if broadcast_type == "test":
            count = len(ADMINS)
        else:
            result = await session.execute(select(User).where(User.is_active == True))
            count = len(result.scalars().all())
    
    broadcast_type_text = "🧪 Тестовая рассылка админам" if broadcast_type == "test" else "📢 Рассылка всем пользователям"
    
    await callback.message.edit_text(
        f"<b>{broadcast_type_text}</b>\n\n"
        f"📊 Количество получателей: <b>{count}</b>\n\n"
        f"⚠️ Подтвердите отправку рассылки:",
        parse_mode="HTML",
        reply_markup=get_confirm_kb()
    )
    await callback.answer()
    await state.set_state(Broadcast.confirming)


# --- Подтверждение и отправка рассылки ---
@router.callback_query(F.data == "bcast_confirm", Broadcast.confirming)
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    content_type = data.get("content_type")
    broadcast_type = data.get("broadcast_type")
    
    await callback.message.edit_text("⏳ Начинаю рассылку...")
    await callback.answer()
    
    # Получаем список получателей
    if broadcast_type == "test":
        recipients = list(ADMINS)
    else:
        async for session in get_session():
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()
            recipients = [user.tg_id for user in users]
    
    # Отправка сообщений
    success_count = 0
    fail_count = 0
    
    for user_id in recipients:
        try:
            # Отправляем контент в зависимости от типа
            if content_type == "text":
                await bot.send_message(user_id, data.get("text"))
            
            elif content_type == "photo" or content_type == "photo_text":
                await bot.send_photo(
                    user_id,
                    photo=data.get("photo_id"),
                    caption=data.get("caption")
                )
            
            elif content_type == "video":
                await bot.send_video(
                    user_id,
                    video=data.get("video_id"),
                    caption=data.get("caption")
                )
            
            elif content_type == "audio":
                if data.get("audio_id"):
                    await bot.send_audio(
                        user_id,
                        audio=data.get("audio_id"),
                        caption=data.get("caption")
                    )
                else:
                    await bot.send_voice(
                        user_id,
                        voice=data.get("voice_id")
                    )
            
            elif content_type == "video_note":
                await bot.send_video_note(
                    user_id,
                    video_note=data.get("video_note_id")
                )
            
            success_count += 1
            # Небольшая задержка, чтобы не попасть под ограничения Telegram
            await asyncio.sleep(0.05)
        
        except Exception as e:
            fail_count += 1
            logger.error(f"[ERROR] Не удалось отправить сообщение пользователю {user_id}: {e}")
    
    # Отчёт о рассылке
    broadcast_type_text = "🧪 Тестовая рассылка" if broadcast_type == "test" else "📢 Рассылка"
    report = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Ошибок: {fail_count}\n"
        f"📈 Всего: {success_count + fail_count}"
    )
    
    await bot.send_message(callback.from_user.id, report, parse_mode="HTML")
    await state.clear()
    logger.info(f"[INFO] {broadcast_type_text} завершена. Успешно: {success_count}, Ошибок: {fail_count}")

