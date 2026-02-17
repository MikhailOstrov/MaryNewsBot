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

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# === МАШИНА СОСТОЯНИЙ (FSM) ===
class AdminState(StatesGroup):
    waiting_for_broadcast = State()      # Режим рассылки
    waiting_for_username = State()       # Режим ввода юзернейма
    waiting_for_message = State()        # Режим ввода сообщения

# === КЛАВИАТУРЫ ===

def get_user_keyboard():
    """Кнопки для обычного пользователя (Inline)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Перейти на платформу", url=SITE_URL)],
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_question")]
    ])

def get_admin_keyboard():
    """Кнопки для администратора (Reply)"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📢 Рассылка новостей")],
        [KeyboardButton(text="✉️ Написать пользователю")],
        [KeyboardButton(text="📊 Статистика")]
    ], resize_keyboard=True, input_field_placeholder="Выберите действие")

def get_cancel_keyboard():
    """Клавиатура с отменой"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)

# === ХЕНДЛЕРЫ АДМИНИСТРАТОРА ===

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Ручной вызов админ-панели"""
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

# --- 2. ЛИЧНОЕ СООБЩЕНИЕ (НОВАЯ ФУНКЦИЯ) ---

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
    
    # Ищем юзернейм в сообщении (@что-то)
    match = re.search(r'@(\w+)', text)
    
    if not match:
        await message.answer(
            "⚠️ <b>Не найден юзернейм!</b>\n\n"
            "Сообщение должно начинаться с @username\n"
            "Пример: <code>@ivan_privet Привет</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    username = match.group(1)  # извлекаем без @
    
    # Извлекаем сообщение (всё после юзернейма)
    message_text = text[match.end():].strip()
    
    if not message_text:
        await message.answer(
            "⚠️ <b>Не найден текст сообщения!</b>\n\n"
            "Пример: <code>@ivan_privet Привет</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Ищем пользователя в базе по username
    user = db.get_user_by_username(username)
    
    if not user:
        await message.answer(
            f"❌ <b>Пользователь @{username} не найден в базе!</b>\n\n"
            "Возможно, он ещё не запускал бота.\n"
            "Попробуйте ещё раз или напишите /cancel",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard()
        )
        return
    
    user_id = user[0]
    user_name = user[2] or "Пользователь"
    
    # Сохраняем данные и переходим к подтверждению (или сразу отправляем)
    # Для простоты отправляем сразу
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
            f"❌ <b>Ошибка отправки!</b>\n\n{e}\n\n"
            "Возможно, пользователь заблокировал бота.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    
    await state.clear()

# --- 3. СТАТИСТИКА ---

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = db.get_all_users()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\nВсего пользователей: {len(users)}",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )

# --- ОТМЕНА ДЛЯ ВСЕХ СОСТОЯНИЙ ---
@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_admin_keyboard())

# === ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ===

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Приветствие + проверка роли"""
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
    await callback.message.answer(
        "✍️ Напишите ваш вопрос ниже, и Мэри лично ответит вам в ближайшее время!"
    )
    await callback.answer()

@dp.message(F.text)
async def handle_user_message(message: types.Message, state: FSMContext):
    """Пересылка вопросов от пользователей админу"""
    if message.text.startswith('/'):
        return
    
    if message.from_user.id == ADMIN_ID:
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