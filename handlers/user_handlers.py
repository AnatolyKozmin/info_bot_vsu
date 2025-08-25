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

# --- FSM состояния ---
class AskQuestion(StatesGroup):
    waiting_for_question = State()
    waiting_for_anon_choice = State()

class FAQAdmin(StatesGroup):
    action = State()  # Новое состояние для выбора действия (add, edit, delete)
    waiting_for_faq_question = State()
    waiting_for_faq_answer = State()
    waiting_for_faq_edit_id = State()
    waiting_for_faq_edit_question = State()
    waiting_for_faq_edit_answer = State()
    waiting_for_faq_delete_id = State()

# --- Клавиатуры ---
main_menu_reply_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="FAQ 📚"), KeyboardButton(text="Задать вопрос ✍️")],
        [KeyboardButton(text="О нас ℹ️")]
    ],
    resize_keyboard=True
)

admin_menu_reply_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="FAQ 📚"), KeyboardButton(text="Задать вопрос ✍️"), KeyboardButton(text="Редактировать FAQ")],
        [KeyboardButton(text="О нас ℹ️")]
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

def get_faq_inline_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="FAQ 📚", callback_data="show_faq")],
            [InlineKeyboardButton(text="Задать вопрос ✍️", callback_data="ask_question")]
        ]
    )

# --- Генерация админ-клавиатуры для FAQ ---
def get_admin_faq_list_kb(faqs):
    kb = []
    for faq in faqs:
        kb.append([
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_faq_{faq.id}"),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_faq_{faq.id}")
        ])
    kb.append([InlineKeyboardButton(text="➕ Добавить FAQ", callback_data="admin_add_faq")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

admin_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Добавить FAQ", callback_data="admin_add_faq")],
        [InlineKeyboardButton(text="Редактировать FAQ", callback_data="admin_edit_faq")],
        [InlineKeyboardButton(text="Удалить FAQ", callback_data="admin_delete_faq")],
        [InlineKeyboardButton(text="Отмена", callback_data="admin_cancel")]
    ]
)

# --- Глобальные переменные ---
reply_waiting = {}
last_question_time = {}

# --- Хендлер /start ---
@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    # Приветственный текст для пользователя
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
    # Выбор клавиатуры в зависимости от того, админ ли пользователь
    kb = admin_menu_reply_kb if msg.from_user.id in ADMINS else main_menu_reply_kb
    await msg.answer(welcome_text, parse_mode="HTML", reply_markup=kb)
    await state.clear()

# --- Хендлер "О нас" ---
@router.message(F.text == "О нас ℹ️")
async def about_reply(msg: Message):
    # Текст с информацией о контактах и медиа
    about_text = (
        "Привет, студент!\n\n"
        "Твои проблемы очень важны, и мы работаем, чтобы их решать. По всем срочным и сложным вопросам ты всегда можешь написать напрямую нам:\n\n"
        "<b>Председатель Студенческого совета факультета ВШУ</b> — @anratnikovaa\n\n"
        "<b>Заместитель Председателя по учебно-социальной деятельности</b> — @pollillixs\n\n"
        "Подписывайся на наши медиа, чтобы быть в курсе всех событий:\n\n"
        "<a href='https://vk.com/hsmedia'>HSMedia</a>\n"
        "<a href='https://vk.com/hsmedia'>Студенческий совет ВШУ | Финансовый университет</a>\n"
        "<a href='https://t.me/hsm_vshum'>ВШУм</a>"
    )
    await msg.answer(about_text, parse_mode="HTML")


