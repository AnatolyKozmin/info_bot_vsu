from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.engine import get_session
from database.models import Question, FAQ
from aiogram import Router, F
import time
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandStart, StateFilter
from config import settings
from aiogram.enums import ChatType

router = Router()

GROUP_CHAT_ID = settings.GROUP_CHAT_ID
ADMINS = settings.ADMINS


class AskQuestion(StatesGroup):
    waiting_for_question = State()
    waiting_for_anon_choice = State()
    waiting_for_answer = State()
    waiting_for_reply_text = State()
    waiting_for_reply_id = State()

class FAQAdmin(StatesGroup):
    waiting_for_faq_question = State()
    waiting_for_faq_answer = State()
    waiting_for_faq_edit_id = State()
    waiting_for_faq_edit_question = State()
    waiting_for_faq_edit_answer = State()
    waiting_for_faq_delete_id = State()

anon_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Анонимно 🤫", callback_data="ask_anon"),
            InlineKeyboardButton(text="Неанонимно 🙂", callback_data="ask_not_anon")
        ]
    ]
)

def get_reply_kb(question_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ответить ✉️", callback_data=f"reply_{question_id}"),
                InlineKeyboardButton(text="Перезадать 🔄", callback_data=f"repeat_{question_id}")
            ]
        ]
    )

def get_faq_inline_kb(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="FAQ 📚", callback_data="show_faq")],
        [InlineKeyboardButton(text="Задать вопрос ✍️", callback_data="ask_question")]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="Редактировать FAQ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Глобальный словарь: user_id -> question_id (для ответов в ЛС)
reply_waiting = {}

# Глобальный словарь: user_id -> время последнего вопроса (timestamp)
last_question_time = {}

# Клавиатура главного меню
main_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="FAQ 📚", callback_data="show_faq")],
        [InlineKeyboardButton(text="Задать вопрос ✍️", callback_data="ask_question")]
    ]
)

# Клавиатура отмены для вопроса
cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_ask")]
    ]
)

admin_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Добавить FAQ", callback_data="admin_add_faq")],
        [InlineKeyboardButton(text="Редактировать FAQ", callback_data="admin_edit_faq")],
        [InlineKeyboardButton(text="Удалить FAQ", callback_data="admin_delete_faq")]
    ]
)

# Клавиатура после отправки вопроса
after_question_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Задать ещё ✍️", callback_data="ask_question")],
        [InlineKeyboardButton(text="FAQ 📚", callback_data="show_faq")]
    ]
)

@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    is_admin = msg.from_user.id in ADMINS
    await msg.answer(
        "Добро пожаловать! Выберите действие:",
        reply_markup=get_faq_inline_kb(is_admin)
    )
    await state.clear()

@router.callback_query(F.data == "admin_panel")
async def admin_panel_btn(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer()
        return
    await callback.message.answer("Админ-панель FAQ:", reply_markup=admin_menu_kb)
    await callback.answer()

@router.callback_query(F.data == "ask_question")
async def ask_question_btn(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    now = time.time()
    last_time = last_question_time.get(user_id, 0)
    if now - last_time < 60:
        await callback.answer(f"Можно задать вопрос раз в минуту! Подождите ещё {int(60 - (now - last_time))} сек.", show_alert=True)
        return
    last_question_time[user_id] = now
    await callback.message.edit_text("Напишите свой вопрос:", reply_markup=cancel_kb)
    await state.set_state(AskQuestion.waiting_for_question)
    await callback.answer()

@router.callback_query(F.data == "cancel_ask")
async def cancel_ask(callback: CallbackQuery, state: FSMContext):
    is_admin = callback.from_user.id in ADMINS
    await callback.message.edit_text("Ввод вопроса отменён.", reply_markup=get_faq_inline_kb(is_admin))
    await state.clear()

@router.message(Command("get_id"))
async def get_id_handler(msg: Message):
    await msg.answer(f"ID этого чата: <code>{msg.chat.id}</code>", parse_mode="HTML")

@router.message(AskQuestion.waiting_for_question)
async def get_question(msg: Message, state: FSMContext):
    await state.update_data(question=msg.text)
    await msg.answer("Ты хочешь задать вопрос анонимно?", reply_markup=anon_kb)
    await state.set_state(AskQuestion.waiting_for_anon_choice)

@router.callback_query(F.data.in_(["ask_anon", "ask_not_anon"]))
async def anon_choice(callback: CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    question = data.get("question")
    is_anon = callback.data == "ask_anon"
    username = callback.from_user.username or "Без ника"
    user_id = callback.from_user.id
    # Сохраняем вопрос в БД
    async for session in get_session():
        q = Question(user_id=user_id, username=username, question=question, is_anon=is_anon)
        session.add(q)
        await session.commit()
        await session.refresh(q)
        question_id = q.id
    # Форматирование
    if is_anon:
        head = f"<b><i>@{username} задал очередной вопрос:</i></b> 🤔"
    else:
        head = f"<b><i>{callback.from_user.full_name} (@{username}) задал очередной вопрос:</i></b> 🤔"
    text = f'{head}\n\n<blockquote>{question}</blockquote>'
    sent = await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        reply_markup=get_reply_kb(question_id),
        parse_mode="HTML"
    )
    # Сохраняем id сообщения в группе
    async for session in get_session():
        q = await session.get(Question, question_id)
        q.group_message_id = sent.message_id
        await session.commit()
    await callback.message.answer("Вопрос отправлен в группу!", reply_markup=after_question_kb)
    await state.clear()

@router.callback_query(F.data.startswith("reply_"))
async def reply_btn(callback: CallbackQuery, state: FSMContext, bot):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Только админ может отвечать на вопросы!", show_alert=True)
        return
    question_id = int(callback.data.split('_')[1])
    await state.clear()  # Сброс состояния в группе
    await callback.answer()
    # Сохраняем, что этот пользователь ожидает ответ в ЛС
    reply_waiting[callback.from_user.id] = question_id
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=f"Введите ваш ответ на вопрос (ID: {question_id}) или нажмите Отмена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"cancel_reply_{question_id}")]]
        )
    )

