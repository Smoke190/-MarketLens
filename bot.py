import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

PORT = int(os.getenv("PORT", "10000"))

SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ==================================================
# RENDER HEALTH SERVER
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"MarketLens Vision is running")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )
    server.serve_forever()


# ==================================================
# TELEGRAM COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🧠 MARKETLENS v0.3\n\n"
        "Vision Engine готов.\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я попробую определить:\n"
        "• направление\n"
        "• структуру рынка\n"
        "• поддержку/сопротивление\n"
        "• свечные сигналы\n"
        "• объём\n"
        "• основной сценарий"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📚 MARKETLENS\n\n"
        "/start — запуск\n"
        "/help — помощь\n\n"
        "📸 Отправь скриншот графика."
    )


# ==================================================
# VISION ANALYSIS
# ==================================================

def analyze_chart(image_path):

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY не установлен"
        )

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    with open(image_path, "rb") as image_file:

        import base64

        image_base64 = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    prompt = """
Ты — технический аналитик MarketLens.

Проанализируй изображение торгового графика.

НЕ придумывай значения, которых невозможно увидеть
на изображении.

Определи:

1. Актив/валютную пару, если она видна.
2. Таймфрейм, если он виден.
3. Направление:
   ВВЕРХ / ВНИЗ / БОКОВИК / НЕОПРЕДЕЛЁННО
4. Рыночную структуру:
   HH, HL, LH, LL, либо боковик.
5. Ближайшую поддержку.
6. Ближайшее сопротивление.
7. Свечные паттерны, если они действительно видны.
8. Объём, если индикатор объёма присутствует.
9. Импульс или коррекцию.
10. Основной сценарий движения.
11. Альтернативный сценарий.
12. Что должно произойти для подтверждения сценария.
13. Что отменяет сценарий.

Если график недостаточно качественный,
напиши:

"НЕДОСТАТОЧНО ДАННЫХ — НУЖЕН НОВЫЙ СКРИНШОТ"

Не используй выдуманную точность.

Ответ должен быть коротким и структурированным.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt
                    },
                    {
                        "type": "input_image",
                        "image_url": (
                            f"data:image/jpeg;base64,"
                            f"{image_base64}"
                        )
                    }
                ]
            }
        ]
    )

    return response.output_text


# ==================================================
# IMAGE RECEIVER
# ==================================================

async def receive_screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:
        return

    try:

        await message.reply_text(
            "📸 Скриншот получен.\n\n"
            "🧠 Vision Engine анализирует график..."
        )

        # Берём изображение максимального качества
        photo = message.photo[-1]

        telegram_file = await context.bot.get_file(
            photo.file_id
        )

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

        await telegram_file.download_to_drive(
            custom_path=filepath
        )

        print(
            f"[SCREENSHOT] Saved: {filepath}"
        )

        # Vision
        analysis = analyze_chart(filepath)

        # Ограничиваем размер Telegram-сообщения
        if len(analysis) > 3900:
            analysis = analysis[:3900]

        await message.reply_text(
            "🧠 MARKETLENS\n\n"
            + analysis
            + "\n\n"
            "⚠️ Анализ является технической оценкой, "
            "а не гарантией движения цены."
        )

    except Exception as error:

        print(
            f"[ERROR] {type(error).__name__}: {error}"
        )

        await message.reply_text(
            "❌ Не удалось выполнить Vision-анализ.\n\n"
            f"Причина: {type(error).__name__}\n\n"
            "Проверь настройки Vision API."
        )


# ==================================================
# MAIN
# ==================================================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не установлен"
        )

    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    print(
        f"HTTP server started on port {PORT}"
    )

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

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

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_screenshot
        )
    )

    print(
        "🧠 MarketLens Vision Engine started"
    )

    app.run_polling()


if __name__ == "__main__":
    main()