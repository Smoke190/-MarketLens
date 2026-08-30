import os
import asyncio
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
# MARKETLENS v1.0
# Telegram + Qwen2.5-VL Gradio Space
# ============================================================
VERSION = "1.0"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ============================================================
# QWEN SPACE
# ============================================================
QWEN_SPACE = "developer0hye/Qwen2.5-VL-7B-Instruct"
QWEN_API = "/qwen_vl_inference"
VISION_TIMEOUT = 180
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
            f"MarketLens v{VERSION} is running".encode()
        )
    def log_message(self, format, *args):
        return
def start_http_server():
    port = int(
        os.environ.get("PORT", "10000")
    )
    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )
    print(
        f"HTTP server started on port {port}"
    )
    server.serve_forever()
# ============================================================
# VISION PROMPT
# ============================================================
VISION_PROMPT = """
Ты — технический аналитик MarketLens.
Проанализируй предоставленный скриншот графика TradingView.
Используй ТОЛЬКО информацию, которая реально видна на изображении.
Определи:
1. Текущий тренд:
   - восходящий
   - нисходящий
   - боковой
2. Структуру цены:
   - HH / HL
   - LH / LL
   - импульс
   - коррекция
   - консолидация
3. Уровни:
   - ближайшая поддержка
   - ближайшее сопротивление
   - сильные уровни, если они хорошо видны
4. Свечи:
   - сильный импульс
   - поглощение
   - ложный пробой
   - длинные тени
   - разворотные признаки
5. Объём, если он отображён на графике.
6. Что сейчас вероятнее:
   - продолжение движения
   - откат
   - пробой
   - разворот
   - боковое движение
В конце дай короткий вывод:
НАПРАВЛЕНИЕ: UP / DOWN / RANGE
УВЕРЕННОСТЬ: 0-100%
СЦЕНАРИЙ:
кратко опиши наиболее вероятный сценарий.
ТОЧКА ИНТЕРЕСА:
укажи область цены или условие входа, только если это действительно можно определить по изображению.
ОТМЕНА СЦЕНАРИЯ:
укажи, при каком движении текущий сценарий становится недействительным.
Не выдумывай цены, уровни или индикаторы, которых не видно.
Не утверждай, что движение гарантировано.
"""
# ============================================================
# QWEN CLIENT
# ============================================================
_qwen_client = None
def get_qwen_client():
    global _qwen_client
    if _qwen_client is None:
        logger.info(
            "[VISION] Connecting to Qwen Space: %s",
            QWEN_SPACE,
        )
        _qwen_client = Client(
            QWEN_SPACE
        )
        logger.info(
            "[VISION] Qwen Space connected"
        )
    return _qwen_client
# ============================================================
# QWEN ANALYSIS
# ============================================================
def qwen_analyze_image(image_path: Path):
    logger.info(
        "[VISION] Preparing image..."
    )
    if not image_path.exists():
        raise RuntimeError(
            f"Image not found: {image_path}"
        )
    client = get_qwen_client()
    logger.info(
        "[VISION] Sending image to Qwen..."
    )
    try:
        result = client.predict(
            image_path=handle_file(
                str(image_path)
            ),
            text_input=VISION_PROMPT,
            api_name=QWEN_API,
        )
    except Exception as exc:
        logger.exception(
            "[VISION] Qwen request failed"
        )
        raise RuntimeError(
            f"Qwen request failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    logger.info(
        "[VISION] Qwen response received"
    )
    logger.info(
        "[VISION] Result type: %s",
        type(result).__name__,
    )
    if result is None:
        raise RuntimeError(
            "Qwen returned empty result"
        )
    if isinstance(result, (list, tuple)):
        if len(result) == 0:
            raise RuntimeError(
                "Qwen returned an empty list"
            )
        result = result[0]
    result_text = str(result).strip()
    if not result_text:
        raise RuntimeError(
            "Qwen returned empty text"
        )
    return result_text