@router.callback_query(F.data.startswith("cancel_reply_"))
async def cancel_reply(callback: CallbackQuery, state: FSMContext):
    reply_waiting.pop(callback.from_user.id, None)
    await callback.message.edit_text("Отмена ответа.")
    await state.clear()

@router.message(StateFilter(None))
async def get_reply_text(msg: Message, state: FSMContext, bot):
    if msg.chat.type != ChatType.PRIVATE:
        return  # Не реагируем на сообщения вне лички
    if msg.from_user.id not in ADMINS:
        return  # Только админ может отвечать
    question_id = reply_waiting.get(msg.from_user.id)
    if not question_id:
        return  # Нет активного вопроса для ответа
    answer_text = msg.text
    answer_user_id = msg.from_user.id
    answer_username = msg.from_user.username or "Без ника"
    # Сохраняем ответ в БД и получаем инфу о вопросе
    async for session in get_session():
        q = await session.get(Question, question_id)
        if not q:
            await msg.answer("Вопрос не найден.")
            reply_waiting.pop(msg.from_user.id, None)
            return
        q.answer = answer_text
        q.answer_user_id = answer_user_id
        q.answer_username = answer_username
        await session.commit()
        group_message_id = q.group_message_id
        user_id = q.user_id
    # Отправляем ответ задавшему вопрос
    await bot.send_message(
        chat_id=user_id,
        text=f"Вам ответили на ваш вопрос:\n\n<blockquote>{q.question}</blockquote>\n\n<b>Ответ:</b> {answer_text}",
        parse_mode="HTML"
    )
    # Редактируем сообщение в группе
    await bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=group_message_id,
        text=f"<b>Отвечено ✅</b>\n\nВопрос:\n<blockquote>{q.question}</blockquote>\n\nОтвет:\n<blockquote>{answer_text}</blockquote>\n<b>Ответил:</b> @{answer_username}",
        parse_mode="HTML"
    )
    await msg.answer("Ответ отправлен и сообщение в группе обновлено!")
    reply_waiting.pop(msg.from_user.id, None)
    await state.clear()

@router.callback_query(F.data.startswith("repeat_"))
async def repeat_question(callback: CallbackQuery, bot):
    question_id = int(callback.data.split('_')[1])
    # Получаем текст вопроса из БД
    async for session in get_session():
        q = await session.get(Question, question_id)
        if not q:
            await callback.answer("Вопрос не найден", show_alert=True)
            return
        text = f"<b>Перезадаём вопрос:</b>\n\n<blockquote>{q.question}</blockquote>"
    await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        reply_markup=get_reply_kb(question_id),
        parse_mode="HTML"
    )
    await callback.answer("Вопрос перезадан!")

