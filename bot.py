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
# ============================================================
# MARKETLENS v0.9
# Telegram + Screenshot Storage + Qwen Vision
#
# Qwen connection:
#   Hugging Face Space:
#   developer0hye/Qwen2.5-VL-7B-Instruct
#
# Endpoint:
#   /qwen_vl_inference
#
# Inputs:
#   image_path
#   text_input
# ============================================================
VERSION = "0.9"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ============================================================
# QWEN CONFIGURATION
# ============================================================
QWEN_SPACE = os.environ.get(
    "QWEN_SPACE",
    "developer0hye/Qwen2.5-VL-7B-Instruct",
)
QWEN_API_NAME = os.environ.get(
    "QWEN_API_NAME",
    "/qwen_vl_inference",
)
# ============================================================
# DIRECTORIES
# ============================================================
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MarketLens")
# ============================================================
# OPTIONAL GRADIO CLIENT
# ============================================================
try:
    from gradio_client import Client, handle_file
    GRADIO_AVAILABLE = True
except Exception as e:
    Client = None
    handle_file = None
    GRADIO_AVAILABLE = False
    logger.warning(
        "gradio_client is not available: %s",
        e,
    )
# ============================================================
# SIMPLE HTTP SERVER FOR RENDER
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.end_headers()
        self.wfile.write(
            f"MarketLens v{VERSION} is running".encode(
                "utf-8"
            )
        )
    def log_message(self, format, *args):
        return
def start_http_server():
    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )
    server = HTTPServer(
        (
            "0.0.0.0",
            port,
        ),
        HealthHandler,
    )
    print(
        f"HTTP server started on port {port}"
    )
    server.serve_forever()
