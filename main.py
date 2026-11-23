
import asyncio
import logging
import os
import random
import re
import sqlite3
import string
from threading import Thread

import aiohttp
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, LabeledPrice
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "")
MAIN_ADMIN_ID = 8438026734
RENDER_URL = "https://portals-ams5.onrender.com"

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


# -------------------- СОСТОЯНИЯ --------------------

class AdminStates(StatesGroup):
    check_amount = State()
    check_currency = State()
    check_uses = State()
    check_password = State()
    balance_target = State()
    balance_amount = State()
    balance_currency = State()


class UserStates(StatesGroup):
    deposit_amount = State()
    crypto_amount = State()
    check_activation = State()
    withdraw_currency = State()
    withdraw_amount = State()
    withdraw_address = State()


# -------------------- БАЗА ДАННЫХ --------------------

def db():
    return sqlite3.connect("users.db")


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        role TEXT DEFAULT 'frish',
        balance_stars REAL DEFAULT 0,
        balance_gram REAL DEFAULT 0,
        balance_usdt REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS checks (
        code TEXT PRIMARY KEY,
        amount REAL,
        currency TEXT,
        uses_left INTEGER,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        currency TEXT,
        amount REAL,
        kind TEXT,
        note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        currency TEXT,
        amount REAL,
        address TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    INSERT OR IGNORE INTO users (id, username, role)
    VALUES (?, 'admin', 'admin')
    """, (MAIN_ADMIN_ID,))

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result


def get_user_id(target):
    conn = db()
    cur = conn.cursor()

    if target.startswith("@"):
        cur.execute(
            "SELECT id FROM users WHERE username=?",
            (target,)
        )
    else:
        try:
            cur.execute(
                "SELECT id FROM users WHERE id=?",
                (int(target),)
            )
        except ValueError:
            conn.close()
            return None

    result = cur.fetchone()
    conn.close()
    return result[0] if result else None


def is_admin(user_id):
    user = get_user(user_id)
    return bool(user and user[2] == "admin")


def log_transaction(user_id, currency, amount, kind, note=""):
    conn = db()
    conn.execute("""
        INSERT INTO transactions
        (user_id, currency, amount, kind, note)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, currency, amount, kind, str(note)))
    conn.commit()
    conn.close()


def change_balance(user_id, currency, amount):
    columns = {
        "stars": "balance_stars",
        "gram": "balance_gram",
        "usdt": "balance_usdt"
    }

    if currency not in columns:
        raise ValueError("Неизвестная валюта")

    conn = db()
    cur = conn.cursor()

    cur.execute(
        f"UPDATE users SET {columns[currency]} = "
        f"{columns[currency]} + ? WHERE id=?",
        (amount, user_id)
    )

    if cur.rowcount:
        cur.execute("""
            INSERT INTO transactions
            (user_id, currency, amount, kind)
            VALUES (?, ?, ?, ?)
        """, (user_id, currency, amount, "balance_change"))

    conn.commit()
    conn.close()


def create_check(amount, currency, uses, password):
    code = "".join(
        random.choices(string.ascii_uppercase + string.digits, k=8)
    )

    conn = db()
    conn.execute("""
        INSERT INTO checks
        (code, amount, currency, uses_left, password)
        VALUES (?, ?, ?, ?, ?)
    """, (code, amount, currency, uses, password))
    conn.commit()
    conn.close()

    return code


init_db()


# -------------------- ВЕБ-СЕРВЕР --------------------

app = Flask(__name__)


@app.route("/")
def index():
    return "Bot is running!"


def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )


async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RENDER_URL) as response:
                    pass
        except Exception:
            logging.exception("Keep alive error")

        await asyncio.sleep(600)


# -------------------- ОБЩИЕ КЛАВИАТУРЫ --------------------

def main_menu(user_id):
    user = get_user(user_id)

    if not user:
        return "Пользователь не найден.", None

    text = (
        "👋 <b>Главное меню</b>\n\n"
        f"⭐ Stars: {user[3]}\n"
        f"💎 TON: {user[4]}\n"
        f"💵 USDT: {user[5]}\n\n"
        "Выберите действие:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💰 Пополнить баланс",
            callback_data="deposit"
        )],
        [InlineKeyboardButton(
            text="📤 Вывести баланс",
            callback_data="withdraw"
        )],
        [InlineKeyboardButton(
            text="🎁 Активировать чек",
            callback_data="activate_check"
        )],
        [InlineKeyboardButton(
            text="📖 Инструкция",
            callback_data="tutor"
        )]
    ])

    return text, keyboard


