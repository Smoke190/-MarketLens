import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 MarketLens v0.1\n\n"
        "Пришли мне скриншот графика, и я подготовлю технический анализ."
    )

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Скриншот получен.\n\n"
        "MarketLens v0.1 пока находится в тестовом режиме.\n"
        "Technical Engine подключим следующим этапом."
    )

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))

    print("MarketLens started")
    app.run_polling()

if __name__ == "__main__":
    main()