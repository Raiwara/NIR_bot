# handlers/categories.py
import json
from aiogram import F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import create_db_connection
import keyboards
from handlers.misc import cancel_handler

# Утилита логирования
async def log_action(conn, user_id: str, action: str, details: dict):
    await conn.execute(
        """
        INSERT INTO Logs(user_id, action, details)
        VALUES($1, $2, $3)
        """,
        user_id,
        action,
        json.dumps(details)
    )

# Состояния для поиска по категориям
class CatStates(StatesGroup):
    WAITING_CATEGORY    = State()
    WAITING_SUBCATEGORY = State()


def register_handlers(dp):
    dp.message(F.text == '📂 По категории')(start_cat_search)
    dp.message(F.text == '❌ Отмена', CatStates.WAITING_CATEGORY)(cancel_handler)
    dp.message(F.text == '❌ Отмена', CatStates.WAITING_SUBCATEGORY)(cancel_handler)
    dp.message(CatStates.WAITING_CATEGORY)(process_category)
    dp.message(CatStates.WAITING_SUBCATEGORY)(process_subcategory)

async def start_cat_search(message: Message, state: FSMContext):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch("SELECT category_id, name FROM Categories ORDER BY name")
    finally:
        await conn.close()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in rows:
        kb.add(KeyboardButton(text=f"{r['category_id']}|{r['name']}"))
    kb.add(KeyboardButton('❌ Отмена'))
    await message.answer("Выберите категорию:", reply_markup=kb)
    await state.set_state(CatStates.WAITING_CATEGORY)

async def process_category(message: Message, state: FSMContext):
    cat_id, cat_name = message.text.split('|', 1)
    await state.update_data(category_id=int(cat_id), category_name=cat_name)
    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            "SELECT subcategory_id, name FROM Subcategories WHERE category_id=$1 ORDER BY name",
            int(cat_id)
        )
    finally:
        await conn.close()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in rows:
        kb.add(KeyboardButton(text=f"{r['subcategory_id']}|{r['name']}"))
    kb.add(KeyboardButton('❌ Отмена'))
    await message.answer(f"Категория «{cat_name}». Выберите подкатегорию:", reply_markup=kb)
    await state.set_state(CatStates.WAITING_SUBCATEGORY)

async def process_subcategory(message: Message, state: FSMContext):
    sub_id, sub_name = message.text.split('|', 1)
    data = await state.get_data()
    conn = await create_db_connection()
    try:
        topics = await conn.fetch(
            """
            SELECT title, COALESCE(description,'—') AS desc
            FROM Topics
            WHERE subcategory_id = $1
            ORDER BY title
            """, int(sub_id)
        )
        # Логируем поиск по категории
        await log_action(
            conn,
            str(message.from_user.id),
            'search_by_category',
            {'category': data['category_name'], 'subcategory': sub_name, 'count': len(topics)}
        )
    finally:
        await conn.close()

    if not topics:
        await message.answer("Тем не найдено.", reply_markup=keyboards.student_kb)
    else:
        lines = [f"📂 Темы в подкатегории «{sub_name}»:"]
        for t in topics:
            lines.append(f"• {t['title']}")
        await message.answer("\n".join(lines), reply_markup=keyboards.student_kb)

    await state.clear()
