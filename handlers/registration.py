# handlers/registration.py
import re
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from config import TEACHER_ACCESS_CODE
from database import create_db_connection
import keyboards

# Состояния регистрации
class RegState:
    ROLE_SELECTION = 0
    TEACHER_CODE = 1
    NAME_INPUT = 2
    EMAIL_INPUT = 3
    PHONE_INPUT = 4
    GROUP_INPUT = 5
    DEPARTMENT_SELECTION = 6

# Временное хранилище данных регистрации
user_registration_data = {}

# Валидации
def validate_email(email: str) -> bool:
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def validate_phone(phone: str) -> bool:
    return re.match(r'^\+7\d{10}$', phone) is not None

def validate_group(group: str) -> bool:
    return re.match(r'^[А-ЯA-Z]{2,3}-\d{2,3}$', group) is not None

# Регистрация хэндлеров
def register_handlers(dp):
    dp.message(Command("start"))(start_handler)
    dp.message(F.text.in_(['🎓 Студент','👨🏫 Преподаватель']))(role_handler)
    dp.message(
        F.text,
        lambda message: message.from_user.id in user_registration_data
    )(process_registration)

# Обработчики
async def start_handler(message: Message):
    user_id = message.from_user.id
    conn = None
    try:
        conn = await create_db_connection()
        student = await conn.fetchrow(
            "SELECT * FROM Students WHERE telegram_id = $1",
            str(user_id)
        )
        teacher = await conn.fetchrow(
            "SELECT * FROM Teachers WHERE telegram_id = $1",
            str(user_id)
        )
        if student:
            await message.answer("🎓 Добро пожаловать, студент!", reply_markup=keyboards.student_kb)
        elif teacher:
            await message.answer("👨🏫 Добро пожаловать, преподаватель!", reply_markup=keyboards.teacher_kb)
        else:
            user_registration_data[user_id] = {"state": RegState.ROLE_SELECTION}
            await message.answer(
                "👋 Для начала работы выберите вашу роль:",
                reply_markup=keyboards.registration_kb
            )
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
    finally:
        if conn:
            await conn.close()

async def role_handler(message: Message):
    user_id = message.from_user.id
    if user_registration_data.get(user_id, {}).get("state") != RegState.ROLE_SELECTION:
        return
    role = "student" if message.text == '🎓 Студент' else "teacher"
    next_state = RegState.TEACHER_CODE if role == "teacher" else RegState.NAME_INPUT
    user_registration_data[user_id] = {"state": next_state, "role": role, "data": {}}

    if role == "teacher":
        await message.answer("Введите секретный код преподавателя:", reply_markup=keyboards.cancel_kb)
    else:
        await message.answer("Введите ваше ФИО:", reply_markup=keyboards.cancel_kb)

