import sqlite3
from typing import List, Tuple, Optional
from datetime import datetime

DB_NAME = 'users.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_banned INTEGER DEFAULT 0,
            last_message_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, is_banned, last_message_time)
        VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def get_all_users() -> List[Tuple[int]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_user_by_username(username: str) -> Optional[Tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, is_banned FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# === АНТИ-СПАМ ===

def check_spam(user_id: int, delay_seconds: int = 5) -> bool:
    """
    Проверяет, не слишком ли часто пишет пользователь.
    Возвращает True, если спам (слишком быстро), False если всё ок.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT last_message_time FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    now = datetime.now()
    
    if result and result[0]:
        last_time = datetime.fromisoformat(result[0])
        delta = (now - last_time).total_seconds()
        
        if delta < delay_seconds:
            conn.close()
            return True  # Спам!
    
    # Обновляем время последнего сообщения
    cursor.execute('UPDATE users SET last_message_time = ? WHERE user_id = ?', (now.isoformat(), user_id))
    conn.commit()
    conn.close()
    
    return False  # Всё ок

# === ЧЕРНЫЙ СПИСОК ===

def ban_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_banned_users() -> List[Tuple[int, str, str]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name FROM users WHERE is_banned = 1')
    users = cursor.fetchall()
    conn.close()
    return users

def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1