async def send_application(user_obj):
    uid = user_obj.id
    username = (
        f"@{user_obj.username}"
        if user_obj.username else "нет"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Юзер",
                callback_data=f"approve:user:{uid}"
            ),
            InlineKeyboardButton(
                text="🦣 Фришный",
                callback_data=f"approve:frish:{uid}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⛔ Заблокировать",
                callback_data=f"block:{uid}"
            )
        ]
    ])

    await bot.send_message(
        MAIN_ADMIN_ID,
        f"🔔 <b>Новая заявка</b>\n\n"
        f"👤 {user_obj.full_name}\n"
        f"🆔 <code>{uid}</code>\n"
        f"🔗 {username}",
        reply_markup=keyboard
    )


# -------------------- START --------------------

@dp.message(F.text.startswith("/start"))
async def start_command(message: types.Message, state: FSMContext):
    uid = message.from_user.id

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username else "нет"
    )

    conn = db()
    conn.execute("""
        INSERT OR IGNORE INTO users (id, username, role)
        VALUES (?, ?, 'frish')
    """, (uid, username))

    conn.execute(
        "UPDATE users SET username=? WHERE id=?",
        (username, uid)
    )

    conn.commit()
    conn.close()

    user = get_user(uid)

    if user[2] == "blocked":
        await message.answer(
            "⛔ Доступ к боту ограничен администрацией."
        )
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) > 1 and parts[1].startswith("check_"):
        code = parts[1][6:]
        await state.update_data(check_code=code)
        await message.answer(
            "Введите пароль чека или напишите «нет», если пароля нет:"
        )
        await state.set_state(UserStates.check_activation)
        return

    if user[2] in ("admin", "user", "frish"):
        text, keyboard = main_menu(uid)
        await message.answer(text, reply_markup=keyboard)
        return

    await send_application(message.from_user)


@dp.message(F.text == "/verify")
async def verify_command(message: types.Message):
    user = get_user(message.from_user.id)

    if user and user[2] == "blocked":
        await message.answer("⛔ Вы заблокированы.")
        return

    await send_application(message.from_user)


# -------------------- ИНСТРУКЦИЯ --------------------

@dp.callback_query(F.data == "tutor")
async def tutor(callback: types.CallbackQuery):
    await callback.message.answer(
        "📖 <b>Инструкция</b>\n\n"
        "Для создания предложения:\n"
        "<code>/price ссылка цена валюта</code>\n\n"
        "Валюты: gram, stars, usdt."
    )
    await callback.answer()


# -------------------- ПОПОЛНЕНИЕ STARS --------------------

@dp.callback_query(F.data == "deposit")
async def deposit(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user or user[2] == "blocked":
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⭐ Telegram Stars",
            callback_data="dep_stars"
        )],
        [InlineKeyboardButton(
            text="💎 TON",
            callback_data="dep_ton"
        )],
        [InlineKeyboardButton(
            text="💵 USDT",
            callback_data="dep_usdt"
        )]
    ])

    await callback.message.answer(
        "Выберите валюту пополнения:",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data == "dep_stars")
async def dep_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите количество Stars:"
    )
    await state.set_state(UserStates.deposit_amount)
    await callback.answer()


@dp.message(UserStates.deposit_amount)
async def process_stars_amount(
    message: types.Message,
    state: FSMContext
):
    try:
        amount = int(message.text)

        if amount <= 0:
            raise ValueError()

        await bot.send_invoice(
            chat_id=message.chat.id,
            title="Пополнение баланса",
            description=f"Пополнение на {amount} Stars",
            payload=f"stars:{message.from_user.id}:{amount}",
            currency="XTR",
            prices=[
                LabeledPrice(label="Telegram Stars", amount=amount)
            ],
            provider_token=""
        )

        await state.clear()

    except ValueError:
        await message.answer(
            "Введите положительное целое число."
        )
    except Exception:
        logging.exception("Stars invoice error")
        await message.answer(
            "Не удалось создать счёт. Попробуйте позже."
        )