async def process_registration(message: Message):
    user_id = message.from_user.id
    if user_id not in user_registration_data:
        return
    state = user_registration_data[user_id]["state"]
    text = message.text.strip()
    role = user_registration_data[user_id]["role"]

    try:
        # 1) Проверка кода преподавателя
        if state == RegState.TEACHER_CODE:
            if text != TEACHER_ACCESS_CODE:
                await message.answer("❌ Неверный код! Попробуйте еще раз:")
                return
            user_registration_data[user_id]["state"] = RegState.NAME_INPUT
            await message.answer("Введите ваше ФИО:", reply_markup=keyboards.cancel_kb)
            return

        # 2) Ввод имени
        if state == RegState.NAME_INPUT:
            if len(text) < 2:
                await message.answer("⚠️ Имя должно содержать минимум 2 символа. Повторите ввод:")
                return
            user_registration_data[user_id]["data"]["name"] = text
            user_registration_data[user_id]["state"] = RegState.EMAIL_INPUT
            # Предлагаем ввести или пропустить email
            kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text='Пропустить')],
                    [KeyboardButton(text='❌ Отмена')]
                ],
                resize_keyboard=True
            )
            await message.answer("Введите ваш email или нажмите «Пропустить»:", reply_markup=kb)
            return

        # 3) Ввод email или пропустить
        if state == RegState.EMAIL_INPUT:
            if text.lower() == 'пропустить':
                user_registration_data[user_id]["data"]["email"] = None
            else:
                if not validate_email(text):
                    await message.answer("⚠️ Некорректный email. Повторите ввод или «Пропустить»:")
                    return
                user_registration_data[user_id]["data"]["email"] = text
            user_registration_data[user_id]["state"] = RegState.PHONE_INPUT
            # Предлагаем ввести или пропустить телефон
            kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text='Пропустить')],
                    [KeyboardButton(text='❌ Отмена')]
                ],
                resize_keyboard=True
            )
            await message.answer("Введите номер телефона (+79991234567) или «Пропустить»:", reply_markup=kb)
            return

        # 4) Ввод телефона или пропустить
        if state == RegState.PHONE_INPUT:
            if text.lower() == 'пропустить':
                user_registration_data[user_id]["data"]["phone"] = None
            else:
                if not validate_phone(text):
                    await message.answer("⚠️ Некорректный номер. Повторите ввод или «Пропустить»:")
                    return
                user_registration_data[user_id]["data"]["phone"] = text

            # следующий этап
            if role == "student":
                user_registration_data[user_id]["state"] = RegState.GROUP_INPUT
                await message.answer("Введите номер группы (например: КС-46):", reply_markup=keyboards.cancel_kb)
            else:
                user_registration_data[user_id]["state"] = RegState.DEPARTMENT_SELECTION
                await _ask_department(message)
            return

        # 5) Ввод группы (только для студентов)
        if state == RegState.GROUP_INPUT:
            if not validate_group(text):
                await message.answer("⚠️ Неверный формат группы. Пример: КС-46")
                return
            user_registration_data[user_id]["data"]["group"] = text
            user_registration_data[user_id]["state"] = RegState.DEPARTMENT_SELECTION
            await _ask_department(message)
            return

        # 6) Выбор кафедры
        if state == RegState.DEPARTMENT_SELECTION:
            user_registration_data[user_id]["data"]["department"] = text
            await save_user_data(user_id, message)
            return

    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
        user_registration_data.pop(user_id, None)


async def _ask_department(message: Message):
    """Запрашивает список кафедр и показывает клавиатуру."""
    conn = await create_db_connection()
    try:
        rows = await conn.fetch("SELECT name FROM Departments ORDER BY name")
        names = [r['name'] for r in rows]
    finally:
        await conn.close()

    # Формируем список рядов кнопок по 2 в ряд
    buttons: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for name in names:
        row.append(KeyboardButton(text=name))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    # Добавляем кнопку отмены отдельным рядом
    buttons.append([KeyboardButton(text='❌ Отмена')])

    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("Выберите вашу кафедру:", reply_markup=kb)



async def save_user_data(user_id: int, message: Message):
    conn = None
    try:
        conn = await create_db_connection()
        data = user_registration_data[user_id]["data"]
        role = user_registration_data[user_id]["role"]

        # id кафедры
        dept_id = await conn.fetchval(
            "SELECT department_id FROM Departments WHERE name = $1",
            data["department"]
        )

        if role == "student":
            await conn.execute(
                """
                INSERT INTO Students(
                    name, email, phone, telegram_id, group_name, department_id
                ) VALUES($1, $2, $3, $4, $5, $6)
                """,
                data["name"], data["email"], data["phone"],
                str(user_id), data["group"], dept_id
            )
            await message.answer("🎓 Регистрация студента завершена!", reply_markup=keyboards.student_kb)
        else:
            await conn.execute(
                """
                INSERT INTO Teachers(
                    name, email, phone, telegram_id, department_id
                ) VALUES($1, $2, $3, $4, $5)
                """,
                data["name"], data["email"], data["phone"],
                str(user_id), dept_id
            )
            await message.answer("👨🏫 Регистрация преподавателя завершена!", reply_markup=keyboards.teacher_kb)

    except Exception as e:
        await message.answer(f"⚠️ Ошибка сохранения данных: {e}")
    finally:
        user_registration_data.pop(user_id, None)
        if conn:
            await conn.close()
