import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
import os
import database as db

# Загружаем переменные из .env
load_dotenv()

# === КОНФИГУРАЦИЯ ===
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
SITE_URL = os.getenv('SITE_URL', 'https://app.maryrose.by/').strip()
FOLLOWUP_DELAY = 60
SPAM_DELAY_SECONDS = 5  # Задержка между сообщениями пользователя

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# === МАШИНА СОСТОЯНИЙ (FSM) ===
class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_username = State()
    waiting_for_ban = State()        # Режим бана по ID
    waiting_for_unban = State()      # Режим разбана по ID

# === КЛАВИАТУРЫ ===

def get_user_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Перейти на платформу", url=SITE_URL)],
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_question")]
    ])

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📢 Рассылка новостей")],
        [KeyboardButton(text="✉️ Написать пользователю")],
        [KeyboardButton(text="🚫 Бан / Разбан")],
        [KeyboardButton(text="📊 Статистика")]
    ], resize_keyboard=True, input_field_placeholder="Выберите действие")

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)

def get_ban_unban_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚫 Забанить пользователя")],
        [KeyboardButton(text="✅ Разбанить пользователя")],
        [KeyboardButton(text="📋 Список забаненных")],
        [KeyboardButton(text="❌ Назад")]
    ], resize_keyboard=True)

# === ПРОВЕРКА НА БАН И СПАМ (MIDDLEWARE) ===

async def check_user_access(message: types.Message) -> bool:
    """Проверяет, забанен ли пользователь и не спамит ли он"""
    user_id = message.from_user.id
    
    # Админа не проверяем
    if user_id == ADMIN_ID:
        return True
    
    # Проверка на бан
    if db.is_user_banned(user_id):
        await message.answer("🚫 Вы заблокированы в этом боте.\nОбратитесь к администрации для разблокировки.")
        return False
    
    # Проверка на спам
    if db.check_spam(user_id, SPAM_DELAY_SECONDS):
        await message.answer(f"⏳ Пожалуйста, подождите {SPAM_DELAY_SECONDS} секунд между сообщениями.")
        return False
    
    return True

# === ХЕНДЛЕРЫ АДМИНИСТРАТОРА ===

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "👨‍💻 <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )

# --- 1. РАССЫЛКА ---