@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    try:
        payment = message.successful_payment
        prefix, uid_text, amount_text = (
            payment.invoice_payload.split(":")
        )

        uid = int(uid_text)
        amount = int(amount_text)

        if prefix != "stars" or uid != message.from_user.id:
            return

        conn = db()
        cur = conn.cursor()

        existing = cur.execute(
            "SELECT id FROM transactions WHERE note=?",
            (payment.telegram_payment_charge_id,)
        ).fetchone()

        if existing:
            conn.close()
            return

        cur.execute("""
            UPDATE users
            SET balance_stars = balance_stars + ?
            WHERE id=?
        """, (amount, uid))

        cur.execute("""
            INSERT INTO transactions
            (user_id, currency, amount, kind, note)
            VALUES (?, ?, ?, ?, ?)
        """, (
            uid, "stars", amount,
            "telegram_stars",
            payment.telegram_payment_charge_id
        ))

        conn.commit()
        conn.close()

        await message.answer(
            f"✅ Оплата подтверждена Telegram.\n"
            f"Зачислено: {amount} Stars."
        )

    except Exception:
        logging.exception("Stars payment error")
        await message.answer(
            "Ошибка зачисления. Обратитесь к администратору."
        )


# -------------------- CRYPTO PAY --------------------

@dp.callback_query(F.data.in_({"dep_ton", "dep_usdt"}))
async def crypto_deposit_start(
    callback: types.CallbackQuery,
    state: FSMContext
):
    if not CRYPTOBOT_TOKEN:
        await callback.answer(
            "Crypto Pay не настроен администратором.",
            show_alert=True
        )
        return

    asset = "TON" if callback.data == "dep_ton" else "USDT"

    await state.update_data(crypto_asset=asset)

    await callback.message.answer(
        f"Введите сумму в {asset}:"
    )

    await state.set_state(UserStates.crypto_amount)
    await callback.answer()


@dp.message(UserStates.crypto_amount)
async def crypto_amount(
    message: types.Message,
    state: FSMContext
):
    try:
        amount = float(message.text.replace(",", "."))

        if amount <= 0:
            raise ValueError()

        data = await state.get_data()
        asset = data["crypto_asset"]

        headers = {
            "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
        }

        payload = {
            "asset": asset,
            "amount": str(amount),
            "description": "Пополнение баланса",
            "payload": f"{message.from_user.id}:{asset}:{amount}",
            "expires_in": 3600
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/createInvoice",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()

        if not result.get("ok"):
            raise RuntimeError("Invoice creation failed")

        invoice = result["result"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Проверить оплату",
                callback_data=f"checkpay:{invoice['invoice_id']}"
            )]
        ])

        await message.answer(
            f"Счёт создан на {amount} {asset}.\n"
            f"Оплатите: {invoice['pay_url']}",
            reply_markup=keyboard
        )

        await state.clear()

    except ValueError:
        await message.answer("Введите положительную сумму.")
    except Exception:
        logging.exception("Crypto invoice error")
        await message.answer(
            "Не удалось создать счёт. Проверьте настройки Crypto Pay."
        )