# ============================================================
# ASYNC VISION WRAPPER
# ============================================================
async def analyze_with_vision(
    image_path: Path
):
    return await asyncio.wait_for(
        asyncio.to_thread(
            qwen_analyze_image,
            image_path,
        ),
        timeout=VISION_TIMEOUT,
    )
# ============================================================
# /START
# ============================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        f"🧠 MARKETLENS v{VERSION}\n\n"
        "Vision Engine: READY 👁️\n"
        "Qwen2.5-VL: CONNECTED\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я определю:\n"
        "• тренд\n"
        "• структуру цены\n"
        "• поддержку/сопротивление\n"
        "• свечные сигналы\n"
        "• вероятное направление\n"
        "• сценарий движения"
    )
    await update.message.reply_text(
        text
    )
# ============================================================
# /HELP
# ============================================================
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        f"🧠 MARKETLENS v{VERSION}\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот графика."
    )
    await update.message.reply_text(
        text
    )
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
            filepath.stat().st_size / 1024
        )
        logger.info(
            "[SCREENSHOT] Saved: %s",
            filepath,
        )
        logger.info(
            "[SCREENSHOT] Size: %.1f KB",
            size_kb,
        )
        # ----------------------------------------------------
        # PROCESSING MESSAGE
        # ----------------------------------------------------
        processing_message = (
            await message.reply_text(
                "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
                f"💾 {filename}\n"
                f"📦 {size_kb:.1f} KB\n\n"
                "🧠 MarketLens Vision\n"
                "⏳ Анализирую график..."
            )
        )
        # ----------------------------------------------------
        # VISION
        # ----------------------------------------------------
        logger.info(
            "[VISION] Starting analysis..."
        )
        result = await analyze_with_vision(
            filepath
        )
        logger.info(
            "[VISION] Analysis completed"
        )
        # ----------------------------------------------------
        # TELEGRAM RESULT
        # ----------------------------------------------------
        response = (
            "🧠 MARKETLENS ANALYSIS\n\n"
            f"{result}\n\n"
            "⚠️ Анализ основан только на "
            "видимом содержимом скриншота."
        )
        # Telegram limit protection
        if len(response) > 4000:
            response = (
                response[:3900]
                + "\n\n…"
            )
        await processing_message.edit_text(
            response
        )
    except asyncio.TimeoutError:
        logger.exception(
            "[VISION ERROR] Timeout"
        )
        await message.reply_text(
            "⏱️ Vision Engine не успел "
            "обработать график.\n\n"
            "Попробуй отправить скриншот ещё раз."
        )
    except Exception as exc:
        logger.exception(
            "[VISION ERROR]"
        )
        error_text = str(exc)
        if len(error_text) > 1000:
            error_text = (
                error_text[:1000]
                + "..."
            )
        await message.reply_text(
            "❌ Vision Engine не смог "
            "обработать график.\n\n"
            f"Ошибка: {type(exc).__name__}\n\n"
            f"{error_text}"
        )
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
        "📸 Отправь скриншот графика TradingView.\n\n"
        "Я передам его в Vision Engine "
        "для технического анализа."
    )
# ============================================================
# TELEGRAM ERROR HANDLER
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
    # 409 Conflict обычно означает
    # второй одновременно работающий polling.
    if error and "Conflict" in str(error):
        logger.warning(
            "Telegram polling conflict detected. "
            "Another bot instance may be running."
        )
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        f"🧠 MarketLens Vision v{VERSION} starting..."
    )
    # --------------------------------------------------------
    # RENDER HEALTH SERVER
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
    # PHOTOS
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
    # START
    # --------------------------------------------------------
    print(
        f"🧠 MarketLens Vision v{VERSION} started"
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
        f"🤖 Qwen Space: {QWEN_SPACE}"
    )
    print(
        f"🔌 API endpoint: {QWEN_API}"
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