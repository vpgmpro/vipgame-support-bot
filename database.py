# database.py - работа с базой данных

import sqlite3
from datetime import datetime

DB_FILE = "support.db"

def init_db():
    """Создаёт таблицы, если их нет"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question TEXT,
            answer TEXT,
            answered BOOLEAN DEFAULT 0,
            created_at TIMESTAMP,
            answered_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def save_user(user):
    """Сохраняет или обновляет пользователя"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, last_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
    ''', (
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        None
    ))
    
    conn.commit()
    conn.close()

def save_question(user_id, question, answer=None):
    """Сохраняет вопрос пользователя"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO questions (user_id, question, answer, answered, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, question, answer, 1 if answer else 0))
    
    conn.commit()
    conn.close()

def save_answer(question_id, answer):
    """Сохраняет ответ на вопрос"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE questions 
        SET answer = ?, answered = 1, answered_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (answer, question_id))
    
    conn.commit()
    conn.close()

def get_stats():
    """Получает статистику"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM questions")
    total_questions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM questions WHERE answered = 1")
    answered_questions = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'total_questions': total_questions,
        'answered': answered_questions,
        'unanswered': total_questions - answered_questions
    }

def get_unanswered_questions(limit=20):
    """Получает последние неотвеченные вопросы"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT q.id, q.user_id, q.question, u.username, q.created_at
        FROM questions q
        LEFT JOIN users u ON q.user_id = u.user_id
        WHERE q.answered = 0
        ORDER BY q.created_at DESC
        LIMIT ?
    ''', (limit,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_last_questions(limit=10):
    """Получает последние вопросы (все)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT q.id, q.user_id, q.question, q.answered, u.username, q.created_at
        FROM questions q
        LEFT JOIN users u ON q.user_id = u.user_id
        ORDER BY q.created_at DESC
        LIMIT ?
    ''', (limit,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_total_users():
    """Получает количество пользователей"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count