@dp.callback_query(F.data.startswith("checkpay:"))
async def check_crypto_payment(callback: types.CallbackQuery):
    if not CRYPTOBOT_TOKEN:
        await callback.answer("Crypto Pay не настроен.", show_alert=True)
        return

    try:
        invoice_id = callback.data.split(":", 1)[1]

        headers = {
            "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pay.crypt.bot/api/getInvoices",
                params={"invoice_ids": invoice_id},
                headers=headers
            ) as response:
                result = await response.json()

        items = result.get("result", {}).get("items", [])

        if (
            not result.get("ok")
            or not items
            or items[0].get("status") != "paid"
        ):
            await callback.answer(
                "Оплата пока не подтверждена.",
                show_alert=True
            )
            return

        invoice = items[0]
        uid_text, asset, amount_text = invoice["payload"].split(":")

        uid = int(uid_text)
        amount = float(amount_text)

        conn = db()
        cur = conn.cursor()

        existing = cur.execute("""
            SELECT id FROM transactions
            WHERE kind='cryptopay' AND note=?
        """, (str(invoice_id),)).fetchone()

        if existing:
            conn.close()
            await callback.answer(
                "Этот платёж уже зачислен.",
                show_alert=True
            )
            return

        column = (
            "balance_gram" if asset == "TON"
            else "balance_usdt"
        )

        currency = "gram" if asset == "TON" else "usdt"

        cur.execute(
            f"UPDATE users SET {column}={column}+? WHERE id=?",
            (amount, uid)
        )

        cur.execute("""
            INSERT INTO transactions
            (user_id, currency, amount, kind, note)
            VALUES (?, ?, ?, ?, ?)
        """, (
            uid, currency, amount,
            "cryptopay", str(invoice_id)
        ))

        conn.commit()
        conn.close()

        await callback.message.answer(
            f"✅ Оплата подтверждена.\n"
            f"Зачислено: {amount} {asset}."
        )

        await callback.answer("Зачислено.")

    except Exception:
        logging.exception("Crypto payment verification error")
        await callback.answer(
            "Ошибка проверки оплаты.",
            show_alert=True
        )


# -------------------- АКТИВАЦИЯ ЧЕКОВ --------------------

@dp.callback_query(F.data == "activate_check")
async def activate_check(
    callback: types.CallbackQuery,
    state: FSMContext
):
    user = get_user(callback.from_user.id)

    if not user or user[2] == "blocked":
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    await state.update_data(check_code=None)

    await callback.message.answer(
        "Введите код чека и пароль через пробел, если он есть:"
    )

    await state.set_state(UserStates.check_activation)
    await callback.answer()


