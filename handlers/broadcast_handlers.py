from sqlalchemy.future import select
from sqlalchemy import func
from database.engine import get_session
from database.models import User, BroadcastInteraction
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from config import settings
import logging
import asyncio
from datetime import datetime, timedelta
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

ADMINS = settings.ADMINS

# --- FSM состояния для рассылки ---
class Broadcast(StatesGroup):
    choosing_content_type = State()
    waiting_for_content = State()
    choosing_tracking = State()  # Новое состояние для выбора отслеживания
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


def get_tracking_kb():
    """Клавиатура выбора отслеживания"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, добавить кнопку отслеживания", callback_data="bcast_tracking_yes")],
            [InlineKeyboardButton(text="❌ Нет, отправить без кнопки", callback_data="bcast_tracking_no")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="bcast_cancel")]
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
    
    # Переходим к выбору отслеживания
    await msg.answer(
        "✅ Контент получен!\n\n"
        "❓ Хотите добавить кнопку отслеживания?\n\n"
        "ℹ️ Кнопка «Прочитал(-а) ✅» позволит отслеживать, кто увидел рассылку.\n"
        "Пользователи смогут нажать на неё после прочтения.",
        reply_markup=get_tracking_kb()
    )
    await state.set_state(Broadcast.choosing_tracking)


# --- Выбор отслеживания ---
@router.callback_query(F.data.in_(["bcast_tracking_yes", "bcast_tracking_no"]), Broadcast.choosing_tracking)
async def choose_tracking(callback: CallbackQuery, state: FSMContext):
    add_tracking = callback.data == "bcast_tracking_yes"
    await state.update_data(add_tracking=add_tracking)
    
    await callback.message.edit_text(
        "✅ Настройка отслеживания сохранена!\n\n"
        "Выберите тип рассылки:",
        reply_markup=get_broadcast_type_kb()
    )
    await callback.answer()
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
    add_tracking = data.get("add_tracking", False)
    
    # Генерируем уникальный ID для этой рассылки
    broadcast_id = str(uuid.uuid4())[:8]  # Короткий ID
    
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
    
    # Создаём кнопку отслеживания если нужно
    tracking_kb = None
    if add_tracking:
        tracking_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Прочитал(-а)", callback_data=f"bcast_read_{broadcast_id}")]
            ]
        )
    
    # Отправка сообщений
    success_count = 0
    fail_count = 0
    
    for user_id in recipients:
        try:
            # Отправляем контент в зависимости от типа
            if content_type == "text":
                await bot.send_message(
                    user_id, 
                    data.get("text"),
                    reply_markup=tracking_kb
                )
            
            elif content_type == "photo" or content_type == "photo_text":
                await bot.send_photo(
                    user_id,
                    photo=data.get("photo_id"),
                    caption=data.get("caption"),
                    reply_markup=tracking_kb
                )
            
            elif content_type == "video":
                await bot.send_video(
                    user_id,
                    video=data.get("video_id"),
                    caption=data.get("caption"),
                    reply_markup=tracking_kb
                )
            
            elif content_type == "audio":
                if data.get("audio_id"):
                    await bot.send_audio(
                        user_id,
                        audio=data.get("audio_id"),
                        caption=data.get("caption"),
                        reply_markup=tracking_kb
                    )
                else:
                    await bot.send_voice(
                        user_id,
                        voice=data.get("voice_id"),
                        reply_markup=tracking_kb
                    )
            
            elif content_type == "video_note":
                # К видео-кружкам нельзя добавить inline кнопки напрямую
                # Отправляем кружок, потом текст с кнопкой если нужно
                await bot.send_video_note(
                    user_id,
                    video_note=data.get("video_note_id")
                )
                if add_tracking:
                    await bot.send_message(
                        user_id,
                        "👆 Нажмите когда просмотрите:",
                        reply_markup=tracking_kb
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
        f"📈 Всего: {success_count + fail_count}\n"
    )
    
    # Добавляем ID рассылки если было отслеживание
    if add_tracking:
        report += (
            f"\n🆔 <b>ID рассылки:</b> <code>{broadcast_id}</code>\n"
            f"ℹ️ Для просмотра статистики используйте:\n"
            f"<code>/bstats {broadcast_id}</code>"
        )
    
    await bot.send_message(callback.from_user.id, report, parse_mode="HTML")
    await state.clear()
    logger.info(f"[INFO] {broadcast_type_text} завершена. Успешно: {success_count}, Ошибок: {fail_count}")


# --- Команда /stats (статистика бота) ---
@router.message(Command("stats"))
async def show_statistics(msg: Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔️ Доступ запрещён! Только для администраторов.")
        return
    
    async for session in get_session():
        # Общее количество пользователей
        total_users_result = await session.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar()
        
        # Активные пользователи
        active_users_result = await session.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_users = active_users_result.scalar()
        
        # Неактивные пользователи
        inactive_users = total_users - active_users
        
        # Новые пользователи за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        new_today_result = await session.execute(
            select(func.count(User.id)).where(User.created_at >= yesterday)
        )
        new_today = new_today_result.scalar()
        
        # Новые пользователи за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_week_result = await session.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        new_week = new_week_result.scalar()
        
        # Новые пользователи за последние 30 дней
        month_ago = datetime.utcnow() - timedelta(days=30)
        new_month_result = await session.execute(
            select(func.count(User.id)).where(User.created_at >= month_ago)
        )
        new_month = new_month_result.scalar()
        
        # Пользователи с username
        with_username_result = await session.execute(
            select(func.count(User.id)).where(User.username.isnot(None))
        )
        with_username = with_username_result.scalar()
        
        # Последние 5 пользователей
        latest_users_result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(5)
        )
        latest_users = latest_users_result.scalars().all()
    
    # Формируем отчёт
    stats_text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users}\n"
        f"✅ <b>Активных:</b> {active_users}\n"
        f"❌ <b>Неактивных:</b> {inactive_users}\n\n"
        f"📈 <b>Динамика:</b>\n"
        f"🆕 За 24 часа: {new_today}\n"
        f"📅 За неделю: {new_week}\n"
        f"📆 За месяц: {new_month}\n\n"
        f"👤 <b>С username:</b> {with_username} ({round(with_username/total_users*100 if total_users > 0 else 0, 1)}%)\n\n"
    )
    
    # Добавляем последних пользователей
    if latest_users:
        stats_text += "🆕 <b>Последние 5 пользователей:</b>\n"
        for i, user in enumerate(latest_users, 1):
            username_display = f"@{user.username}" if user.username else "без username"
            name = user.first_name or "Без имени"
            date = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "—"
            stats_text += f"{i}. {name} ({username_display}) - {date}\n"
    
    await msg.answer(stats_text, parse_mode="HTML")
    logger.info(f"[INFO] Пользователь {msg.from_user.id} запросил статистику")


# --- Обработка нажатия на кнопку "Прочитал(-а)" ---
@router.callback_query(F.data.startswith("bcast_read_"))
async def track_read(callback: CallbackQuery):
    # Извлекаем ID рассылки из callback_data
    broadcast_id = callback.data.replace("bcast_read_", "")
    user_id = callback.from_user.id
    
    # Сохраняем взаимодействие в БД
    async for session in get_session():
        # Проверяем, не нажимал ли уже пользователь
        existing = await session.execute(
            select(BroadcastInteraction).where(
                BroadcastInteraction.user_id == user_id,
                BroadcastInteraction.broadcast_id == broadcast_id,
                BroadcastInteraction.action == "read"
            )
        )
        if existing.scalar_one_or_none():
            await callback.answer("✅ Вы уже отметили это сообщение как прочитанное!", show_alert=False)
            return
        
        # Создаём новую запись
        interaction = BroadcastInteraction(
            user_id=user_id,
            broadcast_id=broadcast_id,
            action="read"
        )
        session.add(interaction)
        await session.commit()
    
    # Обновляем кнопку
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Прочитано", callback_data="already_read")]
            ]
        )
    )
    await callback.answer("✅ Спасибо! Отмечено как прочитанное.", show_alert=False)
    logger.info(f"[INFO] Пользователь {user_id} отметил рассылку {broadcast_id} как прочитанную")


@router.callback_query(F.data == "already_read")
async def already_read(callback: CallbackQuery):
    await callback.answer("✅ Уже отмечено как прочитанное", show_alert=False)


# --- Команда просмотра статистики рассылки ---
@router.message(Command("bstats"))
async def broadcast_stats(msg: Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔️ Доступ запрещён! Только для администраторов.")
        return
    
    # Получаем ID рассылки из команды, например: /bstats abc123
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer(
            "❗️ Использование: /bstats <ID_рассылки>\n\n"
            "ID рассылки указывается в callback_data кнопки отслеживания.\n"
            "Например: /bstats abc12345"
        )
        return
    
    broadcast_id = args[1]
    
    async for session in get_session():
        # Получаем всех кто прочитал
        result = await session.execute(
            select(BroadcastInteraction).where(
                BroadcastInteraction.broadcast_id == broadcast_id,
                BroadcastInteraction.action == "read"
            )
        )
        interactions = result.scalars().all()
        
        if not interactions:
            await msg.answer(
                f"❌ Нет данных по рассылке с ID: <code>{broadcast_id}</code>\n\n"
                "Возможно, рассылка была без кнопки отслеживания или никто ещё не нажал на кнопку.",
                parse_mode="HTML"
            )
            return
        
        # Получаем информацию о пользователях
        read_count = len(interactions)
        user_ids = [i.user_id for i in interactions]
        
        # Получаем общее количество активных пользователей (потенциальных получателей)
        total_users_result = await session.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        total_users = total_users_result.scalar()
        
        # Формируем список прочитавших
        users_info = []
        for interaction in interactions[:10]:  # Показываем первых 10
            user_result = await session.execute(
                select(User).where(User.tg_id == interaction.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                username = f"@{user.username}" if user.username else "без username"
                name = user.first_name or "Без имени"
                read_time = interaction.created_at.strftime("%d.%m %H:%M") if interaction.created_at else "—"
                users_info.append(f"• {name} ({username}) - {read_time}")
    
    percentage = round(read_count / total_users * 100, 1) if total_users > 0 else 0
    
    stats_text = (
        f"📊 <b>Статистика рассылки</b>\n"
        f"🆔 ID: <code>{broadcast_id}</code>\n\n"
        f"✅ <b>Прочитали:</b> {read_count} из {total_users} ({percentage}%)\n"
        f"❌ <b>Не прочитали:</b> {total_users - read_count}\n\n"
    )
    
    if users_info:
        stats_text += "<b>Последние прочитавшие:</b>\n" + "\n".join(users_info)
        if read_count > 10:
            stats_text += f"\n\n... и ещё {read_count - 10} пользователей"
    
    await msg.answer(stats_text, parse_mode="HTML")
    logger.info(f"[INFO] Пользователь {msg.from_user.id} запросил статистику рассылки {broadcast_id}")