@router.callback_query(F.data == "show_faq")
async def show_faq(callback: CallbackQuery):
    # Получаем все FAQ из БД
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()
    if not faqs:
        await callback.message.edit_text("FAQ пока пуст.", reply_markup=get_faq_inline_kb(callback.from_user.id in ADMINS))
        await callback.answer()
        return
    text = "<b>FAQ 📚</b>\n\n"
    for i, faq in enumerate(faqs, 1):
        text += f"<b>{i}. {faq.question}</b>\n<blockquote>{faq.answer}</blockquote>\n\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_faq_inline_kb(callback.from_user.id in ADMINS))
    await callback.answer()

@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMINS:
        return
    await msg.answer("Админ-панель FAQ:", reply_markup=admin_menu_kb)

@router.callback_query(F.data == "admin_add_faq")
async def admin_add_faq(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer()
        return
    await callback.message.answer("Введите вопрос для FAQ:")
    await state.set_state(FAQAdmin.waiting_for_faq_question)
    await callback.answer()

@router.message(FAQAdmin.waiting_for_faq_question)
async def admin_add_faq_question(msg: Message, state: FSMContext):
    await state.update_data(faq_question=msg.text)
    await msg.answer("Введите ответ для FAQ:")
    await state.set_state(FAQAdmin.waiting_for_faq_answer)

@router.message(FAQAdmin.waiting_for_faq_answer)
async def admin_add_faq_answer(msg: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("faq_question")
    answer = msg.text
    async for session in get_session():
        faq = FAQ(question=question, answer=answer)
        session.add(faq)
        await session.commit()
    await msg.answer("FAQ добавлен!", reply_markup=admin_menu_kb)
    await state.clear()

@router.callback_query(F.data == "admin_edit_faq")
async def admin_edit_faq(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer()
        return
    # Получаем список FAQ
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()
    if not faqs:
        await callback.message.answer("FAQ пуст.")
        await callback.answer()
        return
    text = "<b>Выберите номер FAQ для редактирования:</b>\n"
    for i, faq in enumerate(faqs, 1):
        text += f"{i}. {faq.question}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_id)
    await callback.answer()

@router.message(FAQAdmin.waiting_for_faq_edit_id)
async def admin_edit_faq_id(msg: Message, state: FSMContext):
    try:
        faq_num = int(msg.text)
    except ValueError:
        await msg.answer("Введите номер FAQ!")
        return
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()
    if not (1 <= faq_num <= len(faqs)):
        await msg.answer("Нет такого FAQ!")
        return
    faq = faqs[faq_num-1]
    await state.update_data(faq_edit_id=faq.id)
    await msg.answer(f"Введите новый вопрос для FAQ (или - чтобы не менять):\nТекущий: {faq.question}")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_question)

@router.message(FAQAdmin.waiting_for_faq_edit_question)
async def admin_edit_faq_question(msg: Message, state: FSMContext):
    data = await state.get_data()
    faq_id = data.get("faq_edit_id")
    new_question = msg.text
    async for session in get_session():
        faq = await session.get(FAQ, faq_id)
        if new_question != "-":
            faq.question = new_question
        await session.commit()
    await msg.answer("Введите новый ответ для FAQ (или - чтобы не менять):")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_answer)

@router.message(FAQAdmin.waiting_for_faq_edit_answer)
async def admin_edit_faq_answer(msg: Message, state: FSMContext):
    data = await state.get_data()
    faq_id = data.get("faq_edit_id")
    new_answer = msg.text
    async for session in get_session():
        faq = await session.get(FAQ, faq_id)
        if new_answer != "-":
            faq.answer = new_answer
        await session.commit()
    await msg.answer("FAQ обновлён!", reply_markup=admin_menu_kb)
    await state.clear()

@router.callback_query(F.data == "admin_delete_faq")
async def admin_delete_faq(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer()
        return
    # Получаем список FAQ
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()
    if not faqs:
        await callback.message.answer("FAQ пуст.")
        await callback.answer()
        return
    text = "<b>Выберите номер FAQ для удаления:</b>\n"
    for i, faq in enumerate(faqs, 1):
        text += f"{i}. {faq.question}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(FAQAdmin.waiting_for_faq_delete_id)
    await callback.answer()

@router.message(FAQAdmin.waiting_for_faq_delete_id)
async def admin_delete_faq_id(msg: Message, state: FSMContext):
    try:
        faq_num = int(msg.text)
    except ValueError:
        await msg.answer("Введите номер FAQ!")
        return
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()
    if not (1 <= faq_num <= len(faqs)):
        await msg.answer("Нет такого FAQ!")
        return
    faq = faqs[faq_num-1]
    async for session in get_session():
        await session.delete(faq)
        await session.commit()
    await msg.answer("FAQ удалён!", reply_markup=admin_menu_kb)
    await state.clear()