@dp.message(F.text == "📢 Рассылка новостей")
async def start_broadcast_button(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📨 <b>Введите текст рассылки</b>.\n\nМожно отправить текст, фото, видео или файл:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminState.waiting_for_broadcast)

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text and message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_keyboard())
        return
    
    await message.answer("⏳ Рассылка запущена...")
    
    users = db.get_all_users()
    count = 0
    failed = 0
    
    for user in users:
        user_id = user[0]
        if user_id == ADMIN_ID:
            continue
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
        except Exception as e:
            failed += 1
            logging.warning(f"Не удалось отправить пользователю {user_id}: {e}")
        
        await asyncio.sleep(0.05)
    
    await message.answer(
        f"✅ <b>Готово!</b>\n\nОтправлено: {count}\nОшибок: {failed}",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()

# --- 2. ЛИЧНОЕ СООБЩЕНИЕ ---

@dp.message(F.text == "✉️ Написать пользователю")
async def start_personal_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "✍️ <b>Введите данные в формате:</b>\n\n"
        "<code>@username сообщение</code>\n\n"
        "Пример:\n"
        "<code>@ivan_privet Привет, это Мэри!</code>\n\n"
        "Напишите /cancel для отмены.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminState.waiting_for_username)

@dp.message(AdminState.waiting_for_username)
async def process_username_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text and message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_keyboard())
        return
    
    text = message.text.strip()
    match = re.search(r'@(\w+)', text)
    
    if not match:
        await message.answer(
            "⚠️ <b>Не найден юзернейм!</b>\n\n"
            "Сообщение должно содержать @username\n"
            "Пример: <code>@ivan_privet Привет</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    username = match.group(1)
    message_text = text[match.end():].strip()
    
    if not message_text:
        await message.answer(
            "⚠️ <b>Не найден текст сообщения!</b>\n\n"
            "Пример: <code>@ivan_privet Привет</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    user = db.get_user_by_username(username)
    
    if not user:
        await message.answer(
            f"❌ <b>Пользователь @{username} не найден в базе!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    user_id = user[0]
    user_name = user[2] or "Пользователь"
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"📩 <b>Сообщение от администрации:</b>\n\n{message_text}",
            parse_mode=ParseMode.HTML
        )
        
        await message.answer(
            f"✅ <b>Сообщение отправлено!</b>\n\n"
            f"Пользователь: {user_name} (@{username})\n"
            f"ID: <code>{user_id}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка отправки!</b>\n\n{e}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    
    await state.clear()

# --- 3. БАН / РАЗБАН ---

@dp.message(F.text == "🚫 Бан / Разбан")
async def ban_unban_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "🔒 <b>Управление блокировками</b>\n\nВыберите действие:",
        reply_markup=get_ban_unban_keyboard(),
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🚫 Забанить пользователя")
async def start_ban(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "🚫 <b>Введите ID пользователя для бана:</b>\n\n"
        "Напишите /cancel для отмены.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminState.waiting_for_ban)

@dp.message(AdminState.waiting_for_ban)
async def process_ban(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text and message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_ban_unban_keyboard())
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "⚠️ <b>Неверный ID!</b>\n\nВведите числовое ID пользователя.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    if user_id == ADMIN_ID:
        await message.answer("⛔️ Нельзя забанить создателя бота!", reply_markup=get_ban_unban_keyboard())
        await state.clear()
        return
    
    user = db.get_user_by_id(user_id)
    
    if not user:
        await message.answer(
            f"❌ <b>Пользователь с ID {user_id} не найден!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    db.ban_user(user_id)
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            chat_id=user_id,
            text="🚫 Вы были заблокированы в этом боте.\nОбратитесь к администрации для разблокировки."
        )
    except:
        pass
    
    await message.answer(
        f"✅ <b>Пользователь забанен!</b>\n\nID: <code>{user_id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_ban_unban_keyboard()
    )
    await state.clear()

@dp.message(F.text == "✅ Разбанить пользователя")
async def start_unban(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "✅ <b>Введите ID пользователя для разбана:</b>\n\n"
        "Напишите /cancel для отмены.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminState.waiting_for_unban)

@dp.message(AdminState.waiting_for_unban)
async def process_unban(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text and message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_ban_unban_keyboard())
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "⚠️ <b>Неверный ID!</b>\n\nВведите числовое ID пользователя.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    user = db.get_user_by_id(user_id)
    
    if not user:
        await message.answer(
            f"❌ <b>Пользователь с ID {user_id} не найден!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    db.unban_user(user_id)
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            chat_id=user_id,
            text="✅ Вы были разблокированы в этом боте.\nТеперь вы снова можете пользоваться всеми функциями."
        )
    except:
        pass
    
    await message.answer(
        f"✅ <b>Пользователь разбанен!</b>\n\nID: <code>{user_id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_ban_unban_keyboard()
    )
    await state.clear()

@dp.message(F.text == "📋 Список забаненных")
async def show_banned_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    banned = db.get_banned_users()
    
    if not banned:
        await message.answer(
            "✅ <b>Забаненных пользователей нет!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_ban_unban_keyboard()
        )
        return
    
    text = "🚫 <b>Забаненные пользователи:</b>\n\n"
    for user in banned:
        user_id, username, first_name = user
        text += f"• ID: <code>{user_id}</code> — {first_name or 'Без имени'}"
        if username:
            text += f" (@{username})"
        text += "\n"
    
    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_ban_unban_keyboard()
    )

@dp.message(F.text == "❌ Назад")
async def back_to_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "👨‍💻 <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )

# --- 4. СТАТИСТИКА ---

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = db.get_all_users()
    banned = db.get_banned_users()
    
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"Всего пользователей: {len(users)}\n"
        f"Забанено: {len(banned)}\n"
        f"Активных: {len(users) - len(banned)}",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )

# --- ОТМЕНА ---
@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_admin_keyboard())

# === ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ===

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    db.add_user(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name
    )
    
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👋 <b>Привет, Создатель!</b>\n\nБот готов к работе. Выберите действие:",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.HTML
        )
    else:
        # Проверка на бан при старте
        if db.is_user_banned(message.from_user.id):
            await message.answer("🚫 Вы заблокированы в этом боте.\nОбратитесь к администрации для разблокировки.")
            return
        
        user_name = message.from_user.first_name or "Пользователь"
        text = (
            f"👋 Привет, {user_name}! Меня зовут Мэри — твой личный ассистент.\n\n"
            "Рада видеть тебя в официальном боте <b>Mary Rose</b>! 🌹\n\n"
            "Жми на кнопку ниже, чтобы перейти на платформу.\n"
            "Если есть вопросы — я всегда на связи! 👇"
        )
        await message.answer(text, reply_markup=get_user_keyboard(), parse_mode=ParseMode.HTML)
        asyncio.create_task(send_followup(message.from_user.id))

@dp.callback_query(F.data == "ask_question")
async def ask_question_callback(callback: types.CallbackQuery):
    if db.is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы!", show_alert=True)
        return
    
    await callback.message.answer(
        "✍️ Напишите ваш вопрос ниже, и Мэри лично ответит вам в ближайшее время!"
    )
    await callback.answer()

@dp.message(F.text)
async def handle_user_message(message: types.Message, state: FSMContext):
    """Обработка сообщений от пользователей с проверкой на бан и спам"""
    
    # Игнорируем команды
    if message.text.startswith('/'):
        return
    
    # Игнорируем админа
    if message.from_user.id == ADMIN_ID:
        return
    
    # === ПРОВЕРКА ДОСТУПА ===
    if not await check_user_access(message):
        return

    user_name = message.from_user.first_name or "Пользователь"
    user_username = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    user_id = message.from_user.id

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"❓ <b>Вопрос от пользователя</b>\n"
             f"👤 {user_name} ({user_username})\n"
             f"🆔 ID: <code>{user_id}</code>\n\n"
             f"<i>💬 Чтобы ответить — используйте кнопку 'Написать пользователю' выше.</i>",
        parse_mode=ParseMode.HTML
    )
    await message.copy_to(chat_id=ADMIN_ID)
    await message.answer("✅ Ваш вопрос отправлен! Я скоро отвечу.")

# === ВТОРОЕ СООБЩЕНИЕ (FOLLOW-UP) ===
async def send_followup(user_id: int):
    await asyncio.sleep(FOLLOWUP_DELAY)
    
    if db.is_user_banned(user_id):
        return
    
    text = (
        "Надеюсь, ты уже перешёл на сайт и заценил наши фичи! ✨\n\n"
        "В дальнейшем проект будет стремительно расти, как и этот бот. "
        "Не пропусти обновления! 🚀"
    )
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logging.warning(f"Follow-up failed for {user_id}: {e}")

# === ЗАПУСК ===
async def main():
    db.init_db()
    logging.info("База данных инициализирована.")
    logging.info(f"Бот запущен. Ожидание подключений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())