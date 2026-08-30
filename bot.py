import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from gradio_client import Client, handle_file
# ============================================================
# MARKETLENS v0.9
# Telegram + Qwen2.5-VL Gradio Space
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ============================================================
# QWEN SPACE
# ============================================================
VISION_SPACE = "developer0hye/Qwen2.5-VL-7B-Instruct"
# Endpoint confirmed from the Space API
VISION_API_NAME = "/qwen_vl_inference"
# ============================================================
# DIRECTORIES
# ============================================================
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MarketLens")
# ============================================================
# RENDER HEALTH SERVER
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"MarketLens v0.9 is running"
        )
    def log_message(self, format, *args):
        return
def start_http_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )
    print(
        f"HTTP server started on port {port}"
    )
    server.serve_forever()
# ============================================================
# QWEN VISION
# ============================================================
def qwen_analyze_image(
    image_path: str,
    question: str,
):
    """
    Sends image to Qwen2.5-VL Space using gradio_client.
    """
    print("[VISION] Connecting to Qwen Space...")
    print(f"[VISION] Space: {VISION_SPACE}")
    print(f"[VISION] Endpoint: {VISION_API_NAME}")
    try:
        client = Client(
            VISION_SPACE
        )
        print("[VISION] Client connected")
        print("[VISION] Preparing image...")
        image = handle_file(
            image_path
        )
        print("[VISION] Sending image to Qwen...")
        result = client.predict(
            image,
            question,
            api_name=VISION_API_NAME,
        )
        print("[VISION] Response received")
        print(
            f"[VISION] Result type: {type(result)}"
        )
        if result is None:
            raise RuntimeError(
                "Qwen returned empty result"
            )
        result_text = str(result).strip()
        if not result_text:
            raise RuntimeError(
                "Qwen returned empty text"
            )
        print("[VISION] Analysis successful")
        return result_text
    except Exception as e:
        logger.exception(
            "[VISION ERROR]"
        )
        raise RuntimeError(
            f"Qwen Vision error: {type(e).__name__}: {e}"
        )
# ============================================================
# ASYNC WRAPPER
# ============================================================
async def analyze_with_vision(
    image_path: str,
    question: str,
):
    """
    Runs blocking Gradio request
    in a background thread.
    """
    import asyncio
    return await asyncio.to_thread(
        qwen_analyze_image,
        image_path,
        question,
    )
# ============================================================
# START COMMAND
# ============================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "🧠 MARKETLENS v0.9\n\n"
        "Vision Engine: ONLINE\n"
        "Qwen2.5-VL: CONNECTED\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я:\n"
        "1️⃣ Сохраню график\n"
        "2️⃣ Передам его Qwen Vision\n"
        "3️⃣ Получу описание графика\n"
        "4️⃣ Верну анализ сюда\n\n"
        "⚠️ Анализ является технической оценкой, "
        "а не гарантией движения цены."
    )
    await update.message.reply_text(
        text
    )
# ============================================================
# HELP
# ============================================================
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "🧠 MARKETLENS v0.9\n\n"
        "/start — запуск\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот графика."
    )
    await update.message.reply_text(
        text
    )
