# handlers/search.py
import json
from aiogram import F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import create_db_connection
import keyboards

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

class SearchStates(StatesGroup):
    WAITING_KEYWORDS = State()
    WAITING_TITLE    = State()
    WAITING_TEACHER  = State()

def register_handlers(dp):
    dp.message(F.text == '🔍 Поиск темы')(search_topic_start)

    # Отмена
    dp.message(F.text == '❌ Отмена', SearchStates.WAITING_KEYWORDS)(cancel_search)
    dp.message(F.text == '❌ Отмена', SearchStates.WAITING_TITLE)(cancel_search)
    dp.message(F.text == '❌ Отмена', SearchStates.WAITING_TEACHER)(cancel_search)

    # Ветки поиска
    dp.message(F.text == "🔎 По ключевым словам")(search_by_keywords_start)
    dp.message(SearchStates.WAITING_KEYWORDS)(process_search_by_keywords)

    dp.message(F.text == "📖 По названию")(search_by_title_start)
    dp.message(SearchStates.WAITING_TITLE)(process_search_by_title)

    dp.message(F.text == "👨🏫 По преподавателю")(search_by_teacher_start)
    dp.message(SearchStates.WAITING_TEACHER)(process_search_by_teacher)


async def search_topic_start(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 По ключевым словам")],
            [KeyboardButton(text="📖 По названию")],
            [KeyboardButton(text="👨🏫 По преподавателю")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите тип поиска:", reply_markup=kb)


async def cancel_search(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        is_student = await conn.fetchval(
            "SELECT 1 FROM Students WHERE telegram_id = $1", user_id
        )
    finally:
        await conn.close()

    kb = keyboards.student_kb if is_student else keyboards.teacher_kb
    await message.answer("Поиск отменён.", reply_markup=kb)


# ---- По ключевым словам ----

async def search_by_keywords_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Введите ключевые слова через запятую:", reply_markup=kb)
    await state.set_state(SearchStates.WAITING_KEYWORDS)


async def process_search_by_keywords(message: Message, state: FSMContext):
    keywords = [kw.strip().lower() for kw in message.text.split(',') if kw.strip()]
    if not keywords:
        return await message.answer("Введите хотя бы одно ключевое слово:")

    conn = await create_db_connection()
    try:
        # Собираем темы вместе с данными о студенте
        conditions = []
        params     = []
        for i, kw in enumerate(keywords, start=1):
            conditions.append(f"LOWER(k) LIKE ${i}")
            params.append(f"%{kw}%")

        sql = f"""
            SELECT
              t.title,
              t.description,
              t.keywords,
              COALESCE(te.name, 'Не назначен')     AS teacher_name,
              COALESCE(s.name, '—')                AS student_name,
              t.status
            FROM Topics t
            LEFT JOIN Teachers te ON t.teacher_id = te.teacher_id
            LEFT JOIN Students s ON t.student_id = s.student_id
            WHERE EXISTS (
                SELECT 1 FROM unnest(t.keywords) AS k
                WHERE {' OR '.join(conditions)}
            )
            ORDER BY t.title
            LIMIT 50
        """
        topics = await conn.fetch(sql, *params)

        # Логируем
        await log_action(
            conn,
            str(message.from_user.id),
            'search_by_keywords',
            {'keywords': keywords, 'count': len(topics)}
        )
    finally:
        await conn.close()

    if not topics:
        return await message.answer("Темы не найдены по ключевым словам.")

    text = ["🔍 Найденные темы:"]
    for t in topics:
        kws = ", ".join(t['keywords'])
        text.append(
            f"\n📌 <b>{t['title']}</b>\n"
            f"👨🏫 {t['teacher_name']}\n"
            f"👤 {t['student_name']}\n"
            f"🏷 {kws}\n"
            f"📝 {t['description'] or 'нет описания'}\n"
            f"🔹 {t['status']}"
        )
    await message.answer("\n".join(text), parse_mode="HTML")
    await state.clear()


# ---- По названию ----

async def search_by_title_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Введите часть названия темы:", reply_markup=kb)
    await state.set_state(SearchStates.WAITING_TITLE)


async def process_search_by_title(message: Message, state: FSMContext):
    term = message.text.strip().lower()
    if len(term) < 3:
        return await message.answer("Введите минимум 3 символа:")

    conn = await create_db_connection()
    try:
        topics = await conn.fetch(
            """
            SELECT
              t.title,
              t.description,
              t.keywords,
              COALESCE(te.name, 'Не назначен') AS teacher_name,
              COALESCE(s.name, '—')             AS student_name,
              t.status
            FROM Topics t
            LEFT JOIN Teachers te ON t.teacher_id = te.teacher_id
            LEFT JOIN Students s ON t.student_id = s.student_id
            WHERE LOWER(t.title) LIKE $1
            ORDER BY t.title
            LIMIT 50
            """, f"%{term}%"
        )
        await log_action(
            conn,
            str(message.from_user.id),
            'search_by_title',
            {'term': term, 'count': len(topics)}
        )
    finally:
        await conn.close()

    if not topics:
        return await message.answer("Темы не найдены по названию.")

    text = ["🔍 Найденные темы:"]
    for t in topics:
        kws = ", ".join(t['keywords'])
        text.append(
            f"\n📌 <b>{t['title']}</b>\n"
            f"👨🏫 {t['teacher_name']}\n"
            f"👤 {t['student_name']}\n"
            f"🏷 {kws}\n"
            f"📝 {t['description'] or 'нет описания'}\n"
            f"🔹 {t['status']}"
        )
    await message.answer("\n".join(text), parse_mode="HTML")
    await state.clear()


# ---- По преподавателю ----

async def search_by_teacher_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Введите фамилию преподавателя:", reply_markup=kb)
    await state.set_state(SearchStates.WAITING_TEACHER)


async def process_search_by_teacher(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        return await message.answer("Введите минимум 2 символа:")

    conn = await create_db_connection()
    try:
        topics = await conn.fetch(
            """
            SELECT
              t.title,
              t.description,
              t.keywords,
              te.name AS teacher_name,
              COALESCE(s.name, '—') AS student_name,
              t.status
            FROM Topics t
            JOIN Teachers te ON t.teacher_id = te.teacher_id
            LEFT JOIN Students s ON t.student_id = s.student_id
            WHERE te.name ILIKE $1
            ORDER BY t.title
            LIMIT 50
            """, f"%{name}%"
        )
        await log_action(
            conn,
            str(message.from_user.id),
            'search_by_teacher',
            {'name': name, 'count': len(topics)}
        )
    finally:
        await conn.close()

    if not topics:
        return await message.answer("Темы не найдены по преподавателю.")

    text = ["🔍 Найденные темы:"]
    for t in topics:
        kws = ", ".join(t['keywords'])
        text.append(
            f"\n📌 <b>{t['title']}</b>\n"
            f"👨🏫 {t['teacher_name']}\n"
            f"👤 {t['student_name']}\n"
            f"🏷 {kws}\n"
            f"📝 {t['description'] or 'нет описания'}\n"
            f"🔹 {t['status']}"
        )
    await message.answer("\n".join(text), parse_mode="HTML")
    await state.clear()
