import asyncio
import logging
import sqlite3
import secrets
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = '8651151090:AAGYuAkWF7lVig-nwD08Dz6Vs1SEgPA2Ijo'
ADMIN_IDS = [7582399898]  # Твой Telegram ID (замени на свой)

# Xray конфигурация
XRAY_SERVER = "166.88.225.226"
XRAY_PORT = 443
XRAY_PRIVATE_KEY = "0I3YI0bIh2IUYU6MMFmyLSKtliFS9DHJTaG5mtEm_lM"
XRAY_PUBLIC_KEY = "oHbn7gICu11DjtzrELGSAVEvyX6S3SznoOPvtkH6fm0"
XRAY_SHORT_ID = "bbaeecd9b2bd20af"
XRAY_SNI = "www.microsoft.com"

bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_NAME = "vpn_bot.db"

# --- БАЗА ДАННЫХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        # Таблица пользователей
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            subscription_until INTEGER DEFAULT 0,
            device_limit INTEGER DEFAULT 1,
            traffic_limit_gb INTEGER DEFAULT 0,
            traffic_used_gb REAL DEFAULT 0,
            created_at INTEGER,
            is_active INTEGER DEFAULT 1
        )""")
        
        # Таблица конфигов (устройств)
        conn.execute("""CREATE TABLE IF NOT EXISTS configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            config_id TEXT UNIQUE,
            device_name TEXT,
            short_link TEXT UNIQUE,
            created_at INTEGER,
            last_used INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )""")
        
        # Таблица платежей
        conn.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            plan_type TEXT,
            created_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )""")

def get_user(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def create_user(user_id, username):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""INSERT OR IGNORE INTO users (user_id, username, created_at) 
                        VALUES (?, ?, ?)""", (user_id, username, int(time.time())))

def get_user_configs(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT * FROM configs WHERE user_id = ?", (user_id,)).fetchall()

def generate_short_link():
    """Генерирует короткую ссылку (6 символов)"""
    return secrets.token_urlsafe(6)[:6]

def create_vless_link(config_id, device_name):
    """Создаёт VLESS ссылку для конфига"""
    link = (
        f"vless://{config_id}@{XRAY_SERVER}:{XRAY_PORT}"
        f"?encryption=none&flow=xtls-rprx-vision&security=reality"
        f"&sni={XRAY_SNI}&fp=chrome&pbk={XRAY_PUBLIC_KEY}"
        f"&sid={XRAY_SHORT_ID}&type=tcp&headerType=none"
        f"#🇩🇪_{device_name}"
    )
    return link

def add_config_to_xray(config_id):
    """Добавляет конфиг в Xray (нужно будет реализовать через API или файл)"""
    # TODO: Интеграция с Xray для добавления UUID в конфиг
    pass

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    create_user(user_id, username)
    user = get_user(user_id)
    
    welcome_text = """🔐 **SecureCrypt VPN**

Добро пожаловать в безопасный VPN сервис!

🌍 Локация: Германия 🇩🇪
⚡ Скорость: до 100 Mbit/s
🔒 Протокол: VLESS + Reality

**Команды:**
/profile - Мой профиль
/devices - Управление устройствами
/plans - Тарифные планы
/help - Помощь"""
    
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используй /start")
        return
    
    configs = get_user_configs(user_id)
    subscription_until = user[2]
    device_limit = user[3]
    traffic_limit = user[4]
    traffic_used = user[5]
    
    if subscription_until > time.time():
        sub_date = datetime.fromtimestamp(subscription_until).strftime("%d.%m.%Y")
        status = f"✅ Активна до {sub_date}"
    else:
        status = "❌ Не активна"
    
    profile_text = f"""👤 **Ваш профиль**

📊 Подписка: {status}
📱 Устройств: {len(configs)}/{device_limit}
📊 Трафик: {traffic_used:.2f} GB / {traffic_limit} GB

Используй /devices для управления устройствами"""
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(Command("devices"))
async def cmd_devices(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используй /start")
        return
    
    configs = get_user_configs(user_id)
    device_limit = user[3]
    
    if not configs:
        text = "📱 У вас пока нет устройств.\n\nИспользуйте кнопку ниже для добавления."
    else:
        text = f"📱 **Ваши устройства ({len(configs)}/{device_limit}):**\n\n"
        for idx, config in enumerate(configs, 1):
            device_name = config[3]
            short_link = config[4]
            text += f"{idx}. {device_name} - `{short_link}`\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить устройство", callback_data="add_device")],
        [InlineKeyboardButton(text="🗑 Удалить устройство", callback_data="remove_device")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "add_device")
async def add_device_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    configs = get_user_configs(user_id)
    device_limit = user[3]
    
    if len(configs) >= device_limit:
        await callback.answer("❌ Достигнут лимит устройств!", show_alert=True)
        return
    
    # Генерируем новый конфиг
    import uuid
    config_id = str(uuid.uuid4())
    device_name = f"Device_{len(configs) + 1}"
    short_link = generate_short_link()
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""INSERT INTO configs (user_id, config_id, device_name, short_link, created_at) 
                        VALUES (?, ?, ?, ?, ?)""", 
                     (user_id, config_id, device_name, short_link, int(time.time())))
    
    # Создаём VLESS ссылку
    vless_link = create_vless_link(config_id, device_name)
    
    text = f"""✅ **Устройство добавлено!**

📱 Название: {device_name}
🔗 Короткая ссылка: `{short_link}`

**Ссылка для подключения:**
```
{vless_link}
```

**Как подключиться:**
1. Скопируй ссылку выше
2. Открой v2rayN/Hiddify/v2rayNG
3. Импортируй из буфера обмена

Или используй короткую ссылку: https://t.me/SecureCrypt_bot?start={short_link}"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("plans"))
async def cmd_plans(message: types.Message):
    plans_text = """💎 Тарифные планы

