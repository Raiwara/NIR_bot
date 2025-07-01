# handlers/misc.py

import json
from aiogram import F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database import create_db_connection
import keyboards


class MiscStates(StatesGroup):
    WAITING_DELETE_CONFIRM = State()
    WAITING_USER_SELECTION = State()


def register_handlers(dp):
    # Показать свободные темы
    dp.message(F.text == '📚 Свободные темы')(show_free_topics)

    # Удалить свой аккаунт
    dp.message(F.text == '🗑 Удалить аккаунт')(delete_account_start)
    dp.message(F.text == '❌ Отмена', MiscStates.WAITING_DELETE_CONFIRM)(cancel_handler)
    dp.message(MiscStates.WAITING_DELETE_CONFIRM)(process_delete_confirm)

    # Просмотр профиля
    dp.message(F.text == '👤 Просмотр профиля')(view_data_start)
    dp.message(F.text == '❌ Отмена', MiscStates.WAITING_USER_SELECTION)(cancel_handler)
    dp.message(MiscStates.WAITING_USER_SELECTION)(process_user_selection)

    # Универсальная отмена
    dp.message(F.text == '❌ Отмена')(cancel_handler)


async def show_free_topics(message: Message):
    conn = await create_db_connection()
    try:
        topics = await conn.fetch(
            """
            SELECT t.title, t.description, t.keywords,
                   COALESCE(te.name, 'Не назначен') AS teacher_name
              FROM Topics t
              LEFT JOIN Teachers te ON t.teacher_id = te.teacher_id
             WHERE t.status = 'free'
             ORDER BY t.title
             LIMIT 50
            """
        )
    finally:
        await conn.close()

    if not topics:
        return await message.answer("Сейчас нет свободных тем.")

    # Формируем блоки по 5 тем
    for i in range(0, len(topics), 5):
        chunk = topics[i: i + 5]
        text = "\n\n".join(
            f"📌 <b>{t['title']}</b>\n"
            f"👨🏫 Преподаватель: {t['teacher_name']}\n"
            f"🏷 Ключевые слова: {', '.join(t['keywords'])}\n"
            f"📝 Описание: {t['description'] or 'нет описания'}"
            for t in chunk
        )
        await message.answer(text, parse_mode="HTML")


async def delete_account_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton('Подтверждаю удаление')],
            [KeyboardButton('❌ Отмена')],
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Вы уверены, что хотите безвозвратно удалить все свои данные из бота?",
        reply_markup=kb
    )
    await state.set_state(MiscStates.WAITING_DELETE_CONFIRM)


async def process_delete_confirm(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if message.text.strip() == 'Подтверждаю удаление':
        conn = await create_db_connection()
        try:
            await conn.execute("DELETE FROM Students WHERE telegram_id = $1", user_id)
            await conn.execute("DELETE FROM Teachers WHERE telegram_id = $1", user_id)
        finally:
            await conn.close()

        await message.answer(
            "Ваши данные успешно удалены. Чтобы зарегистрироваться заново, нажмите /start.",
            reply_markup=keyboards.registration_kb
        )
    else:
        await return_to_main_menu(message)
    await state.clear()


async def view_data_start(message: Message, state: FSMContext):
    conn = await create_db_connection()
    try:
        # Сначала собираем преподавателей, затем студентов
        rows = await conn.fetch(
            """
            SELECT telegram_id, name, 'Преподаватель' AS role, teacher_id AS uid
              FROM Teachers
            UNION ALL
            SELECT telegram_id, name, 'Студент' AS role, student_id AS uid
              FROM Students
            ORDER BY role DESC, name
            """
        )
    finally:
        await conn.close()

    buttons = [
        [KeyboardButton(text=f"{r['role']} | {r['name']}")] for r in rows
    ]
    buttons.append([KeyboardButton(text='❌ Отмена')])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer(
        "Выберите пользователя для просмотра его профиля:",
        reply_markup=kb
    )
    await state.set_state(MiscStates.WAITING_USER_SELECTION)


async def process_user_selection(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == '❌ Отмена':
        await cancel_handler(message, state)
        return

    role, name = [part.strip() for part in text.split('|', 1)]

    conn = await create_db_connection()
    try:
        if role == 'Преподаватель':
            row = await conn.fetchrow(
                """
                SELECT name, email, phone, telegram_id,
                       (SELECT title FROM Topics WHERE teacher_id = t.teacher_id LIMIT 1) AS topic
                  FROM Teachers t
                 WHERE t.name = $1
                """,
                name
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT name, email, phone, telegram_id,
                       (SELECT title FROM Topics WHERE student_id = s.student_id LIMIT 1) AS topic
                  FROM Students s
                 WHERE s.name = $1
                """,
                name
            )
    finally:
        await conn.close()

    if row:
        await message.answer(
            "👤 <b>Профиль пользователя:</b>\n"
            f"Роль: <b>{role}</b>\n"
            f"Имя: {row['name']}\n"
            f"Email: {row['email']}\n"
            f"Телефон: {row['phone']}\n"
            f"Тема: {row['topic'] or 'нет темы'}",
            parse_mode="HTML"
        )
    else:
        await message.answer("Пользователь не найден.")

    await return_to_main_menu(message)
    await state.clear()


async def cancel_handler(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    await return_to_main_menu(message)


async def return_to_main_menu(message: Message):
    user_id = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        is_student = await conn.fetchval("SELECT 1 FROM Students WHERE telegram_id = $1", user_id)
        is_teacher = await conn.fetchval("SELECT 1 FROM Teachers WHERE telegram_id = $1", user_id)
    finally:
        await conn.close()

    if is_student:
        await message.answer("Возвращаемся в главное меню:", reply_markup=keyboards.student_kb)
    elif is_teacher:
        await message.answer("Возвращаемся в главное меню:", reply_markup=keyboards.teacher_kb)
    else:
        await message.answer("Вы не зарегистрированы.", reply_markup=keyboards.registration_kb)
