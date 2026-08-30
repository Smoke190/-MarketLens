import os
import threading
import base64
import requests

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

VISION_URL = (
    "https://developer0hye-qwen2-5-vl-7b-instruct.hf.space"
    "/run/qwen_vl_inference"
)

SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ==============================
# RENDER SERVER
# ==============================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"MarketLens Vision is running"
        )

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )
    server.serve_forever()


# ==============================
# TELEGRAM
# ==============================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🧠 MARKETLENS v0.4\n\n"
        "Vision Engine готов.\n\n"
        "📸 Отправь скриншот TradingView."
    )


# ==============================
# VISION
# ==============================

def analyze_chart(image_path):

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    prompt = """
Ты — Technical Engine MarketLens.

Проанализируй торговый график на изображении.

Определи только то, что реально видно.

Нужно определить:

1. Актив / валютную пару.
2. Таймфрейм.
3. Направление:
ВВЕРХ / ВНИЗ / БОКОВИК / НЕОПРЕДЕЛЁННО.

4. Рыночную структуру:
HH / HL / LH / LL.

5. Ближайшую поддержку.

6. Ближайшее сопротивление.

7. Свечную структуру.

8. Разворотные паттерны, если они действительно видны.

9. Объём, если он присутствует.

10. Импульс или коррекцию.

11. Основной сценарий.

12. Альтернативный сценарий.

13. Условия подтверждения.

14. Условия отмены.

Не выдумывай значения.

Если график плохо виден, напиши:

НЕДОСТАТОЧНО ДАННЫХ — НУЖЕН НОВЫЙ СКРИНШОТ.

Формат:

📊 MARKETLENS

Актив:
Таймфрейм:

📈 Тренд:
📊 Структура:

🟢 Поддержка:
🔴 Сопротивление:

🕯 Свечи:
📊 Объём:

🎯 Основной сценарий:
🔄 Альтернативный сценарий:

✅ Подтверждение:
❌ Отмена:

📌 Итог:
"""

    payload = {
        "data": [
            {
                "path": None,
                "url": (
                    "data:image/jpeg;base64,"
                    + image_base64
                ),
                "size": len(image_bytes),
                "orig_name": "chart.jpg",
                "mime_type": "image/jpeg",
                "is_stream": False,
                "meta": {
                    "_type": "gradio.FileData"
                }
            },
            prompt
        ]
    }

    response = requests.post(
        VISION_URL,
        json=payload,
        timeout=180
    )

    # Подробный вывод ошибки
    if response.status_code != 200:

        print(
            f"[VISION ERROR] HTTP "
            f"{response.status_code}"
        )

        print(
            "[VISION ERROR] Response:"
        )

        print(
            response.text[:2000]
        )

        raise RuntimeError(
            f"Vision HTTP "
            f"{response.status_code}"
        )

    result = response.json()

    print(
        "[VISION] Response received"
    )

    return extract_result(result)


# ==============================
# RESULT
# ==============================

def extract_result(result):

    if "output" in result:

        output = result["output"]

        if isinstance(output, str):
            return output

        return str(output)

    if "data" in result:

        data = result["data"]

        if isinstance(data, list):

            if len(data) > 0:

                if isinstance(data[0], str):
                    return data[0]

                return str(data[0])

        return str(data)

    return str(result)


# ==============================
# SCREENSHOT
# ==============================

async def receive_screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:
        return

    if not message.photo:
        return

    try:

        await message.reply_text(
            "📸 Скриншот получен.\n\n"
            "🧠 Vision Engine анализирует..."
        )

        photo = message.photo[-1]

        telegram_file = (
            await context.bot.get_file(
                photo.file_id
            )
        )

        timestamp = datetime.utcnow().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        user_id = message.from_user.id

        filename = (
            f"chart_{user_id}_"
            f"{timestamp}.jpg"
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

        analysis = analyze_chart(
            filepath
        )

        if len(analysis) > 3900:
            analysis = analysis[:3900]

        await message.reply_text(
            analysis
            + "\n\n"
            "⚠️ Технический анализ не является "
            "гарантией движения цены."
        )

    except Exception as error:

        print(
            f"[ERROR] {type(error).__name__}: "
            f"{error}"
        )

        await message.reply_text(
            "❌ Vision Engine не смог "
            "обработать график.\n\n"
            f"Ошибка: {type(error).__name__}"
        )


# ==============================
# MAIN
# ==============================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден"
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
        MessageHandler(
            filters.PHOTO,
            receive_screenshot
        )
    )

    print(
        "🧠 MarketLens Vision started"
    )

    app.run_polling()


if __name__ == "__main__":
    main()