# ============================================================
# QWEN VISION
# ============================================================
VISION_PROMPT = """
Ты — MarketLens Vision Engine, технический аналитик графиков.
Проанализируй изображение торгового графика.
Определи:
1. Направление тренда:
   - UP
   - DOWN
   - SIDEWAYS
2. Структуру рынка:
   - HH
   - HL
   - LH
   - LL
   - range
   - breakout
   - pullback
3. Ближайшие уровни:
   - Support
   - Resistance
4. Поведение свечей.
5. Если на графике виден объём — оцени его относительно движения цены.
6. Определи наиболее вероятный сценарий:
   - продолжение движения
   - откат
   - пробой
   - ложный пробой
   - боковик
7. Дай итоговый сигнал:
DIRECTION: UP / DOWN / NEUTRAL
CONFIDENCE: 0-100%
ENTRY: BUY / SELL / WAIT
IMPORTANT:
Не выдумывай уровни, которых невозможно увидеть на графике.
Если изображения недостаточно для анализа — напиши NEED_NEW_SCREENSHOT.
Ответ должен быть коротким, структурированным и без лишней воды.
"""
def clean_qwen_result(result):
    """
    Приводит различные варианты ответа Gradio
    к обычной строке.
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, (list, tuple)):
        parts = []
        for item in result:
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item)
            else:
                parts.append(
                    str(item)
                )
        return "\n".join(parts).strip()
    if isinstance(result, dict):
        # Возможные ключи ответа
        for key in (
            "text",
            "output",
            "result",
            "value",
        ):
            value = result.get(key)
            if value is not None:
                if isinstance(
                    value,
                    str,
                ):
                    return value.strip()
                return str(value).strip()
        return str(result).strip()
    return str(result).strip()
def qwen_analyze_image(
    image_path: str,
) -> str:
    if not GRADIO_AVAILABLE:
        raise RuntimeError(
            "gradio_client is not installed. "
            "Add gradio-client to requirements.txt"
        )
    if not Path(image_path).exists():
        raise RuntimeError(
            f"Image does not exist: {image_path}"
        )
    print(
        "[VISION] Connecting to Qwen Space..."
    )
    print(
        f"[VISION] Space: {QWEN_SPACE}"
    )
    print(
        f"[VISION] API: {QWEN_API_NAME}"
    )
    try:
        client = Client(
            QWEN_SPACE
        )
        print(
            "[VISION] Qwen Space connected."
        )
    except Exception as e:
        logger.exception(
            "[VISION] Failed to connect to Qwen Space"
        )
        raise RuntimeError(
            f"Could not connect to Qwen Space: {e}"
        )
    try:
        print(
            "[VISION] Preparing image..."
        )
        image_input = handle_file(
            image_path
        )
        print(
            "[VISION] Sending image to Qwen..."
        )
        result = client.predict(
            image_input,
            VISION_PROMPT,
            api_name=QWEN_API_NAME,
        )
        print(
            "[VISION] Qwen response received."
        )
        text = clean_qwen_result(
            result
        )
        if not text:
            raise RuntimeError(
                "Qwen returned an empty response."
            )
        return text
    except Exception as e:
        logger.exception(
            "[VISION] Qwen inference failed"
        )
        raise RuntimeError(
            f"Qwen inference error: {e}"
        )
async def analyze_with_vision(
    filepath: Path,
) -> str:
    return await asyncio.to_thread(
        qwen_analyze_image,
        str(filepath),
    )
# ============================================================
# TELEGRAM COMMANDS
# ============================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return
    text = (
        f"🧠 MARKETLENS v{VERSION}\n\n"
        "Vision Engine готов.\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я:\n"
        "1️⃣ сохраню график\n"
        "2️⃣ отправлю его в Qwen Vision\n"
        "3️⃣ получу технический анализ\n"
        "4️⃣ покажу направление движения\n"
        "5️⃣ дам BUY / SELL / WAIT\n\n"
        "⚠️ Если график плохо виден, попрошу новый скриншот."
    )
    await update.message.reply_text(
        text
    )
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return
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
# SCREENSHOT HANDLER
# ============================================================
async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    if not message:
        return
    if not message.photo:
        return
    filepath = None
    try:
        # ----------------------------------------------------
        # GET HIGHEST QUALITY TELEGRAM PHOTO
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
        # INITIAL RESPONSE
        # ----------------------------------------------------
        status_message = await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 Файл: {filename}\n"
            f"📦 Размер: {size_kb:.1f} KB\n\n"
            "🧠 MarketLens Vision v0.9\n"
            "👁️ Qwen Vision анализирует график...\n\n"
            "⏳ Подожди несколько секунд."
        )
        # ----------------------------------------------------
        # VISION
        # ----------------------------------------------------
        print(
            "[VISION] Starting analysis..."
        )
        try:
            result = await analyze_with_vision(
                filepath
            )
        except Exception as vision_error:
            logger.exception(
                "[VISION ERROR]"
            )
            await status_message.edit_text(
                "❌ Vision Engine не смог обработать график.\n\n"
                f"Ошибка: {type(vision_error).__name__}\n\n"
                f"{str(vision_error)[:1200]}\n\n"
                "Проверь Render Logs."
            )
            return
        # ----------------------------------------------------
        # CHECK FOR NEW SCREENSHOT
        # ----------------------------------------------------
        normalized = result.upper()
        if (
            "NEED_NEW_SCREENSHOT"
            in normalized
            or
            "НЕДОСТАТОЧНО"
            in normalized
        ):
            await status_message.edit_text(
                "📸 НУЖЕН НОВЫЙ СКРИНШОТ\n\n"
                "Qwen Vision не видит достаточно данных "
                "для надёжного анализа.\n\n"
                "Отправь более чёткий график TradingView."
            )
            return
        # ----------------------------------------------------
        # SEND ANALYSIS
        # ----------------------------------------------------
        final_text = (
            "🧠 MARKETLENS v0.9\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "👁️ QWEN VISION ANALYSIS\n\n"
            f"{result}\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Анализ является вероятностным, "
            "а не гарантией движения цены."
        )
        # Telegram message limit protection
        if len(final_text) > 3900:
            final_text = (
                final_text[:3850]
                + "\n\n…"
            )
        await status_message.edit_text(
            final_text
        )
        print(
            "[VISION] Analysis successfully sent."
        )
    except Exception as e:
        logger.exception(
            "[SCREENSHOT ERROR]"
        )
        try:
            await message.reply_text(
                "❌ Произошла ошибка.\n\n"
                f"Ошибка: {type(e).__name__}\n"
                f"{str(e)[:1000]}"
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
    text = update.message.text or ""
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь мне скриншот графика TradingView.\n\n"
        "Я отправлю его в Vision Engine "
        "для технического анализа."
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
    # Conflict is usually caused by another polling
    # process using the same Telegram bot token.
    if (
        error
        and
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
        f"🧠 MarketLens Vision v{VERSION} starting..."
    )
    print(
        f"🤖 Qwen Space: {QWEN_SPACE}"
    )
    print(
        f"🔌 Qwen API: {QWEN_API_NAME}"
    )
    # --------------------------------------------------------
    # START RENDER HEALTH SERVER
    # --------------------------------------------------------
    Thread(
        target=start_http_server,
        daemon=True,
    ).start()
    # --------------------------------------------------------
    # TELEGRAM APPLICATION
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
    # PHOTO HANDLER
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )
    # --------------------------------------------------------
    # TEXT HANDLER
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )
    # --------------------------------------------------------
    # ERROR HANDLER
    # --------------------------------------------------------
    application.add_error_handler(
        error_handler
    )
    # --------------------------------------------------------
    # STATUS
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
    if GRADIO_AVAILABLE:
        print(
            "👁️ Vision Engine: READY"
        )
    else:
        print(
            "👁️ Vision Engine: OFFLINE "
            "(gradio-client missing)"
        )
    print(
        f"🤖 Qwen Space: {QWEN_SPACE}"
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