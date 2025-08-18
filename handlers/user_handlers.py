from sqlalchemy.future import select
from database.engine import get_session
from database.models import Question, FAQ
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.enums import ChatType
from config import settings
import logging
import time
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

GROUP_CHAT_ID = settings.GROUP_CHAT_ID
ADMINS = settings.ADMINS

# --- FSM ---
class AskQuestion(StatesGroup):
    waiting_for_question = State()
    waiting_for_anon_choice = State()

class FAQAdmin(StatesGroup):
    waiting_for_faq_question = State()
    waiting_for_faq_answer = State()
    waiting_for_faq_edit_id = State()
    waiting_for_faq_edit_question = State()
    waiting_for_faq_edit_answer = State()
    waiting_for_faq_delete_id = State()

# --- Клавиатуры ---
main_menu_reply_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="FAQ 📚"), KeyboardButton(text="Задать вопрос ✍️")]
    ],
    resize_keyboard=True
)

admin_menu_reply_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="FAQ 📚"), KeyboardButton(text="Задать вопрос ✍️"), KeyboardButton(text="Редактировать FAQ")]
    ],
    resize_keyboard=True
)

cancel_reply_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Отмена")]],
    resize_keyboard=True,
    one_time_keyboard=True
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
    
    return InlineKeyboardMarkup(inline_keyboard=kb)

admin_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Добавить FAQ", callback_data="admin_add_faq")],
        [InlineKeyboardButton(text="Редактировать FAQ", callback_data="admin_edit_faq")],
        [InlineKeyboardButton(text="Удалить FAQ", callback_data="admin_delete_faq")]
    ]
)

# --- Глобальные словари ---
reply_waiting = {}
last_question_time = {}

# --- /start ---
@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    welcome_text = (
        "Привет, студент!\n\n"
        "Этот бот был создан <b>Студенческим советом ВШУ Х ЦТ ИК</b>, чтобы сделать твоё обучение комфортнее. Здесь ты можешь:\n\n"
        "— <b>задать вопрос по учёбе</b>;\n"
        "— <b>сообщить о поломке в корпусе</b> (сломанная мебель, неработающий свет и др.);\n"
        "— <b>поделиться проблемой, связанной с учебным процессом</b> (некорректное поведение преподавателя, аттестация, экзамены и др.).\n\n"
        "📌 <i>Просто выбери нужную опцию в меню и напиши свой вопрос, а мы постараемся помочь. Ответ придёт в течение 2-х дней.</i>\n\n"
        "❗️В случае использования нецензурной лексики, оскорблений, некорректных формулировок или предоставления ложной информации, сообщение будет заблокировано, и ответа не последует.\n"
        "❗️Бот гарантирует полную конфиденциальность и анонимность при выборе этой опции.\n\n"
        "<i>Твой вклад важен — вместе мы сделаем учёбу комфортнее!</i>"
    )
    if msg.from_user.id in ADMINS:
        await msg.answer(welcome_text, parse_mode="HTML", reply_markup=admin_menu_reply_kb)
    else:
        await msg.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu_reply_kb)
    await state.clear()

