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
# MARKETLENS v0.9.1
# Telegram Bot + Screenshot Storage + Qwen Vision
# ============================================================
VERSION = "0.9.1"
# ============================================================
# ENVIRONMENT
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ============================================================
# QWEN SPACE
# ============================================================
QWEN_SPACE = "developer0hye/Qwen2.5-VL-7B-Instruct"
QWEN_API_NAME = "/qwen_vl_inference"
# ============================================================
# DIRECTORIES
# ============================================================
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(
    parents=True,
    exist_ok=True
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
# GRADIO CLIENT
# ============================================================
try:
    from gradio_client import Client, handle_file
    GRADIO_AVAILABLE = True
except Exception as e:
    GRADIO_AVAILABLE = False
    Client = None
    handle_file = None
    logger.error(
        "gradio_client import failed: %s",
        e
    )
# ============================================================
# RENDER HEALTH SERVER
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()
        self.wfile.write(
            f"MarketLens v{VERSION} OK".encode(
                "utf-8"
            )
        )
    def log_message(self, format, *args):
        return
def start_http_server():
    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )
    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        HealthHandler
    )
    print(
        f"HTTP server started on port {port}"
    )
    server.serve_forever()
# ============================================================
# VISION PROMPT
# ============================================================
VISION_PROMPT = """
Ты — MarketLens Vision Engine.
Твоя задача — профессионально анализировать изображение
торгового графика.
Не выдумывай данные, которых нет на изображении.
Проанализируй:
1. TREND
UP / DOWN / SIDEWAYS
2. MARKET STRUCTURE
HH / HL / LH / LL / RANGE / BREAKOUT / PULLBACK
3. SUPPORT
Ближайшая видимая зона поддержки.
4. RESISTANCE
Ближайшая видимая зона сопротивления.
5. CANDLE ACTION
Что происходит с последними свечами.
6. VOLUME
Если объём присутствует на графике —
оценивает ли он движение цены.
7. SCENARIO
Выбери наиболее вероятный:
CONTINUATION
PULLBACK
BREAKOUT
FALSE BREAKOUT
RANGE
8. SIGNAL
BUY
SELL
WAIT
9. CONFIDENCE
0-100%
10. ENTRY
Если возможно, укажи логичную область входа.
11. INVALIDATION
Что должно произойти, чтобы сценарий считался отменённым.
ВАЖНО:
Если изображение недостаточно хорошо видно,
если не видно цены, свечей или структуры рынка,
напиши:
NEED_NEW_SCREENSHOT
Ответ:
📊 MARKETLENS ANALYSIS
TREND:
...
STRUCTURE:
...
SUPPORT:
...
RESISTANCE:
...
CANDLE ACTION:
...
VOLUME:
...
SCENARIO:
...
SIGNAL:
...
CONFIDENCE:
...
ENTRY:
...
INVALIDATION:
...
Не используй лишнюю воду.
"""
# ============================================================
# CLEAN RESULT
# ============================================================
def clean_result(result):
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
                parts.append(
                    item
                )
            else:
                parts.append(
                    str(item)
                )
        return "\n".join(
            parts
        ).strip()
    if isinstance(result, dict):
        for key in (
            "text",
            "output",
            "result",
            "value"
        ):
            if key in result:
                value = result[key]
                if value is None:
                    continue
                return str(value).strip()
        return str(result).strip()
    return str(result).strip()
# ============================================================
# QWEN ANALYSIS
# ============================================================
def qwen_analyze_image(
    image_path: str
) -> str:
    print(
        "[VISION] Connecting to Qwen Space..."
    )
    print(
        f"[VISION] Space: {QWEN_SPACE}"
    )
    print(
        f"[VISION] Endpoint: {QWEN_API_NAME}"
    )
    if not GRADIO_AVAILABLE:
        raise RuntimeError(
            "gradio-client is not installed. "
            "Check requirements.txt"
        )
    if not Path(image_path).exists():
        raise RuntimeError(
            f"Image not found: {image_path}"
        )
    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------
    try:
        client = Client(
            QWEN_SPACE
        )
        print(
            "[VISION] Qwen Space connected."
        )
    except Exception as e:
        logger.exception(
            "[VISION] Connection failed"
        )
        raise RuntimeError(
            f"Qwen Space connection failed: {e}"
        )
    # --------------------------------------------------------
    # PREPARE FILE
    # --------------------------------------------------------
    try:
        print(
            "[VISION] Preparing image..."
        )
        image_input = handle_file(
            image_path
        )
    except Exception as e:
        logger.exception(
            "[VISION] Image preparation failed"
        )
        raise RuntimeError(
            f"Image preparation failed: {e}"
        )
    # --------------------------------------------------------
    # CALL QWEN
    # --------------------------------------------------------
    try:
        print(
            "[VISION] Sending image to Qwen..."
        )
        result = client.predict(
            image_path=image_input,
            text_input=VISION_PROMPT,
            api_name=QWEN_API_NAME
        )
    except Exception as e:
        logger.exception(
            "[VISION] Qwen inference failed"
        )
        raise RuntimeError(
            f"Qwen inference failed: {e}"
        )
    # --------------------------------------------------------
    # PROCESS RESPONSE
    # --------------------------------------------------------
    print(
        "[VISION] Qwen response received."
    )
    text = clean_result(
        result
    )
    if not text:
        raise RuntimeError(
            "Qwen returned an empty response."
        )
    print(
        "[VISION] Analysis text received."
    )
    return text
