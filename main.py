import asyncio
import re
import io
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from config import API_TOKEN
from database import create_db_connection, init_db


bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Константы
TEACHER_ACCESS_CODE = "prof_code_123"
DEPARTMENT_NAME = "ЦИТХиН"

# FSM состояния
class TopicStates(StatesGroup):
    WAITING_TITLE = State()
    WAITING_DESCRIPTION = State()
    WAITING_KEYWORDS = State()

class ReserveStates(StatesGroup):
    WAITING_TITLE = State()

class UnreserveStates(StatesGroup):
    WAITING_CONFIRM = State()

# Клавиатуры
student_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📝 Предложить тему')],
        [KeyboardButton(text='🔍 Поиск темы'), KeyboardButton(text='📚 Свободные темы')],
        [KeyboardButton(text='🔄 Сменить тему')]
    ],
    resize_keyboard=True
)

teacher_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📝 Предложить тему')],
        [KeyboardButton(text='🔍 Поиск темы'), KeyboardButton(text='📚 Свободные темы')],
        [KeyboardButton(text='✅ Одобрить тему')]
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📊 Статистика по группам')],
        [KeyboardButton(text='📈 Популярные запросы')],
        [KeyboardButton(text='❌ Отмена')]
    ],
    resize_keyboard=True
)


registration_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🎓 Студент')],
        [KeyboardButton(text='👨🏫 Преподаватель')]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text='❌ Отмена')]],
    resize_keyboard=True
)

@dp.message(F.text == '📚 Свободные темы')
async def list_free_topics(message: Message, state: FSMContext):
    user_id = message.from_user.id
    conn = None
    try:
        conn = await create_db_connection()
        student_id = await conn.fetchval(
            "SELECT student_id FROM Students WHERE telegram_id = $1", str(user_id)
        )
        if not student_id:
            await message.answer("❌ Эта функция доступна только студентам!")
            return
        free_topics = await conn.fetch(
            "SELECT title FROM Topics WHERE status='free' AND department_id = ("
            "SELECT department_id FROM Students WHERE student_id=$1) LIMIT 10", student_id
        )
        if not free_topics:
            await message.answer("Свободных тем пока нет.", reply_markup=student_kb)
            return
        topics_list = '\n'.join(f"• {t['title']}" for t in free_topics)
        await message.answer(
            f"Выберите тему для закрепления (введите точное название):\n{topics_list}",
            reply_markup=cancel_kb
        )
        await state.set_state(ReserveStates.WAITING_TITLE)
    finally:
        if conn:
            await conn.close()

@dp.message(ReserveStates.WAITING_TITLE)
async def process_reserve_title(message: Message, state: FSMContext):
    title = message.text.strip()
    user_id = message.from_user.id
    conn = None
    try:
        conn = await create_db_connection()
        student_id = await conn.fetchval(
            "SELECT student_id FROM Students WHERE telegram_id=$1", str(user_id)
        )
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM Topics WHERE student_id=$1", student_id
        )
        if existing and existing > 0:
            await message.answer(
                "⚠️ У вас уже есть закрепленная тему. Сначала открепитесь от неё.",
                reply_markup=student_kb
            )
            await state.clear()
            return
        updated = await conn.fetchrow(
            """
            UPDATE Topics
            SET status='reserved', student_id=$1
            WHERE title=$2 AND status='free'
            RETURNING topic_id
            """,
            student_id, title
        )
        if not updated:
            await message.answer(
                "Тема не найдена или уже занята. Попробуйте выбрать другую.",
                reply_markup=student_kb
            )
        else:
            topic_id = updated['topic_id']
            await conn.execute(
                "INSERT INTO Interactions(student_id, topic_id, user_role, action) VALUES($1,$2,'student','reserved')",
                student_id, topic_id
            )
            await message.answer(
                f"✅ Тема «{title}» успешно закреплена за вами!", reply_markup=student_kb
            )
    finally:
        if conn:
            await conn.close()
        await state.clear()

@dp.message(F.text == '🔄 Сменить тему')
async def start_unreserve(message: Message, state: FSMContext):
    user_id = message.from_user.id
    conn = None
    try:
        conn = await create_db_connection()
        student_id = await conn.fetchval(
            "SELECT student_id FROM Students WHERE telegram_id=$1", str(user_id)
        )
        if not student_id:
            await message.answer("❌ Эта функция доступна только студентам!")
            return
        current = await conn.fetchrow(
            "SELECT title FROM Topics WHERE student_id=$1", student_id
        )
        if not current:
            await message.answer("У вас нет закреплённой темы.", reply_markup=student_kb)
            return
        title = current['title']
        yes_no_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Да'), KeyboardButton(text='Нет')],
                [KeyboardButton(text='❌ Отмена')]
            ],
            resize_keyboard=True
        )
        await message.answer(
            f"Ваша текущая тема: «{title}». Вы действительно хотите открепиться?",
            reply_markup=yes_no_kb
        )
        await state.update_data(title=title, student_id=student_id)
        await state.set_state(UnreserveStates.WAITING_CONFIRM)
    finally:
        if conn:
            await conn.close()

@dp.message(UnreserveStates.WAITING_CONFIRM)
async def process_unreserve_confirm(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    data = await state.get_data()
    title = data.get('title')
    student_id = data.get('student_id')
    conn = None
    try:
        if text == 'да':
            conn = await create_db_connection()
            await conn.execute(
                "UPDATE Topics SET status='free', student_id=NULL WHERE student_id=$1", student_id
            )
            await conn.execute(
                "INSERT INTO Interactions(student_id, topic_id, user_role, action) "
                "SELECT $1, topic_id, 'student', 'unreserved' FROM Topics WHERE title=$2",
                student_id, title
            )
            await message.answer(
                f"✅ Вы успешно открепились от темы «{title}».", reply_markup=student_kb
            )
        else:
            await message.answer("Операция отменена.", reply_markup=student_kb)
    finally:
        if conn:
            await conn.close()
        await state.clear()

async def send_group_histogram(message: Message):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            "SELECT COALESCE(group_name, 'Не указана') AS grp, COUNT(*) AS cnt "
            "FROM Students GROUP BY grp ORDER BY cnt DESC"
        )
        groups = [r['grp'] for r in rows]
        counts = [r['cnt'] for r in rows]

        # Построение гистограммы
        plt.figure(figsize=(8,4))
        plt.bar(groups, counts)
        plt.xlabel('Группа')
        plt.ylabel('Число студентов')
        plt.title('Распределение студентов по группам')
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        await bot.send_photo(message.chat.id, buf)
        plt.close()
    finally:
        await conn.close()

@dp.message(F.text == '📊 Статистика по группам')
async def cmd_group_stats(message: Message):
    await send_group_histogram(message)

@dp.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    conn = None
    try:
        conn = await create_db_connection()
        student = await conn.fetchrow("SELECT 1 FROM Students WHERE telegram_id=$1", str(user_id))
        teacher = await conn.fetchrow("SELECT 1 FROM Teachers WHERE telegram_id=$1", str(user_id))
        if student:
            await message.answer("🎓 Добро пожаловать, студент!", reply_markup=student_kb)
        elif teacher:
            await message.answer("👨🏫 Добро пожаловать, преподаватель!", reply_markup=teacher_kb)
        else:
            # ... регистрация
            pass
    finally:
        if conn:
            await conn.close()

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))