📦 Базовый - 200₽/месяц
• 1 устройство
• 50 GB трафика
• Германия 🇩🇪

📦 Стандарт - 350₽/месяц
• 3 устройства
• 150 GB трафика
• Германия 🇩🇪

📦 Премиум - 500₽/месяц
• 5 устройств
• Безлимитный трафик
• Германия 🇩🇪

Для покупки напишите @your_username"""
    
    await message.answer(plans_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """❓ **Помощь**

**Основные команды:**
/start - Начать работу
/profile - Мой профиль
/devices - Управление устройствами
/plans - Тарифные планы

**Как подключиться:**
1. Купите подписку (/plans)
2. Добавьте устройство (/devices)
3. Скопируйте ссылку
4. Импортируйте в v2rayN/Hiddify

**Поддержка:** @your_username"""
    
    await message.answer(help_text, parse_mode="Markdown")

# --- АДМИН КОМАНДЫ ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    with sqlite3.connect(DB_NAME) as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_subs = conn.execute("SELECT COUNT(*) FROM users WHERE subscription_until > ?", (int(time.time()),)).fetchone()[0]
        total_configs = conn.execute("SELECT COUNT(*) FROM configs").fetchone()[0]
    
    admin_text = f"""👑 **Админ панель**

👥 Всего пользователей: {total_users}
✅ Активных подписок: {active_subs}
📱 Всего устройств: {total_configs}

**Команды:**
/adduser <user_id> <days> - Добавить подписку
/stats - Статистика"""
    
    await message.answer(admin_text, parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        init_db()
        logger.info("✅ База данных инициализирована")
        
        await bot.set_my_commands([
            BotCommand(command='start', description='🚀 Начать'),
            BotCommand(command='profile', description='👤 Мой профиль'),
            BotCommand(command='devices', description='📱 Устройства'),
            BotCommand(command='plans', description='💎 Тарифы'),
            BotCommand(command='help', description='❓ Помощь')
        ])
        logger.info("✅ Команды бота установлены")
        
        logger.info("=" * 50)
        logger.info("🚀 VPN БОТ ЗАПУЩЕН!")
        logger.info("=" * 50)
        
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