# ============================================================
# ASYNC VISION WRAPPER
# ============================================================
async def analyze_with_vision(
    filepath: Path
) -> str:
    return await asyncio.to_thread(
        qwen_analyze_image,
        str(filepath)
    )
# ============================================================
# /START
# ============================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    await update.message.reply_text(
        f"""
🧠 MARKETLENS v{VERSION}
👁️ Vision Engine: READY
🤖 Qwen Vision: READY
📸 Отправь скриншот TradingView.
Я:
1️⃣ сохраню график
2️⃣ передам изображение Qwen Vision
3️⃣ определю тренд
4️⃣ найду структуру рынка
5️⃣ определю Support / Resistance
6️⃣ оценю свечи и объём
7️⃣ дам BUY / SELL / WAIT
8️⃣ укажу Confidence
Если график плохо виден —
я попрошу новый скриншот.
"""
    )
# ============================================================
# /HELP
# ============================================================
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    await update.message.reply_text(
        f"""
🧠 MARKETLENS v{VERSION}
Команды:
/start — запуск
/help — помощь
📸 Для анализа просто отправь
скриншот торгового графика.
"""
    )
# ============================================================
# PHOTO HANDLER
# ============================================================
async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.message
    if not message:
        return
    if not message.photo:
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
        # STATUS MESSAGE
        # ----------------------------------------------------
        status = await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 {filename}\n"
            f"📦 {size_kb:.1f} KB\n\n"
            "🧠 MarketLens Vision v0.9.1\n"
            "👁️ Отправляю график в Qwen Vision...\n\n"
            "⏳ Анализ..."
        )
        # ----------------------------------------------------
        # VISION
        # ----------------------------------------------------
        try:
            print(
                "[VISION] Starting analysis..."
            )
            result = await analyze_with_vision(
                filepath
            )
        except Exception as e:
            logger.exception(
                "[VISION ERROR]"
            )
            await status.edit_text(
                "❌ Vision Engine не смог обработать график.\n\n"
                f"Ошибка: {type(e).__name__}\n\n"
                f"{str(e)[:1500]}\n\n"
                "Проверь Render Logs."
            )
            return
        # ----------------------------------------------------
        # NEW SCREENSHOT REQUEST
        # ----------------------------------------------------
        upper_result = result.upper()
        if (
            "NEED_NEW_SCREENSHOT"
            in upper_result
        ):
            await status.edit_text(
                "📸 НУЖЕН НОВЫЙ СКРИНШОТ\n\n"
                "Qwen Vision не смог получить "
                "достаточно информации с графика.\n\n"
                "Отправь более чёткий скриншот TradingView."
            )
            return
        # ----------------------------------------------------
        # FINAL MESSAGE
        # ----------------------------------------------------
        final_text = (
            "🧠 MARKETLENS v0.9.1\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Сигнал является вероятностным "
            "анализом и не гарантирует движение цены."
        )
        # Telegram limit
        if len(final_text) > 3900:
            final_text = (
                final_text[:3850]
                + "\n\n…"
            )
        await status.edit_text(
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
                "❌ Ошибка обработки изображения.\n\n"
                f"{type(e).__name__}: "
                f"{str(e)[:1000]}"
            )
        except Exception:
            pass
# ============================================================
# TEXT HANDLER
# ============================================================
async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    text = (
        update.message.text
        or ""
    )
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь скриншот графика TradingView."
    )
# ============================================================
# TELEGRAM ERROR HANDLER
# ============================================================
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    error = context.error
    logger.error(
        "Telegram error: %s",
        error
    )
    if (
        error
        and
        "Conflict" in str(error)
    ):
        logger.warning(
            "Telegram polling conflict: "
            "another instance of this bot "
            "is using the same token."
        )
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        f"🧠 MarketLens Vision v{VERSION} starting..."
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
            "👁️ Vision Engine: OFFLINE"
        )
    print(
        f"🤖 Qwen Space: {QWEN_SPACE}"
    )
    print(
        f"🔌 Qwen Endpoint: {QWEN_API_NAME}"
    )
    # --------------------------------------------------------
    # RENDER SERVER
    # --------------------------------------------------------
    Thread(
        target=start_http_server,
        daemon=True
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
            start
        )
    )
    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )
    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )
    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text
        )
    )
    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------
    application.add_error_handler(
        error_handler
    )
    print(
        f"🧠 MarketLens Vision v{VERSION} started"
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