import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# Папка для сохранения скриншотов
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# --------------------------------------------------
# HTTP SERVER FOR RENDER
# --------------------------------------------------

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"MarketLens v0.2 is running")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


# --------------------------------------------------
# TELEGRAM COMMANDS
# --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🧠 MARKETLENS v0.2\n\n"
        "Я готов принимать графики.\n\n"
        "📸 Отправь мне скриншот TradingView.\n\n"
        "После получения я сохраню изображение "
        "для дальнейшего технического анализа."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📚 MARKETLENS\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот графика."
    )


# --------------------------------------------------
# IMAGE PROCESSING
# --------------------------------------------------

async def receive_screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message or not message.photo:
        return

    try:

        # Берём изображение максимального качества
        photo = message.photo[-1]

        # Получаем файл Telegram
        telegram_file = await context.bot.get_file(photo.file_id)

        # Уникальное имя
        timestamp = datetime.utcnow().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        user_id = message.from_user.id

        filename = (
            f"chart_{user_id}_{timestamp}.jpg"
        )

        filepath = os.path.join(
            SCREENSHOT_DIR,
            filename
        )

        # Сохраняем изображение
        await telegram_file.download_to_drive(
            custom_path=filepath
        )

        # Информация о файле
        file_size = os.path.getsize(filepath)

        size_kb = round(
            file_size / 1024,
            1
        )

        # Ответ пользователю
        await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 Файл: {filename}\n"
            f"📦 Размер: {size_kb} KB\n\n"
            "✅ Изображение сохранено.\n\n"
            "🧠 Следующий этап:\n"
            "Technical Engine проанализирует "
            "структуру графика, уровни, свечи и объём."
        )

        print(
            f"[SCREENSHOT] Saved: {filepath}"
        )

    except Exception as error:

        print(
            f"[ERROR] Screenshot processing: {error}"
        )

        await message.reply_text(
            "❌ Не удалось сохранить скриншот.\n\n"
            "Попробуй отправить изображение ещё раз."
        )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing"
        )

    # Запускаем HTTP сервер для Render
    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    print(
        f"HTTP server started on port {PORT}"
    )

    # Telegram application
    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    # Images
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_screenshot
        )
    )

    print(
        "🧠 MarketLens v0.2 started successfully"
    )

    # Запуск Telegram polling
    app.run_polling()


if __name__ == "__main__":
    main()