@dp.message(UserStates.check_activation)
async def process_check(
    message: types.Message,
    state: FSMContext
):
    user = get_user(message.from_user.id)

    if not user or user[2] == "blocked":
        await message.answer("⛔ Доступ ограничен.")
        await state.clear()
        return

    data = await state.get_data()
    parts = message.text.split()

    code = data.get("check_code") or parts[0].upper()

    if data.get("check_code"):
        password = (
            None if message.text.strip().lower() == "нет"
            else message.text.strip()
        )
    else:
        password = parts[1] if len(parts) > 1 else None

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT amount, currency, uses_left, password
        FROM checks WHERE code=?
    """, (code,))

    check = cur.fetchone()

    if not check:
        conn.close()
        await message.answer("❌ Чек не найден.")
        await state.clear()
        return

    amount, currency, uses_left, db_password = check

    if uses_left <= 0:
        conn.close()
        await message.answer("❌ Лимит активаций исчерпан.")
        await state.clear()
        return

    if db_password and db_password != password:
        conn.close()
        await message.answer("❌ Неверный пароль.")
        await state.clear()
        return

    columns = {
        "stars": "balance_stars",
        "gram": "balance_gram",
        "usdt": "balance_usdt"
    }

    if currency not in columns:
        conn.close()
        await message.answer("Ошибка валюты чека.")
        await state.clear()
        return

    cur.execute("""
        UPDATE checks
        SET uses_left=uses_left-1
        WHERE code=? AND uses_left>0
    """, (code,))

    if cur.rowcount != 1:
        conn.close()
        await message.answer("Чек уже активирован.")
        await state.clear()
        return

    cur.execute(
        f"UPDATE users SET {columns[currency]}="
        f"{columns[currency]}+? WHERE id=?",
        (amount, message.from_user.id)
    )

    cur.execute("""
        INSERT INTO transactions
        (user_id, currency, amount, kind, note)
        VALUES (?, ?, ?, ?, ?)
    """, (
        message.from_user.id,
        currency,
        amount,
        "check",
        code
    ))

    conn.commit()
    conn.close()

    await message.answer(
        f"🎉 Чек активирован!\n"
        f"Начислено: {amount} {currency.upper()}."
    )

    await state.clear()


# -------------------- АДМИН-ПАНЕЛЬ --------------------

@dp.message(F.text == "/adminpanel")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="👥 Список пользователей",
            callback_data="adm_list"
        )],
        [InlineKeyboardButton(
            text="🎁 Создать чек",
            callback_data="adm_check"
        )],
        [InlineKeyboardButton(
            text="➕➖ Изменить баланс",
            callback_data="adm_balance"
        )],
        [InlineKeyboardButton(
            text="📜 История операций",
            callback_data="adm_history"
        )],
        [InlineKeyboardButton(
            text="📥 Скачать базу",
            callback_data="adm_db"
        )]
    ])

    await message.answer(
        "👑 <b>Админ-панель</b>",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "adm_list")
async def admin_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    conn = db()
    users = conn.execute(
        "SELECT id, username, role FROM users"
    ).fetchall()
    conn.close()

    keyboard = []

    for uid, username, role in users:
        icon = {
            "admin": "👑",
            "user": "👤",
            "frish": "🦣",
            "blocked": "⛔"
        }.get(role, "👤")

        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {username}",
                callback_data=f"usr_{uid}"
            )
        ])

    await callback.message.edit_text(
        "👥 Выберите пользователя:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("usr_"))
async def user_manage(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[1])
    user = get_user(uid)

    if not user:
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Назначить админом",
            callback_data=f"set_admin_{uid}"
        )],
        [InlineKeyboardButton(
            text="Сделать фришным",
            callback_data=f"set_frish_{uid}"
        )],
        [InlineKeyboardButton(
            text="Сделать юзером",
            callback_data=f"set_user_{uid}"
        )],
        [InlineKeyboardButton(
            text="🔓 Разблокировать" if user[2] == "blocked"
            else "⛔ Заблокировать",
            callback_data=f"toggleblock_{uid}"
        )],
        [InlineKeyboardButton(
            text="📜 История",
            callback_data=f"history_{uid}"
        )]
    ])

    text = (
        f"👤 <b>Пользователь:</b> {user[1]}\n"
        f"🆔 ID: {uid}\n"
        f"Роль: {user[2]}\n\n"
        f"⭐ {user[3]} | 💎 {user[4]} | 💵 {user[5]}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("set_admin_"))
async def set_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[-1])
    update_role(uid, "admin")
    await callback.answer("Назначен администратором.")
    await user_manage(
        types.CallbackQuery.model_validate(
            {**callback.model_dump(), "data": f"usr_{uid}"}
        )
    )


@dp.callback_query(F.data.startswith("set_frish_"))
async def set_frish(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[-1])
    update_role(uid, "frish")
    await callback.answer("Роль изменена.")


@dp.callback_query(F.data.startswith("set_user_"))
async def set_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[-1])
    update_role(uid, "user")
    await callback.answer("Роль изменена.")


def update_role(uid, role):
    conn = db()
    conn.execute(
        "UPDATE users SET role=? WHERE id=?",
        (role, uid)
    )
    conn.commit()
    conn.close()


@dp.callback_query(F.data.startswith("toggleblock_"))
async def toggle_block(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[-1])

    if uid == MAIN_ADMIN_ID:
        await callback.answer(
            "Главного администратора блокировать нельзя.",
            show_alert=True
        )
        return

    user = get_user(uid)

    if not user:
        return

    role = "frish" if user[2] == "blocked" else "blocked"
    update_role(uid, role)

    try:
        await bot.send_message(
            uid,
            "⛔ Вы заблокированы администрацией."
            if role == "blocked"
            else "✅ Доступ восстановлен. Напишите /start."
        )
    except Exception:
        pass

    await callback.answer("Статус обновлён.")


# -------------------- ЗАЯВКИ НА ДОСТУП --------------------

@dp.callback_query(F.data.startswith("approve:"))
async def approve_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    _, role, uid_text = callback.data.split(":")
    uid = int(uid_text)

    if role not in ("user", "frish"):
        await callback.answer("Недопустимая роль.", show_alert=True)
        return

    conn = db()
    conn.execute("""
        INSERT OR IGNORE INTO users(id, username, role)
        VALUES (?, 'нет', ?)
    """, (uid, role))

    conn.execute(
        "UPDATE users SET role=? WHERE id=?",
        (role, uid)
    )

    conn.commit()
    conn.close()

    await callback.message.edit_text(
        f"✅ Пользователь {uid} одобрен как {role}."
    )

    try:
        await bot.send_message(
            uid,
            f"🎉 Ваша заявка одобрена. Роль: {role}.\n"
            "Напишите /start."
        )
    except Exception:
        pass

    await callback.answer()


@dp.callback_query(F.data.startswith("block:"))
async def block_application(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split(":")[1])

    if uid == MAIN_ADMIN_ID:
        return

    conn = db()
    conn.execute("""
        INSERT OR IGNORE INTO users(id, username, role)
        VALUES (?, 'нет', 'blocked')
    """, (uid,))

    conn.execute(
        "UPDATE users SET role='blocked' WHERE id=?",
        (uid,)
    )

    conn.commit()
    conn.close()

    await callback.message.edit_text("⛔ Пользователь заблокирован.")
    await callback.answer()


@dp.callback_query(F.data.startswith("reject:"))
async def reject_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split(":")[1])

    conn = db()
    conn.execute("""
        INSERT OR IGNORE INTO users(id, username, role)
        VALUES (?, 'нет', 'blocked')
    """, (uid,))

    conn.execute(
        "UPDATE users SET role='blocked' WHERE id=?",
        (uid,)
    )

    conn.commit()
    conn.close()

    await callback.message.edit_text(
        "⛔ Заявка отклонена, пользователь заблокирован."
    )
    await callback.answer()


# -------------------- ИЗМЕНЕНИЕ БАЛАНСА АДМИНОМ --------------------

@dp.callback_query(F.data == "adm_balance")
async def balance_start(
    callback: types.CallbackQuery,
    state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.answer(
        "Введите ID пользователя или @username:"
    )

    await state.set_state(AdminStates.balance_target)
    await callback.answer()


@dp.message(AdminStates.balance_target)
async def balance_target(
    message: types.Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    uid = get_user_id(message.text.strip())

    if not uid:
        await message.answer("Пользователь не найден.")
        return

    await state.update_data(uid=uid)

    await message.answer(
        "Введите сумму.\n"
        "Положительное число — начисление.\n"
        "Отрицательное — списание."
    )

    await state.set_state(AdminStates.balance_amount)


@dp.message(AdminStates.balance_amount)
async def balance_amount(
    message: types.Message,
    state: FSMContext
):
    try:
        amount = float(message.text.replace(",", "."))

        if amount == 0:
            raise ValueError()

        await state.update_data(amount=amount)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⭐ Stars",
                callback_data="adj:stars"
            )],
            [InlineKeyboardButton(
                text="💎 TON",
                callback_data="adj:gram"
            )],
            [InlineKeyboardButton(
                text="💵 USDT",
                callback_data="adj:usdt"
            )]
        ])

        await message.answer(
            "Выберите валюту:",
            reply_markup=keyboard
        )

        await state.set_state(AdminStates.balance_currency)

    except ValueError:
        await message.answer("Введите ненулевую сумму числом.")


@dp.callback_query(
    AdminStates.balance_currency,
    F.data.startswith("adj:")
)
async def balance_currency(
    callback: types.CallbackQuery,
    state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    currency = callback.data.split(":")[1]

    change_balance(
        data["uid"],
        currency,
        data["amount"]
    )

    await callback.message.answer(
        f"Баланс пользователя {data['uid']} изменён "
        f"на {data['amount']} {currency.upper()}."
    )

    await state.clear()
    await callback.answer("Готово.")


# -------------------- СОЗДАНИЕ ЧЕКОВ --------------------

@dp.callback_query(F.data == "adm_check")
async def admin_check(
    callback: types.CallbackQuery,
    state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.answer("Введите сумму чека:")
    await state.set_state(AdminStates.check_amount)
    await callback.answer()


@dp.message(AdminStates.check_amount)
async def check_amount(
    message: types.Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    try:
        amount = float(message.text.replace(",", "."))

        if amount <= 0:
            raise ValueError()

        await state.update_data(amount=amount)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Stars",
                callback_data="chk_stars"
            )],
            [InlineKeyboardButton(
                text="TON",
                callback_data="chk_gram"
            )],
            [InlineKeyboardButton(
                text="USDT",
                callback_data="chk_usdt"
            )]
        ])

        await message.answer(
            "Выберите валюту:",
            reply_markup=keyboard
        )

        await state.set_state(AdminStates.check_currency)

    except ValueError:
        await message.answer("Введите положительную сумму.")


@dp.callback_query(
    AdminStates.check_currency,
    F.data.startswith("chk_")
)
async def check_currency(
    callback: types.CallbackQuery,
    state: FSMContext
):
    currency = callback.data.split("_")[1]

    await state.update_data(currency=currency)

    await callback.message.answer(
        "Введите количество активаций:"
    )

    await state.set_state(AdminStates.check_uses)
    await callback.answer()


@dp.message(AdminStates.check_uses)
async def check_uses(
    message: types.Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    try:
        uses = int(message.text)

        if uses <= 0:
            raise ValueError()

        await state.update_data(uses=uses)

        await message.answer(
            "Введите пароль или напишите «нет»:"
        )

        await state.set_state(AdminStates.check_password)

    except ValueError:
        await message.answer("Введите положительное целое число.")


@dp.message(AdminStates.check_password)
async def check_password(
    message: types.Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    password = (
        None if message.text.lower() == "нет"
        else message.text
    )

    data = await state.get_data()

    code = create_check(
        data["amount"],
        data["currency"],
        data["uses"],
        password
    )

    link = f"https://t.me/portals_nftbot?start=check_{code}"

    await message.answer(
        f"✅ <b>Чек создан</b>\n\n"
        f"Код: <code>{code}</code>\n"
        f"Ссылка: {link}\n"
        f"Валюта: {data['currency']}\n"
        f"Сумма: {data['amount']}\n"
        f"Активаций: {data['uses']}\n"
        f"Пароль: {password or 'нет'}"
    )

    await state.clear()


# -------------------- ВЫВОД: ТОЛЬКО ЗАЯВКИ --------------------

@dp.callback_query(F.data == "withdraw")
async def withdraw_start(
    callback: types.CallbackQuery,
    state: FSMContext
):
    user = get_user(callback.from_user.id)

    if not user or user[2] == "blocked":
        await callback.answer("Доступ запрещён.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Stars",
            callback_data="wd:stars"
        )],
        [InlineKeyboardButton(
            text="TON",
            callback_data="wd:gram"
        )],
        [InlineKeyboardButton(
            text="USDT",
            callback_data="wd:usdt"
        )]
    ])

    await callback.message.answer(
        "Вывод оформляется только заявкой.\n"
        "Бот не отправляет деньги и не списывает баланс.",
        reply_markup=keyboard
    )

    await state.set_state(UserStates.withdraw_currency)
    await callback.answer()


@dp.callback_query(
    UserStates.withdraw_currency,
    F.data.startswith("wd:")
)
async def withdraw_currency(
    callback: types.CallbackQuery,
    state: FSMContext
):
    currency = callback.data.split(":")[1]

    await state.update_data(currency=currency)

    await callback.message.answer("Введите сумму заявки:")
    await state.set_state(UserStates.withdraw_amount)
    await callback.answer()


@dp.message(UserStates.withdraw_amount)
async def withdraw_amount(
    message: types.Message,
    state: FSMContext
):
    try:
        amount = float(message.text.replace(",", "."))

        if amount <= 0:
            raise ValueError()

        await state.update_data(amount=amount)

        data = await state.get_data()

        if data["currency"] == "stars":
            await save_withdrawal(message, state, "")
        else:
            await message.answer("Введите адрес кошелька:")
            await state.set_state(UserStates.withdraw_address)

    except ValueError:
        await message.answer("Введите положительную сумму.")


@dp.message(UserStates.withdraw_address)
async def withdraw_address(
    message: types.Message,
    state: FSMContext
):
    address = message.text.strip()

    if len(address) < 8 or len(address) > 160:
        await message.answer("Проверьте адрес и отправьте ещё раз.")
        return

    await save_withdrawal(message, state, address)


async def save_withdrawal(
    message: types.Message,
    state: FSMContext,
    address: str
):
    data = await state.get_data()
    uid = message.from_user.id

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO withdrawals
        (user_id, currency, amount, address)
        VALUES (?, ?, ?, ?)
    """, (
        uid,
        data["currency"],
        data["amount"],
        address
    ))

    request_id = cur.lastrowid

    cur.execute("""
        INSERT INTO transactions
        (user_id, currency, amount, kind, note)
        VALUES (?, ?, ?, ?, ?)
    """, (
        uid,
        data["currency"],
        0,
        "withdraw_request",
        str(request_id)
    ))

    conn.commit()
    conn.close()

    await message.answer(
        f"✅ Заявка №{request_id} отправлена администрации.\n"
        "Автоматической выплаты нет."
    )

    try:
        await bot.send_message(
            MAIN_ADMIN_ID,
            f"📤 <b>Заявка на вывод №{request_id}</b>\n\n"
            f"Пользователь: <code>{uid}</code>\n"
            f"Сумма: {data['amount']} "
            f"{data['currency'].upper()}\n"
            f"Адрес: <code>{address or 'не требуется'}</code>"
        )
    except Exception:
        logging.exception("Withdrawal notification error")

    await state.clear()