# --- FAQ ---
async def show_faq_list(chat, is_admin=False):
    async for session in get_session():
        faqs = (await session.execute(select(FAQ))).scalars().all()

    if not faqs:
        text = "FAQ пока пуст."
        if isinstance(chat, Message):
            if is_admin:
                await chat.answer(text, reply_markup=get_faq_inline_kb(is_admin))
            else:
                await chat.answer(text)
        else:
            try:
                if is_admin:
                    await chat.message.edit_text(text, reply_markup=get_faq_inline_kb(is_admin))
                else:
                    await chat.message.edit_text(text)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    raise
        return

    text = "<b>FAQ 📚</b>\n\n"
    for i, faq in enumerate(faqs, 1):
        text += f"<b>{i}. {faq.question}</b>\n<blockquote>{faq.answer}</blockquote>\n\n"

    if isinstance(chat, Message):
        if is_admin:
            await chat.answer(text, parse_mode="HTML", reply_markup=get_faq_inline_kb(is_admin))
        else:
            await chat.answer(text, parse_mode="HTML")
    else:
        try:
            if is_admin:
                await chat.message.edit_text(text, parse_mode="HTML", reply_markup=get_faq_inline_kb(is_admin))
            else:
                await chat.message.edit_text(text, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

@router.message(lambda msg: msg.text == "FAQ 📚")
async def faq_reply(msg: Message):
    is_admin = msg.from_user.id in ADMINS
    await show_faq_list(msg, is_admin=is_admin)

@router.callback_query(F.data == "show_faq")
async def faq_inline(callback: CallbackQuery):
    await show_faq_list(callback, callback.from_user.id in ADMINS)
    await callback.answer()

# --- Задать вопрос ---
async def start_question_flow(chat, state: FSMContext, user_id: int):
    now = time.time()
    last_time = last_question_time.get(user_id, 0)

    if now - last_time < 60:
        text = f"Можно задать вопрос раз в минуту! Подождите ещё {int(60 - (now - last_time))} сек."
        if isinstance(chat, CallbackQuery):
            await chat.answer(text, show_alert=True)
        else:
            await chat.answer(text)
        return

    last_question_time[user_id] = now
    if isinstance(chat, CallbackQuery):
        try:
            await chat.message.edit_text("Напишите свой вопрос:")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
    else:
        await chat.answer("Напишите свой вопрос:", reply_markup=cancel_reply_kb)

    await state.set_state(AskQuestion.waiting_for_question)

@router.message(lambda msg: msg.text == "Задать вопрос ✍️")
async def ask_question_reply(msg: Message, state: FSMContext):
    await start_question_flow(msg, state, msg.from_user.id)

@router.callback_query(F.data == "ask_question")
async def ask_question_inline(callback: CallbackQuery, state: FSMContext):
    await start_question_flow(callback, state, callback.from_user.id)
    await callback.answer()

@router.message(AskQuestion.waiting_for_question)
async def get_question(msg: Message, state: FSMContext):
    await state.update_data(question=msg.text)
    await msg.answer("Ты хочешь задать вопрос анонимно?",
                     reply_markup=ReplyKeyboardMarkup(
                         keyboard=[
                             [KeyboardButton(text="Анонимно 🤫"), KeyboardButton(text="Неанонимно 🙂")]
                         ],
                         resize_keyboard=True
                     ))
    await state.set_state(AskQuestion.waiting_for_anon_choice)

@router.message(lambda msg: msg.text in ["Анонимно 🤫", "Неанонимно 🙂"])
async def anon_choice(msg: Message, state: FSMContext, bot):
    data = await state.get_data()
    question = data.get("question")
    is_anon = msg.text == "Анонимно 🤫"
    username = msg.from_user.username or "Без ника"
    user_id = msg.from_user.id

    async for session in get_session():
        q = Question(user_id=user_id, username=username, question=question, is_anon=is_anon)
        session.add(q)
        await session.commit()
        await session.refresh(q)
        question_id = q.id

    head = (f"<b><i>@{username} задал вопрос:</i></b> 🤔" if is_anon
            else f"<b><i>{msg.from_user.full_name} (@{username}) задал вопрос:</i></b> 🤔")
    text = f'{head}\n\n<blockquote>{question}</blockquote>'

    sent = await bot.send_message(GROUP_CHAT_ID, text, reply_markup=get_reply_kb(question_id), parse_mode="HTML")

    async for session in get_session():
        q = await session.get(Question, question_id)
        q.group_message_id = sent.message_id
        await session.commit()

    await msg.answer("Вопрос отправлен в группу!", reply_markup=main_menu_reply_kb)
    await state.clear()

# --- Ответ на вопрос ---
@router.callback_query(F.data.startswith("reply_"))
async def reply_btn(callback: CallbackQuery, state: FSMContext, bot):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Только админ может отвечать на вопросы!", show_alert=True)
        return
    question_id = int(callback.data.split('_')[1])
    reply_waiting[callback.from_user.id] = question_id
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=f"Введите ваш ответ на вопрос (ID: {question_id}) или нажмите Отмена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"cancel_reply_{question_id}")]]
        )
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_reply_"))
async def cancel_reply(callback: CallbackQuery, state: FSMContext):
    reply_waiting.pop(callback.from_user.id, None)
    await callback.message.edit_text("Отмена ответа.")
    await state.clear()

@router.message(StateFilter(None))
async def get_reply_text(msg: Message, state: FSMContext, bot):
    if msg.chat.type != ChatType.PRIVATE:
        return
    if msg.from_user.id not in ADMINS:
        return
    question_id = reply_waiting.get(msg.from_user.id)
    if not question_id:
        return

    answer_text = msg.text
    answer_username = msg.from_user.username or "Без ника"

    async for session in get_session():
        q = await session.get(Question, question_id)
        if not q:
            await msg.answer("Вопрос не найден.")
            reply_waiting.pop(msg.from_user.id, None)
            return
        q.answer = answer_text
        q.answer_user_id = msg.from_user.id
        q.answer_username = answer_username
        await session.commit()
        group_message_id = q.group_message_id
        user_id = q.user_id

    await bot.send_message(
        chat_id=user_id,
        text=f"Вам ответили на ваш вопрос:\n\n<blockquote>{q.question}</blockquote>\n\n<b>Ответ:</b> {answer_text}",
        parse_mode="HTML"
    )

    await bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=group_message_id,
        text=f"<b>Отвечено ✅</b>\n\nВопрос:\n<blockquote>{q.question}</blockquote>\n\nОтвет:\n<blockquote>{answer_text}</blockquote>\n<b>Ответил:</b> @{answer_username}",
        parse_mode="HTML"
    )

    await msg.answer("Ответ отправлен и сообщение в группе обновлено!")
    reply_waiting.pop(msg.from_user.id, None)
    await state.clear()

# --- Перезадать вопрос ---
@router.callback_query(F.data.startswith("repeat_"))
async def repeat_question(callback: CallbackQuery, bot):
    question_id = int(callback.data.split('_')[1])
    async for session in get_session():
        q = await session.get(Question, question_id)
        if not q:
            await callback.answer("Вопрос не найден", show_alert=True)
            return
        text = f"<b>Перезадаём вопрос:</b>\n\n<blockquote>{q.question}</blockquote>"
    await bot.send_message(GROUP_CHAT_ID, text, reply_markup=get_reply_kb(question_id), parse_mode="HTML")
    await callback.answer("Вопрос перезадан!")

# --- Админ-панель ---
@router.callback_query(F.data == "admin_panel")
async def admin_panel_btn(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer()
        return
    await callback.message.answer("Админ-панель FAQ:", reply_markup=admin_menu_kb)
    await callback.answer()

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

# --- DEBUG ---
@router.message()
async def debug_log(msg: Message):
    logger.info(f"[DEBUG] user_id={msg.from_user.id}, text={msg.text!r}, state={msg.chat.type}")

@router.message(lambda msg: msg.text == "Редактировать FAQ")
async def admin_edit_faq_reply(msg: Message):
    if msg.from_user.id not in ADMINS:
        return
    await msg.answer("Админ-панель FAQ:", reply_markup=admin_menu_kb)
