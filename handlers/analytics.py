# handlers/analytics.py
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from aiogram import F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import create_db_connection
import keyboards


class AnalyticsStates(StatesGroup):
    CHOOSING = State()
    WAITING_DEPARTMENT = State()
    WAITING_GROUP = State()


def register_handlers(dp):
    dp.message(F.text == '📈 Аналитика')(analytics_menu)
    dp.message(F.text == '❌ Отмена', AnalyticsStates.CHOOSING)(cancel)

    dp.message(F.text == '🗂 Категоризация')(analytics_start)
    dp.message(F.text == '📈 Гистограмма по кафедрам')(histogram_departments)
    dp.message(F.text == '📈 Гистограмма по группам')(histogram_groups)
    dp.message(F.text == '👥 Студенты с темой')(list_with_topic)
    dp.message(F.text == '👤 Студенты без темы')(list_without_topic)

    dp.message(AnalyticsStates.WAITING_DEPARTMENT)(process_department)
    dp.message(AnalyticsStates.WAITING_GROUP)(process_group)


async def analytics_menu(message: Message, state: FSMContext):
    conn = await create_db_connection()
    try:
        is_teacher = await conn.fetchval(
            "SELECT 1 FROM Teachers WHERE telegram_id = $1",
            str(message.from_user.id),
        )
    finally:
        await conn.close()

    if not is_teacher:
        await message.answer("⚠️ Доступно только преподавателям!")
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🗂 Категоризация')],
            [KeyboardButton(text='📈 Гистограмма по кафедрам'),
             KeyboardButton(text='📈 Гистограмма по группам')],
            [KeyboardButton(text='👥 Студенты с темой'),
             KeyboardButton(text='👤 Студенты без темы')],
            [KeyboardButton(text='❌ Отмена')],
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите отчёт по аналитике:", reply_markup=kb)
    await state.set_state(AnalyticsStates.CHOOSING)


async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Возвращаемся в главное меню.", reply_markup=keyboards.teacher_kb)


async def analytics_start(message: Message, state: FSMContext):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch("SELECT name FROM Departments ORDER BY name")
    finally:
        await conn.close()

    buttons = [[KeyboardButton(text=r['name'])] for r in rows]
    buttons.append([KeyboardButton(text='❌ Отмена')])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer("Выберите кафедру для фильтрации:", reply_markup=kb)
    await state.set_state(AnalyticsStates.WAITING_DEPARTMENT)


async def process_department(message: Message, state: FSMContext):
    dept = message.text.strip()
    await state.update_data(department=dept)

    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT group_name FROM Students "
            "WHERE department_id = (SELECT department_id FROM Departments WHERE name = $1)",
            dept
        )
    finally:
        await conn.close()

    buttons = [[KeyboardButton(text=r['group_name'])] for r in rows]
    buttons.append([KeyboardButton(text='❌ Отмена')])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer("Выберите группу для фильтрации:", reply_markup=kb)
    await state.set_state(AnalyticsStates.WAITING_GROUP)


