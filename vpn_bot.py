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
    """Генерирует короткую ссылку (8 символов)"""
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:8]

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

def create_key_page(short_link, vless_link):
    """Создаёт HTML страницу для ключа"""
    html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VPN Key</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 600px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #667eea; text-align: center; }
        .key-box {
            background: #f7f7f7;
            border: 2px dashed #667eea;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            word-break: break-all;
            font-family: monospace;
            font-size: 14px;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            cursor: pointer;
            width: 100%;
            font-size: 16px;
            font-weight: bold;
            transition: 0.3s;
        }
        .btn:hover { background: #764ba2; }
        .success {
            display: none;
            color: #28a745;
            text-align: center;
            margin-top: 10px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Your VPN Key</h1>
        <div class="key-box" id="vlessKey">VLESS_LINK</div>
        <button class="btn" onclick="copyKey()">📋 Copy Key</button>
        <div class="success" id="successMsg">✅ Copied to clipboard!</div>
    </div>
    <script>
        function copyKey() {
            const key = document.getElementById('vlessKey').textContent;
            navigator.clipboard.writeText(key).then(() => {
                document.getElementById('successMsg').style.display = 'block';
                setTimeout(() => {
                    document.getElementById('successMsg').style.display = 'none';
                }, 2000);
            });
        }
    </script>
</body>
</html>"""
    
    html_content = html_template.replace('VLESS_LINK', vless_link)
    
    # Сохраняем HTML файл
    import os
    os.makedirs('/var/www/html/keys', exist_ok=True)
    with open(f'/var/www/html/keys/{short_link}.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return f"http://{XRAY_SERVER}/keys/{short_link}.html"

def add_config_to_xray(config_id):
    """Добавляет конфиг в Xray"""
    import json
    try:
        # Читаем текущий конфиг
        with open('/usr/local/etc/xray/config.json', 'r') as f:
            xray_config = json.load(f)
        
        # Проверяем есть ли уже этот UUID
        existing_ids = [client['id'] for client in xray_config['inbounds'][0]['settings']['clients']]
        if config_id not in existing_ids:
            # Добавляем новый UUID
            xray_config['inbounds'][0]['settings']['clients'].append({
                "id": config_id,
                "flow": "xtls-rprx-vision"
            })
            
            # Сохраняем конфиг
            with open('/usr/local/etc/xray/config.json', 'w') as f:
                json.dump(xray_config, f, indent=2)
            
            # Перезапускаем Xray
            import subprocess
            subprocess.run(['systemctl', 'restart', 'xray'], check=True)
            logging.info(f"✅ UUID {config_id} добавлен в Xray")
    except Exception as e:
        logging.error(f"❌ Ошибка добавления UUID в Xray: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    create_user(user_id, username)
    
    # Создаём бесплатный ключ автоматически
    configs = get_user_configs(user_id)
    
    if not configs:
        # Генерируем первый бесплатный ключ
        import uuid
        config_id = str(uuid.uuid4())
        short_link = generate_short_link()
        
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""INSERT INTO configs (user_id, config_id, device_name, short_link, created_at) 
                            VALUES (?, ?, ?, ?, ?)""", 
                         (user_id, config_id, "Подписка", short_link, int(time.time())))
            # Устанавливаем лимит 50GB для бесплатного
            conn.execute("UPDATE users SET traffic_limit_gb = 50 WHERE user_id = ?", (user_id,))
        
        # Добавляем UUID в Xray
        add_config_to_xray(config_id)
        
        vless_link = create_vless_link(config_id, "Subscription")
        
        # Создаём subscription URL
        import base64
        sub_content = base64.b64encode(vless_link.encode()).decode()
        sub_url = f"http://{XRAY_SERVER}/sub/{short_link}"
        
        # Сохраняем subscription файл
        import os
        os.makedirs('/var/www/html/sub', exist_ok=True)
        with open(f'/var/www/html/sub/{short_link}', 'w') as f:
            f.write(vless_link)
        
        welcome_text = f"""🎉 Спасибо за подписку!

Советуем не отписываться от канала, ведь там будут публиковаться различные новости о данном впн, включая уведомления о работе сервиса, анонсы и прочие обновления проекта :3

📊 Трафик: 0 GB / 50 GB

👉 Инструкция по установке: https://telegra.ph/VPN-Setup-Guide-04-15

На бесплатных серверах скорость может сильно ухудшаться от высокой нагрузки, а также трафик ограничен до 50 гигабайт в месяц

✅ Если вы хотите пользоваться сервисом без ограничений, то рекомендуем вам приобрести платный ключ в главном меню бота!"""
        
        await message.answer(welcome_text)
        await message.answer(f"Вот ваша подписка:\n\n<code>{sub_url}</code>", parse_mode="HTML")
    else:
        welcome_text = """🔐 SecureCrypt VPN

Добро пожаловать обратно!

Используйте команды:
/keys - Мои ключи
/premium - Премиум подписка
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
    traffic_limit = user[4]
    traffic_used = user[5]
    
    profile_text = f"""👤 Ваш профиль

📱 Ключей: {len(configs)}
📊 Трафик: {traffic_used:.2f} GB / {"∞" if traffic_limit == 0 else f"{traffic_limit} GB"}

Используй /keys для просмотра ключей"""
    
    await message.answer(profile_text)

@dp.message(Command("keys"))
async def cmd_keys(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    configs = get_user_configs(user_id)
    
    if not configs:
        await message.answer("❌ У вас нет ключей. Используйте /start")
        return
    
    traffic_limit = user[4]
    traffic_used = user[5]
    
    for idx, config in enumerate(configs, 1):
        short_link = config[4]
        sub_url = f"http://{XRAY_SERVER}/sub/{short_link}"
        
        if traffic_limit == 0:
            traffic_info = "📊 Трафик: Безлимит ♾️"
        else:
            remaining = traffic_limit - traffic_used
            traffic_info = f"📊 Трафик: {traffic_used:.1f} GB / {traffic_limit} GB (осталось {remaining:.1f} GB)"
        
        text = f"🔑 Подписка #{idx}\n\n{traffic_info}\n\nСсылка на подписку:\n<code>{sub_url}</code>"
        
        await message.answer(text, parse_mode="HTML")

@dp.message(Command("premium"))
async def cmd_premium(message: types.Message):
    premium_text = """💎 Премиум подписка

🚀 Безлимитный трафик
⚡ Максимальная скорость
🌍 Германия 🇩🇪
📱 До 5 устройств

💰 Цена: 300₽/месяц

Для покупки напишите @your_username"""
    
    await message.answer(premium_text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """❓ Помощь

Основные команды:
/start - Получить бесплатный ключ
/keys - Мои ключи
/profile - Мой профиль
/premium - Премиум подписка

Как подключиться:
1. Скопируйте ключ из /keys
2. Откройте v2rayN/Hiddify/v2rayNG
3. Импортируйте из буфера обмена

Поддержка: @your_username"""
    
    await message.answer(help_text)

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
