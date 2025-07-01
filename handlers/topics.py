# handlers/topics.py
import json
from aiogram import F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import create_db_connection
import keyboards


# состояния для разных сценариев
class TopicStates(StatesGroup):
    WAITING_TITLE = State()
    WAITING_DESCRIPTION = State()
    WAITING_KEYWORDS = State()


class ApproveTopicStates(StatesGroup):
    WAITING_TITLE = State()


class DetachStates(StatesGroup):
    WAITING_TITLE = State()


class DeleteAccountStates(StatesGroup):
    CONFIRM = State()


async def log_action(conn, user_id: str, action: str, details: dict):
    await conn.execute(
        """
        INSERT INTO Logs(user_id, action, details)
        VALUES($1, $2, $3)
        """,
        user_id, action, json.dumps(details)
    )


def register_handlers(dp):
    # создание/предложение темы
    dp.message(F.text == '📝 Предложить тему')(suggest_topic)
    dp.message(F.text == '❌ Отмена', TopicStates.WAITING_TITLE)(cancel_topic)
    dp.message(F.text == '❌ Отмена', TopicStates.WAITING_DESCRIPTION)(cancel_topic)
    dp.message(F.text == '❌ Отмена', TopicStates.WAITING_KEYWORDS)(cancel_topic)
    dp.message(TopicStates.WAITING_TITLE)(process_title)
    dp.message(TopicStates.WAITING_DESCRIPTION)(process_description)
    dp.message(TopicStates.WAITING_KEYWORDS)(process_keywords)

    # одобрение темы (преподаватель)
    dp.message(F.text == '✅ Одобрить тему')(approve_topic_start)
    dp.message(F.text == '❌ Отмена', ApproveTopicStates.WAITING_TITLE)(cancel_approve_topic)
    dp.message(ApproveTopicStates.WAITING_TITLE)(process_approve_topic)

    # открепление от темы (студент)
    dp.message(F.text == '📤 Открепиться от темы')(detach_topic_start)
    dp.message(F.text == '❌ Отмена', DetachStates.WAITING_TITLE)(cancel_detach)
    dp.message(DetachStates.WAITING_TITLE)(process_detach)

    # удаление аккаунта
    dp.message(F.text == '🗑 Удалить аккаунт')(delete_account_start)
    dp.message(F.text == 'ПОДТВЕРЖДАЮ', DeleteAccountStates.CONFIRM)(process_delete_account)
    dp.message(F.text == 'ОТМЕНА', DeleteAccountStates.CONFIRM)(cancel_delete_account)


# --- ПРЕДЛОЖЕНИЕ ТЕМЫ ---
async def suggest_topic(message: Message, state: FSMContext):
    user_tg = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        student = await conn.fetchrow(
            "SELECT student_id, department_id FROM Students WHERE telegram_id = $1",
            user_tg
        )
        teacher = await conn.fetchrow(
            "SELECT teacher_id, department_id FROM Teachers WHERE telegram_id = $1",
            user_tg
        )
        if not student and not teacher:
            return await message.answer(
                "❌ Для предложения темы необходимо пройти регистрацию!",
                reply_markup=keyboards.registration_kb
            )
        dept_id = student['department_id'] if student else teacher['department_id']
        await state.update_data(
            student_id=student['student_id'] if student else None,
            teacher_id=teacher['teacher_id'] if teacher else None,
            department_id=dept_id
        )
        await message.answer(
            "Введите название темы:",
            reply_markup=keyboards.cancel_kb
        )
        await state.set_state(TopicStates.WAITING_TITLE)
    finally:
        await conn.close()


async def cancel_topic(message: Message, state: FSMContext):
    await state.clear()
    kb = keyboards.student_kb if await _is_student(message) else keyboards.teacher_kb
    await message.answer("Операция отменена.", reply_markup=kb)