async def process_group(message: Message, state: FSMContext):
    data = await state.get_data()
    dept = data['department']
    grp  = message.text.strip()

    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT s.name AS student_name,
                   COALESCE(t.title, '—') AS topic_title
            FROM Students s
            LEFT JOIN Topics t ON s.student_id = t.student_id
            WHERE s.department_id = (
                SELECT department_id FROM Departments WHERE name = $1
            ) AND s.group_name = $2
            ORDER BY s.name
            """,
            dept, grp
        )
    finally:
        await conn.close()

    if not rows:
        await message.answer("❌ Студентов с темами не найдено.", reply_markup=keyboards.teacher_kb)
    else:
        text = "👥 <b>Список студентов и их тем:</b>\n" + "\n".join(
            f"{r['student_name']} — {r['topic_title']}" for r in rows
        )
        await message.answer(text, parse_mode="HTML", reply_markup=keyboards.teacher_kb)

    await state.clear()


async def histogram_departments(message: Message):
    conn = await create_db_connection()
    try:
        is_teacher = await conn.fetchval(
            "SELECT 1 FROM Teachers WHERE telegram_id = $1",
            str(message.from_user.id)
        )
        if not is_teacher:
            await message.answer("⚠️ Только для преподавателей!")
            return

        rows = await conn.fetch(
            """
            SELECT d.name AS dept, COUNT(s.student_id) AS cnt
            FROM Departments d
            LEFT JOIN Students s ON d.department_id = s.department_id
            GROUP BY d.name
            ORDER BY cnt DESC
            """
        )
    finally:
        await conn.close()

    names  = [r['dept'] for r in rows]
    counts = [r['cnt']  for r in rows]
    idx    = list(range(1, len(names) + 1))

    fig, ax = plt.subplots()
    ax.bar(idx, counts, width=0.6)
    ax.set_title("Распределение студентов по кафедрам")
    ax.set_xlabel("Номер кафедры")
    ax.set_ylabel("Количество студентов")
    ax.set_xticks(idx)
    ax.set_xticklabels(idx)
    ax.set_yticks(range(0, max(counts) + 1))
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    photo = BufferedInputFile(buf.getvalue(), filename="depts.png")
    await message.answer_photo(photo, caption="📊 Студентов по кафедрам", reply_markup=keyboards.teacher_kb)

    legend = "🔢 Расшифровка:\n" + "\n".join(f"{i} — {n}: {c}" for i,n,c in zip(idx, names, counts))
    await message.answer(legend, reply_markup=keyboards.teacher_kb)


async def histogram_groups(message: Message):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT s.group_name AS grp, COUNT(*) AS cnt
            FROM Students s
            JOIN Topics t ON s.student_id = t.student_id
            WHERE t.status = 'closed'
            GROUP BY s.group_name
            ORDER BY cnt DESC
            """
        )
    finally:
        await conn.close()

    groups = [r['grp'] for r in rows]
    counts = [r['cnt'] for r in rows]
    idx    = list(range(1, len(groups) + 1))

    fig, ax = plt.subplots()
    ax.bar(idx, counts)
    ax.set_title("Студенты с одобренными темами по группам")
    ax.set_xlabel("Номер группы")
    ax.set_ylabel("Количество студентов")
    ax.set_xticks(idx)
    ax.set_xticklabels(idx, rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    photo = BufferedInputFile(buf.getvalue(), filename="groups.png")
    await message.answer_photo(photo, caption="📊 Студентов по группам", reply_markup=keyboards.teacher_kb)

    legend = "🔢 Расшифровка:\n" + "\n".join(f"{i} — {g}: {c}" for i,g,c in zip(idx, groups, counts))
    await message.answer(legend, reply_markup=keyboards.teacher_kb)


async def list_with_topic(message: Message):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT s.name, t.title
            FROM Students s
            JOIN Topics t ON s.student_id = t.student_id
            WHERE t.status = 'closed'
            ORDER BY s.name
            """
        )
    finally:
        await conn.close()

    if not rows:
        await message.answer("Нет студентов с одобренными темами.", reply_markup=keyboards.teacher_kb)
    else:
        text = "👥 Студенты с темой:\n" + "\n".join(f"{r['name']} — «{r['title']}»" for r in rows)
        await message.answer(text, reply_markup=keyboards.teacher_kb)


async def list_without_topic(message: Message):
    conn = await create_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT s.name
            FROM Students s
            LEFT JOIN Topics t ON s.student_id = t.student_id
            WHERE t.student_id IS NULL
            ORDER BY s.name
            """
        )
    finally:
        await conn.close()

    if not rows:
        await message.answer("Все студенты выбрали темы.", reply_markup=keyboards.teacher_kb)
    else:
        text = "👤 Студенты без темы:\n" + "\n".join(r['name'] for r in rows)
        await message.answer(text, reply_markup=keyboards.teacher_kb)
