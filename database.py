# database.py
import asyncpg
from config import POSTGRES_URI

async def init_db():
    conn = await asyncpg.connect(POSTGRES_URI)
    try:
        # Используем транзакцию для обеспечения атомарности
        async with conn.transaction():
            # Таблицы предметной области
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Departments (
                    department_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Students (
                    student_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    phone TEXT,
                    telegram_id TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    group_name TEXT,
                    department_id INTEGER REFERENCES Departments(department_id) ON DELETE SET NULL
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Teachers (
                    teacher_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    phone TEXT,
                    telegram_id TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    department_id INTEGER REFERENCES Departments(department_id) ON DELETE SET NULL
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Topics (
                    topic_id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    keywords TEXT[],
                    status TEXT CHECK (status IN ('free', 'reserved', 'closed')),
                    teacher_id INTEGER REFERENCES Teachers(teacher_id) ON DELETE SET NULL,
                    student_id INTEGER REFERENCES Students(student_id) ON DELETE SET NULL,
                    department_id INTEGER REFERENCES Departments(department_id) ON DELETE CASCADE
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Suggestions (
                    suggestion_id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    student_id INTEGER REFERENCES Students(student_id) ON DELETE CASCADE,
                    status TEXT CHECK (status IN ('pending', 'approved', 'rejected')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            # Обновлённая лог‑таблица действий
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Interactions (
                    interaction_id SERIAL PRIMARY KEY,
                    teacher_id   INTEGER REFERENCES Teachers(teacher_id) ON DELETE CASCADE,
                    student_id   INTEGER REFERENCES Students(student_id) ON DELETE CASCADE,
                    topic_id     INTEGER REFERENCES Topics(topic_id)   ON DELETE CASCADE,
                    user_role    TEXT CHECK(user_role IN ('student','teacher')),
                    action       TEXT NOT NULL,
                    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            # Категории и связь с темами
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS Categories (
                    category_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id INTEGER REFERENCES Categories(category_id) ON DELETE CASCADE
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS TopicCategories (
                    topic_id INTEGER REFERENCES Topics(topic_id) ON DELETE CASCADE,
                    category_id INTEGER REFERENCES Categories(category_id) ON DELETE CASCADE,
                    PRIMARY KEY(topic_id, category_id)
                );
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS SearchLogs (
                    log_id SERIAL PRIMARY KEY,
                    student_id INTEGER REFERENCES Students(student_id) ON DELETE CASCADE,
                    query TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

                        ''')
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")
    finally:
        await conn.close()

async def create_db_connection():
    return await asyncpg.connect(POSTGRES_URI)