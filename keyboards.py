# keyboard.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

student_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📝 Предложить тему')],
        [KeyboardButton(text='🔍 Поиск темы')],
        [KeyboardButton(text='📚 Свободные темы')],
        [KeyboardButton(text='🎯 Выбираю тему')],
        [KeyboardButton(text='📤 Открепиться от темы')],
        [KeyboardButton(text='🗑 Удалить аккаунт')]
    ],
    resize_keyboard=True
)

teacher_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📝 Предложить тему')],
        [KeyboardButton(text='🔍 Поиск темы')],
        [KeyboardButton(text='📈 Аналитика')],
        [KeyboardButton(text='📚 Свободные темы')],
        [KeyboardButton(text='✅ Одобрить тему')],
        [KeyboardButton(text='👤 Просмотр профиля')],
        [KeyboardButton(text='🗑 Удалить аккаунт')]
    ],
    resize_keyboard=True
)

registration_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🎓 Студент'), KeyboardButton(text='👨🏫 Преподаватель')]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='❌ Отмена')]
    ],
    resize_keyboard=True
)

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📝 Предложить тему'), KeyboardButton(text='🔍 Поиск темы')],
        [KeyboardButton(text='📈 Аналитика')],
        [KeyboardButton(text='📚 Свободные темы'), KeyboardButton(text='📂 По категории')],
        [KeyboardButton(text='👤 Просмотр профиля'), KeyboardButton(text='🗑 Удалить аккаунт')]
    ],
    resize_keyboard=True
)

def setup(dp):
    pass