# -------------------- ИСТОРИЯ --------------------

@dp.callback_query(F.data == "adm_history")
async def admin_history(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    conn = db()
    rows = conn.execute("""
        SELECT user_id, currency, amount, kind, created_at
        FROM transactions
        ORDER BY id DESC LIMIT 25
    """).fetchall()
    conn.close()

    if not rows:
        await callback.message.answer("История операций пуста.")
    else:
        text = "📜 <b>Последние операции</b>\n\n"

        for uid, currency, amount, kind, date in rows:
            text += (
                f"ID {uid}: {amount:+g} {currency.upper()}\n"
                f"{kind} · {date}\n\n"
            )

        await callback.message.answer(text)

    await callback.answer()


@dp.callback_query(F.data.startswith("history_"))
async def user_history(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split("_")[1])

    conn = db()
    rows = conn.execute("""
        SELECT currency, amount, kind, created_at
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC LIMIT 20
    """, (uid,)).fetchall()
    conn.close()

    text = f"📜 <b>История пользователя {uid}</b>\n\n"

    if not rows:
        text += "Операций нет."
    else:
        for currency, amount, kind, date in rows:
            text += (
                f"{amount:+g} {currency.upper()} · "
                f"{kind} · {date}\n"
            )

    await callback.message.answer(text)
    await callback.answer()


# -------------------- СКАЧАТЬ БАЗУ --------------------

@dp.callback_query(F.data == "adm_db")
async def admin_database(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    try:
        await callback.message.answer_document(
            FSInputFile("users.db"),
            caption="База данных пользователей"
        )
    except Exception:
        logging.exception("Database export error")
        await callback.message.answer(
            "Не удалось отправить базу."
        )

    await callback.answer()


# -------------------- NFT-ПРЕДЛОЖЕНИЯ --------------------

async def create_offer(
    chat_id,
    user_id,
    full_name,
    text,
    biz_id=None
):
    match = re.match(
        r"^/price\s+(https?://\S+)\s+([\d.]+)\s+(gram|stars|usdt)",
        text,
        re.IGNORECASE
    )

    if not match:
        return

    nft_link, price, currency = match.groups()

    user_link = (
        f"<a href='tg://user?id={user_id}'>"
        f"{full_name}</a>"
    )

    message_text = (
        f"Пользователь {user_link} предлагает "
        f"{price} {currency.upper()} за подарок.\n\n"
        f"<a href='{nft_link}'>Открыть ссылку</a>\n\n"
        "Условия оплаты и передачи необходимо согласовать "
        "напрямую. Бот не предоставляет эскроу и не гарантирует "
        "платёж или передачу подарка."
    )

    await bot.send_message(
        chat_id,
        message_text,
        business_connection_id=biz_id
    )


@dp.message(F.text.regexp(r"^/price\s+"))
async def handle_price(message: types.Message):
    user = get_user(message.from_user.id)

    if not user or user[2] not in ("admin", "user"):
        return

    await create_offer(
        message.chat.id,
        message.from_user.id,
        message.from_user.full_name,
        message.text
    )


# -------------------- ЗАПУСК --------------------

async def main():
    Thread(
        target=run_flask,
        daemon=True
    ).start()

    asyncio.create_task(keep_alive())

    logging.info("Bot started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped")
