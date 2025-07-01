# bot.py
import asyncio
from aiogram import Bot, Dispatcher
from config import API_TOKEN
import keyboards

# Импортируем ваши пакеты-обработчики
from handlers import registration, topics, search, misc, analytics, categories, choose_topic

async def main():
    # Инициализируем бота и диспетчера
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    # При желании можно настроить middleware, фильтры и т.п.
    keyboards.setup(dp)

    # Регистрируем хэндлеры из модулей
    registration.register_handlers(dp)
    topics.register_handlers(dp)
    search.register_handlers(dp)
    categories.register_handlers(dp)
    misc.register_handlers(dp)
    analytics.register_handlers(dp)
    choose_topic.register_handlers(dp)

    # Стартуем лонг-поллинг
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
