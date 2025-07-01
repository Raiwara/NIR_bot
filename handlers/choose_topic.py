# handlers/choose_topic.py
from aiogram import F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import create_db_connection
import keyboards

class ChooseTopicStates(StatesGroup):
    WAITING_TITLE = State()

def register_handlers(dp):
    dp.message(F.text == '🎯 Выбираю тему')(choose_topic_start)
    dp.message(F.text == '❌ Отмена', ChooseTopicStates.WAITING_TITLE)(cancel_choose)
    dp.message(ChooseTopicStates.WAITING_TITLE)(process_choose)

    dp.callback_query(F.data.startswith("approve_choose:"))(approve_choose)
    dp.callback_query(F.data.startswith("decline_choose:"))(decline_choose)


async def choose_topic_start(message: Message, state: FSMContext):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch("""
            SELECT title, topic_id, teacher_id
            FROM Topics
            WHERE teacher_id IS NOT NULL
              AND student_id IS NULL
              AND status = 'free'
        """)
    finally:
        await conn.close()

    if not rows:
        return await message.answer(
            "Нет тем, доступных для выбора.",
            reply_markup=keyboards.student_kb
        )

    # строим клавиатуру через именованный параметр text
    buttons = [[KeyboardButton(text=r['title'])] for r in rows]
    buttons.append([KeyboardButton(text='❌ Отмена')])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    # сохраняем mapping
    await state.update_data(
        choose_map={r['title']:(r['topic_id'], r['teacher_id']) for r in rows}
    )

    await message.answer("Выберите тему:", reply_markup=kb)
    await state.set_state(ChooseTopicStates.WAITING_TITLE)


async def cancel_choose(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=keyboards.student_kb)


async def process_choose(message: Message, state: FSMContext):
    data = await state.get_data()
    mapping = data.get('choose_map', {})
    sel = message.text.strip()

    if sel not in mapping:
        await message.answer("Тема недоступна или уже выбрана.", reply_markup=keyboards.student_kb)
        return await state.clear()

    topic_id, teacher_id = mapping[sel]
    student_tg = str(message.from_user.id)

    # получаем telegram_id преподавателя
    conn = await create_db_connection()
    try:
        teacher_tg = await conn.fetchval(
            "SELECT telegram_id FROM Teachers WHERE teacher_id = $1",
            teacher_id
        )
    finally:
        await conn.close()

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_choose:{topic_id}:{student_tg}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_choose:{topic_id}:{student_tg}")
    ]])

    await message.bot.send_message(
        chat_id=int(teacher_tg),
        text=(
            f"📝 Студент @{message.from_user.username or student_tg} "
            f"хочет выбрать тему «{sel}»."
        ),
        reply_markup=markup
    )

    await message.answer("✅ Ваш запрос отправлен преподавателю.", reply_markup=keyboards.student_kb)
    await state.clear()


async def approve_choose(query: CallbackQuery):
    _, topic_id_str, student_tg = query.data.split(":")
    topic_id = int(topic_id_str)
    conn = await create_db_connection()
    try:
        await conn.execute(
            """
            UPDATE Topics
               SET student_id = (
                   SELECT student_id FROM Students WHERE telegram_id = $1
               ), status = 'closed'
             WHERE topic_id = $2
            """,
            student_tg, topic_id
        )
    finally:
        await conn.close()

    # уведомляем студента
    await query.bot.send_message(
        chat_id=int(student_tg),
        text="✅ Ваш выбор темы одобрен преподавателем."
    )
    await query.answer("Тема закреплена за студентом")


async def decline_choose(query: CallbackQuery):
    _, topic_id, student_tg = query.data.split(":")
    await query.bot.send_message(
        chat_id=int(student_tg),
        text="❌ Преподаватель отклонил ваш запрос."
    )
    await query.answer("Запрос отклонён")