@router.message(F.text == 'Редактировать FAQ')
async def admin_faq_panel(msg: Message, state: FSMContext):
    logger.info(f"[INFO] Пользователь {msg.from_user.id} открывает админ-панель FAQ через reply-кнопку: '{msg.text}'")
    if msg.from_user.id not in ADMINS:
        await msg.answer("Доступно только администраторам!")
        return
    faqs = await get_faqs()
    if not faqs:
        await msg.answer("FAQ пуст. Нечего редактировать.", reply_markup=get_admin_faq_list_kb([]))
        await state.set_state(FAQAdmin.action)
        return
    text = "<b>FAQ для редактирования:</b>\n\n"
    for i, faq in enumerate(faqs, 1):
        text += f"<b>{i}. {faq.question}</b>\n<blockquote>{faq.answer}</blockquote>\n"
    await msg.answer(text, parse_mode="HTML", reply_markup=get_admin_faq_list_kb(faqs))
    await state.set_state(FAQAdmin.action)

# --- Функция для получения списка FAQ из БД (общая для всех операций) ---
async def get_faqs():
    async for session in get_session():
        return (await session.execute(select(FAQ))).scalars().all()

# --- Функция для показа FAQ ---
async def show_faq_list(chat: Message | CallbackQuery):
    faqs = await get_faqs()
    if not faqs:
        text = "FAQ пока пуст."
    else:
        text = "<b>FAQ 📚</b>\n\n"
        for i, faq in enumerate(faqs, 1):
            text += f"<b>{i}. {faq.question}</b>\n<blockquote>{faq.answer}</blockquote>\n\n"


    if isinstance(chat, Message):
        await chat.answer(text, parse_mode="HTML")
    else:
        try:
            await chat.message.edit_text(text, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

# --- Хендлеры для просмотра FAQ ---
@router.message(F.text == "FAQ 📚")
async def faq_reply(msg: Message):
    await show_faq_list(msg)

@router.callback_query(F.data == "show_faq")
async def faq_inline(callback: CallbackQuery):
    await show_faq_list(callback)
    await callback.answer()

# --- Запуск процесса задания вопроса ---
async def start_question_flow(chat: Message | CallbackQuery, state: FSMContext, user_id: int):
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

    text = "Напишите свой вопрос:"
    kb = cancel_reply_kb if isinstance(chat, Message) else None
    if isinstance(chat, CallbackQuery):
        try:
            await chat.message.edit_text(text)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
    else:
        await chat.answer(text, reply_markup=kb)
    await state.set_state(AskQuestion.waiting_for_question)

# --- Хендлеры для начала задания вопроса ---
@router.message(F.text == "Задать вопрос ✍️")
async def ask_question_reply(msg: Message, state: FSMContext):
    await start_question_flow(msg, state, msg.from_user.id)

@router.callback_query(F.data == "ask_question")
async def ask_question_inline(callback: CallbackQuery, state: FSMContext):
    await start_question_flow(callback, state, callback.from_user.id)
    await callback.answer()

# --- Получение текста вопроса ---
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

# --- Выбор анонимности и отправка вопроса ---
@router.message(F.text.in_(["Анонимно 🤫", "Неанонимно 🙂"]), AskQuestion.waiting_for_anon_choice)
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

    head = f"<b><i>@{username} задал вопрос:</i></b> 🤔" if is_anon else f"<b><i>{msg.from_user.full_name} (@{username}) задал вопрос:</i></b> 🤔"
    text = f'{head}\n\n<blockquote>{question}</blockquote>'
    sent = await bot.send_message(GROUP_CHAT_ID, text, reply_markup=get_reply_kb(question_id), parse_mode="HTML")

    async for session in get_session():
        q = await session.get(Question, question_id)
        q.group_message_id = sent.message_id
        await session.commit()

    await msg.answer("Вопрос отправлен в группу!", reply_markup=main_menu_reply_kb)
    await state.clear()

# --- Ответ на вопрос (админ) ---
@router.callback_query(F.data.startswith("reply_"))
async def reply_btn(callback: CallbackQuery, bot):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Только админ может отвечать на вопросы!", show_alert=True)
        return
    question_id = int(callback.data.split('_')[1])
    reply_waiting[callback.from_user.id] = question_id
    await bot.send_message(
        callback.from_user.id,
        f"Введите ваш ответ на вопрос (ID: {question_id}) или нажмите Отмена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"cancel_reply_{question_id}")]]
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_reply_"))
async def cancel_reply(callback: CallbackQuery):
    reply_waiting.pop(callback.from_user.id, None)
    await callback.message.edit_text("Отмена ответа.")
    await callback.answer()


@router.message(StateFilter(None))
async def get_reply_text(msg: Message, state: FSMContext, bot):
    if msg.chat.type != ChatType.PRIVATE or msg.from_user.id not in ADMINS:
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
        user_id,
        f"Вам ответили на ваш вопрос:\n\n<blockquote>{q.question}</blockquote>\n\n<b>Ответ:</b> {answer_text}",
        parse_mode="HTML"
    )

    await bot.edit_message_text(
        GROUP_CHAT_ID,
        group_message_id,
        f"<b>Отвечено ✅</b>\n\nВопрос:\n<blockquote>{q.question}</blockquote>\n\nОтвет:\n<blockquote>{answer_text}</blockquote>\n<b>Ответил:</b> @{answer_username}",
        parse_mode="HTML"
    )

    await msg.answer("Ответ отправлен и сообщение в группе обновлено!")
    reply_waiting.pop(msg.from_user.id, None)
    await state.clear()


# --- Перезадание вопроса ---
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


# --- Открытие админ-панели FAQ ---


@router.callback_query(F.data == "admin_edit_faq")
async def admin_edit_faq_callback(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[INFO] Пользователь {callback.from_user.id} открывает админ-панель FAQ через inline-кнопку")
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступно только администраторам!", show_alert=True)
        return
    await callback.message.edit_text("Выберите действие в админ-панели FAQ:", reply_markup=admin_menu_kb)
    await state.set_state(FAQAdmin.action)
    await callback.answer()


# --- Отмена админ-действий ---
@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Действие отменено.")
    await state.clear()
    await callback.answer()


# --- Добавление FAQ ---
@router.callback_query(F.data == "admin_add_faq", FAQAdmin.action)
async def admin_add_faq(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[INFO] Пользователь {callback.from_user.id} начинает добавление FAQ")
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступ запрещён!", show_alert=True)
        return
    await callback.message.edit_text("Введите вопрос для нового FAQ:")
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
    await msg.answer("FAQ успешно добавлен!", reply_markup=admin_menu_kb)
    await state.set_state(FAQAdmin.action)  # Возврат в панель


# --- Редактирование FAQ ---
# --- Индивидуальное редактирование FAQ по inline-кнопке ---
@router.callback_query(F.data.startswith("edit_faq_"), FAQAdmin.action)
async def edit_faq_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступ запрещён!", show_alert=True)
        return
    try:
        faq_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("Некорректный ID FAQ!", show_alert=True)
        return
    async for session in get_session():
        faq = await session.get(FAQ, faq_id)
        if not faq:
            await callback.answer("FAQ не найден!", show_alert=True)
            return
    await state.update_data(faq_edit_id=faq.id, current_question=faq.question, current_answer=faq.answer)
    await callback.message.edit_text(f"Введите новый вопрос (текущий: {faq.question}) или '-' для пропуска:")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_question)
    await callback.answer()


# --- Индивидуальное удаление FAQ по inline-кнопке ---
@router.callback_query(F.data.startswith("delete_faq_"), FAQAdmin.action)
async def delete_faq_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступ запрещён!", show_alert=True)
        return
    try:
        faq_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("Некорректный ID FAQ!", show_alert=True)
        return
    async for session in get_session():
        faq = await session.get(FAQ, faq_id)
        if not faq:
            await callback.answer("FAQ не найден!", show_alert=True)
            return
        await session.delete(faq)
        await session.commit()
    await callback.message.edit_text("FAQ успешно удалён!", reply_markup=admin_menu_kb)
    await state.set_state(FAQAdmin.action)
    await callback.answer()


@router.callback_query(F.data == "admin_edit_faq", FAQAdmin.action)
async def admin_edit_faq(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[INFO] Пользователь {callback.from_user.id} начинает редактирование FAQ")
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступ запрещён!", show_alert=True)
        return
    faqs = await get_faqs()
    if not faqs:
        await callback.message.edit_text("FAQ пуст. Нечего редактировать.")
        await callback.answer()
        await state.set_state(FAQAdmin.action)
        return
    text = "<b>Выберите номер FAQ для редактирования:</b>\n"
    for i, faq in enumerate(faqs, 1):
        text += f"{i}. {faq.question}\n"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_id)
    await callback.answer()


@router.message(FAQAdmin.waiting_for_faq_edit_id)
async def admin_edit_faq_id(msg: Message, state: FSMContext):
    try:
        faq_num = int(msg.text)
    except ValueError:
        await msg.answer("Введите корректный номер FAQ!")
        return
    faqs = await get_faqs()
    if not (1 <= faq_num <= len(faqs)):
        await msg.answer("Такого FAQ нет!")
        return
    faq = faqs[faq_num - 1]
    await state.update_data(faq_edit_id=faq.id, current_question=faq.question, current_answer=faq.answer)
    await msg.answer(f"Введите новый вопрос (текущий: {faq.question}) или '-' для пропуска:")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_question)


@router.message(FAQAdmin.waiting_for_faq_edit_question)
async def admin_edit_faq_question(msg: Message, state: FSMContext):
    new_question = msg.text if msg.text != "-" else (await state.get_data()).get("current_question")
    await state.update_data(faq_edit_question=new_question)
    await msg.answer(f"Введите новый ответ (текущий: {(await state.get_data()).get('current_answer')}) или '-' для пропуска:")
    await state.set_state(FAQAdmin.waiting_for_faq_edit_answer)


@router.message(FAQAdmin.waiting_for_faq_edit_answer)
async def admin_edit_faq_answer(msg: Message, state: FSMContext):
    data = await state.get_data()
    faq_id = data.get("faq_edit_id")
    new_question = data.get("faq_edit_question")
    new_answer = msg.text if msg.text != "-" else data.get("current_answer")
    async for session in get_session():
        faq = await session.get(FAQ, faq_id)
        faq.question = new_question
        faq.answer = new_answer
        await session.commit()
    await msg.answer("FAQ успешно обновлён!", reply_markup=admin_menu_kb)
    await state.set_state(FAQAdmin.action)  # Возврат в панель


# --- Удаление FAQ ---
@router.callback_query(F.data == "admin_delete_faq", FAQAdmin.action)
async def admin_delete_faq(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[INFO] Пользователь {callback.from_user.id} начинает удаление FAQ")
    if callback.from_user.id not in ADMINS:
        await callback.answer("Доступ запрещён!", show_alert=True)
        return
    faqs = await get_faqs()
    if not faqs:
        await callback.message.edit_text("FAQ пуст. Нечего удалять.")
        await callback.answer()
        await state.set_state(FAQAdmin.action)
        return
    text = "<b>Выберите номер FAQ для удаления:</b>\n"
    for i, faq in enumerate(faqs, 1):
        text += f"{i}. {faq.question}\n"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(FAQAdmin.waiting_for_faq_delete_id)
    await callback.answer()


@router.message(FAQAdmin.waiting_for_faq_delete_id)
async def admin_delete_faq_id(msg: Message, state: FSMContext):
    try:
        faq_num = int(msg.text)
    except ValueError:
        await msg.answer("Введите корректный номер FAQ!")
        return
    faqs = await get_faqs()
    if not (1 <= faq_num <= len(faqs)):
        await msg.answer("Такого FAQ нет!")
        return
    faq = faqs[faq_num - 1]
    async for session in get_session():
        await session.delete(faq)
        await session.commit()
    await msg.answer("FAQ успешно удалён!", reply_markup=admin_menu_kb)
    await state.set_state(FAQAdmin.action)  # Возврат в панель