async def process_title(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 5:
        return await message.answer("⚠️ Название должно быть не короче 5 символов. Попробуйте ещё раз.")
    await state.update_data(title=text)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Пропустить')],
            [KeyboardButton(text='❌ Отмена')],
        ],
        resize_keyboard=True
    )
    await message.answer("Введите описание темы (или нажмите 'Пропустить'):", reply_markup=kb)
    await state.set_state(TopicStates.WAITING_DESCRIPTION)


async def process_description(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() != 'пропустить' and len(text) < 10:
        return await message.answer("⚠️ Описание должно быть не короче 10 символов. Попробуйте ещё раз.")
    await state.update_data(description=None if text.lower() == 'пропустить' else text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='❌ Отмена')]],
        resize_keyboard=True
    )
    await message.answer("Введите ключевые слова через запятую:", reply_markup=kb)
    await state.set_state(TopicStates.WAITING_KEYWORDS)


async def process_keywords(message: Message, state: FSMContext):
    kws = [k.strip() for k in message.text.split(',') if k.strip()]
    if not kws:
        return await message.answer("⚠️ Укажите хотя бы одно ключевое слово.")
    data = await state.get_data()
    conn = await create_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO Topics(
                title, description, keywords, status,
                student_id, teacher_id, department_id
            ) VALUES($1,$2,$3,$4,$5,$6,$7)
            """,
            data['title'],
            data.get('description'),
            kws,
            'free',
            data.get('student_id'),
            data.get('teacher_id'),
            data['department_id']
        )
        await log_action(conn, str(message.from_user.id), 'add_topic', {
            'title': data['title'], 'keywords': kws
        })
        kb = keyboards.student_kb if data.get('student_id') else keyboards.teacher_kb
        await message.answer("✅ Тема добавлена!", reply_markup=kb)
    finally:
        await conn.close()
        await state.clear()


# --- ОДОБРЕНИЕ ТЕМЫ ---
async def approve_topic_start(message: Message, state: FSMContext):
    user_tg = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        if not await conn.fetchval(
            "SELECT 1 FROM Teachers WHERE telegram_id = $1", user_tg
        ):
            return await message.answer("⚠️ Только для преподавателей!", reply_markup=keyboards.teacher_kb)

        rows = await conn.fetch(
            """
            SELECT t.title,
                   COALESCE(s.name,'—') AS proposer
              FROM Topics t
              LEFT JOIN Students s ON t.student_id = s.student_id
             WHERE t.status='free'
             ORDER BY t.title
             LIMIT 10
            """
        )
        if not rows:
            return await message.answer("Нет тем для одобрения.", reply_markup=keyboards.teacher_kb)

        prompt = "Введите точное название для одобрения:\n\n"
        prompt += "\n".join(f"• {r['title']} (предложил {r['proposer']})" for r in rows)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text='❌ Отмена')]],
            resize_keyboard=True
        )
        await message.answer(prompt, reply_markup=kb)
        await state.set_state(ApproveTopicStates.WAITING_TITLE)
    finally:
        await conn.close()


async def process_approve_topic(message: Message, state: FSMContext):
    title = message.text.strip()
    user_tg = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        teacher_id = await conn.fetchval(
            "SELECT teacher_id FROM Teachers WHERE telegram_id = $1", user_tg
        )
        result = await conn.execute(
            """
            UPDATE Topics
               SET status='closed', teacher_id=$1
             WHERE title=$2 AND status='free'
            """,
            teacher_id, title
        )
        if result == 'UPDATE 0':
            return await message.answer("⚠️ Тема не найдена или уже закрыта.")
        await message.answer(f"✅ Тема «{title}» одобрена.", reply_markup=keyboards.teacher_kb)
    finally:
        await conn.close()
        await state.clear()


async def cancel_approve_topic(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=keyboards.teacher_kb)


# --- ОТКРЕПЛЕНИЕ ОТ ТЕМЫ ---
async def detach_topic_start(message: Message, state: FSMContext):
    user_tg = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        student_id = await conn.fetchval(
            "SELECT student_id FROM Students WHERE telegram_id = $1", user_tg
        )
        if not student_id:
            return await message.answer("❌ Вы не студент или не зарегистрированы.", reply_markup=keyboards.student_kb)

        rows = await conn.fetch(
            """
            SELECT title
            FROM Topics
            WHERE student_id = $1
            """,
            student_id
        )
        if not rows:
            return await message.answer("❌ У вас нет тем для открепления.", reply_markup=keyboards.student_kb)

        buttons = [[KeyboardButton(text=r['title'])] for r in rows]
        buttons.append([KeyboardButton(text='❌ Отмена')])
        kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

        await message.answer("Выберите тему, от которой хотите открепиться:", reply_markup=kb)
        await state.update_data(student_id=student_id)
        await state.set_state(DetachStates.WAITING_TITLE)
    finally:
        await conn.close()


async def process_detach(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('student_id')
    title = message.text.strip()
    if not student_id:
        await message.answer("❌ Повторите команду.", reply_markup=keyboards.student_kb)
        return await state.clear()

    conn = await create_db_connection()
    try:
        result = await conn.execute(
            """
            UPDATE Topics
               SET student_id = NULL, status = 'free'
             WHERE title = $1 AND student_id = $2
            """,
            title, student_id
        )
        if result == 'UPDATE 1':
            await message.answer(f"✅ Вы открепились от темы «{title}».", reply_markup=keyboards.student_kb)
            await log_action(conn, str(message.from_user.id), 'detach_topic', {'title': title})
        else:
            await message.answer("❌ Не удалось найти такую тему, привязанную к вам.", reply_markup=keyboards.student_kb)
    finally:
        await conn.close()
        await state.clear()


# --- УДАЛЕНИЕ АККАУНТА И ТЕМ ---
async def delete_account_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='ПОДТВЕРЖДАЮ')],
            [KeyboardButton(text='ОТМЕНА')],
        ],
        resize_keyboard=True
    )
    await message.answer(
        "❗ Вы уверены, что хотите удалить свой аккаунт и все предложённые вами темы? Это действие необратимо.",
        reply_markup=kb
    )
    await state.set_state(DeleteAccountStates.CONFIRM)


async def process_delete_account(message: Message, state: FSMContext):
    user_tg = str(message.from_user.id)
    conn = await create_db_connection()
    try:
        student = await conn.fetchrow("SELECT student_id FROM Students WHERE telegram_id = $1", user_tg)
        if student:
            sid = student['student_id']
            await conn.execute("DELETE FROM Topics WHERE student_id=$1", sid)
            await conn.execute("DELETE FROM Students WHERE student_id=$1", sid)
            await log_action(conn, user_tg, 'delete_account', {'role':'student'})
            await message.answer("✅ Ваш аккаунт и все ваши темы удалены.", reply_markup=keyboards.registration_kb)
            await state.clear()
            return

        teacher = await conn.fetchrow("SELECT teacher_id FROM Teachers WHERE telegram_id = $1", user_tg)
        if teacher:
            tid = teacher['teacher_id']
            await conn.execute("DELETE FROM Topics WHERE teacher_id=$1", tid)
            await conn.execute("DELETE FROM Teachers WHERE teacher_id=$1", tid)
            await log_action(conn, user_tg, 'delete_account', {'role':'teacher'})
            await message.answer("✅ Ваш преподавательский аккаунт и все ваши темы удалены.", reply_markup=keyboards.registration_kb)
            await state.clear()
            return

        await message.answer("⚠️ Аккаунт не найден.", reply_markup=keyboards.registration_kb)
    finally:
        await conn.close()


async def cancel_detach(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Открепление отменено.", reply_markup=keyboards.student_kb)


async def cancel_delete_account(message: Message, state: FSMContext):
    await state.clear()
    kb = keyboards.student_kb if await _is_student(message) else keyboards.teacher_kb
    await message.answer("Удаление отменено.", reply_markup=kb)


# вспомогательная функция
async def _is_student(message: Message) -> bool:
    conn = await create_db_connection()
    try:
        return bool(await conn.fetchval(
            "SELECT 1 FROM Students WHERE telegram_id=$1",
            str(message.from_user.id)
        ))
    finally:
        await conn.close()