# ============================================================
# VISION PROMPT
# ============================================================
VISION_PROMPT = """
Ты — модуль технического анализа MarketLens.
Проанализируй изображение торгового графика.
Определи:
1. Текущее направление движения:
   UP / DOWN / SIDEWAYS
2. Структуру рынка:
   - тренд
   - импульс
   - коррекция
   - консолидация
3. Ключевые уровни:
   - ближайшее сопротивление
   - ближайшая поддержка
4. Поведение свечей:
   - импульсные свечи
   - поглощение
   - ложный пробой
   - отбой
   - сжатие волатильности
5. Если виден объём:
   оцени подтверждает ли он движение.
6. Сценарии:
   основной сценарий
   альтернативный сценарий
7. Укажи, что должно произойти для подтверждения движения.
Не выдумывай значения цены, которых невозможно прочитать
на изображении.
Ответ дай структурировано и коротко.
Формат:
📊 MARKETLENS ANALYSIS
Направление: UP / DOWN / SIDEWAYS
Сила сигнала: LOW / MEDIUM / HIGH
Тренд:
...
Поддержка:
...
Сопротивление:
...
Свечи:
...
Основной сценарий:
...
Альтернативный сценарий:
...
Подтверждение:
...
Риск:
...
"""
# ============================================================
# PHOTO HANDLER
# ============================================================
async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    if not message or not message.photo:
        return
    try:
        # ----------------------------------------------------
        # TELEGRAM FILE
        # ----------------------------------------------------
        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(
            photo.file_id
        )
        # ----------------------------------------------------
        # FILE NAME
        # ----------------------------------------------------
        now = datetime.now(
            timezone.utc
        )
        timestamp = now.strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        user_id = (
            message.from_user.id
            if message.from_user
            else "unknown"
        )
        filename = (
            f"chart_"
            f"{user_id}_"
            f"{timestamp}.jpg"
        )
        filepath = (
            SCREENSHOTS_DIR /
            filename
        )
        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------
        await telegram_file.download_to_drive(
            custom_path=str(filepath)
        )
        size_kb = (
            filepath.stat().st_size /
            1024
        )
        print(
            f"[SCREENSHOT] Saved: {filepath}"
        )
        print(
            f"[SCREENSHOT] Size: {size_kb:.1f} KB"
        )
        # ----------------------------------------------------
        # USER MESSAGE
        # ----------------------------------------------------
        status_message = await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 {filename}\n"
            f"📦 {size_kb:.1f} KB\n\n"
            "🧠 Отправляю график в Qwen Vision...\n"
            "⏳ Подожди немного."
        )
        # ----------------------------------------------------
        # VISION
        # ----------------------------------------------------
        try:
            result = await analyze_with_vision(
                str(filepath),
                VISION_PROMPT,
            )
        except Exception as vision_error:
            logger.exception(
                "[VISION ERROR]"
            )
            await status_message.edit_text(
                "❌ Vision Engine не смог обработать график.\n\n"
                f"Ошибка: {type(vision_error).__name__}\n\n"
                "Проверь Render Logs."
            )
            return
        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------
        response = (
            "🧠 MARKETLENS v0.9\n\n"
            "👁️ Qwen Vision:\n\n"
            f"{result}"
        )
        # Telegram message limit
        MAX_LENGTH = 4000
        if len(response) <= MAX_LENGTH:
            await status_message.edit_text(
                response
            )
        else:
            await status_message.edit_text(
                response[:MAX_LENGTH]
            )
            remaining = response[
                MAX_LENGTH:
            ]
            while remaining:
                chunk = remaining[
                    :MAX_LENGTH
                ]
                await message.reply_text(
                    chunk
                )
                remaining = remaining[
                    MAX_LENGTH:
                ]
        print(
            "[VISION] Result sent to Telegram"
        )
    except Exception as e:
        logger.exception(
            "[SCREENSHOT ERROR]"
        )
        try:
            await message.reply_text(
                "❌ Ошибка обработки изображения.\n\n"
                f"{type(e).__name__}: {e}"
            )
        except Exception:
            pass
# ============================================================
# TEXT HANDLER
# ============================================================
async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return
    text = (
        update.message.text or ""
    )
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь скриншот TradingView.\n\n"
        "MarketLens автоматически передаст его "
        "в Vision Engine."
    )
# ============================================================
# ERROR HANDLER
# ============================================================
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    error = context.error
    logger.error(
        "Telegram error: %s",
        error,
    )
    # Conflict is usually caused by
    # another bot instance using getUpdates.
    if (
        error and
        "Conflict" in str(error)
    ):
        logger.warning(
            "Telegram polling conflict: "
            "another bot instance may be running."
        )
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        "🧠 MarketLens Vision v0.9 starting..."
    )
    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------
    Thread(
        target=start_http_server,
        daemon=True,
    ).start()
    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------
    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )
    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )
    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )
    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.TEXT &
            ~filters.COMMAND,
            handle_text,
        )
    )
    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------
    application.add_error_handler(
        error_handler
    )
    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    print(
        "🧠 MarketLens Vision v0.9 started"
    )
    print(
        "📸 Screenshot Engine: READY"
    )
    print(
        "💾 Screenshot Storage: READY"
    )
    print(
        "👁️ Vision Engine: READY"
    )
    print(
        f"🤖 Qwen Space: {VISION_SPACE}"
    )
    print(
        f"🔌 Endpoint: {VISION_API_NAME}"
    )
    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------
    application.run_polling(
        drop_pending_updates=True
    )
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()