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
# MARKETLENS v0.7
# Telegram + Screenshot + Qwen Gradio Client
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# Hugging Face Space
VISION_SPACE = os.environ.get(
    "VISION_SPACE",
    "developer0hye/Qwen2.5-VL-7B-Instruct"
)
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
# SIMPLE HTTP SERVER FOR RENDER
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
            b"MarketLens v0.7 is running"
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
        ("0.0.0.0", port),
        HealthHandler
    )
    print(
        f"HTTP server started on port {port}"
    )
    server.serve_forever()
# ============================================================
# QWEN VISION
# ============================================================
def qwen_analyze_image(image_path: str) -> str:
    """
    Connects to the Hugging Face Gradio Space
    using the official gradio_client.
    The client automatically communicates with
    the current Space API instead of relying on
    the old /run/... endpoint.
    """
    print("[VISION] Connecting to Qwen Space...")
    print(f"[VISION] Space: {VISION_SPACE}")
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        raise RuntimeError(
            "gradio_client is not installed. "
            "Add gradio_client to requirements.txt"
        )
    try:
        client = Client(VISION_SPACE)
        print("[VISION] Connected to Space")
        # ----------------------------------------------------
        # Inspect API
        # ----------------------------------------------------
        try:
            api_info = client.view_api(
                all_endpoints=True
            )
            print(
                "[VISION] Available API endpoints:"
            )
            print(api_info)
        except Exception as api_error:
            print(
                "[VISION] Could not inspect API:"
            )
            print(
                f"{type(api_error).__name__}: "
                f"{api_error}"
            )
        # ----------------------------------------------------
        # Trading analysis prompt
        # ----------------------------------------------------
        prompt = """
Ты — профессиональный технический аналитик.
Проанализируй изображение графика TradingView.
Нужно определить:
1. Текущее направление движения цены:
   UP / DOWN / SIDEWAYS
2. Структуру рынка:
   - тренд
   - импульс
   - коррекция
   - пробой
   - ложный пробой
3. Ближайшие уровни:
   - Support
   - Resistance
4. Поведение последних свечей.
5. Если виден объём — оцени его относительно движения цены.
6. Дай наиболее вероятный сценарий следующего движения.
Ответ пиши кратко и структурированно:
📊 MARKETLENS ANALYSIS
Направление: ...
Уверенность: ...%
Тренд: ...
Support:
...
Resistance:
...
Свечи:
...
Объём:
...
Сценарий:
...
⚠️ ВАЖНО:
Не выдумывай уровни или данные, которых нет на изображении.
Если график недостаточно хорошо виден — прямо скажи, что нужен новый скриншот.
"""
        # ----------------------------------------------------
        # Try common Gradio endpoints
        # ----------------------------------------------------
        possible_endpoints = [
            "/generate_image",
            "/predict",
            "/chat",
            "/generate",
        ]
        last_error = None
        for endpoint in possible_endpoints:
            try:
                print(
                    f"[VISION] Trying endpoint: {endpoint}"
                )
                result = client.predict(
                    handle_file(image_path),
                    prompt,
                    api_name=endpoint
                )
                print(
                    f"[VISION] Endpoint {endpoint} returned"
                )
                # ------------------------------------------------
                # Normalize result
                # ------------------------------------------------
                if isinstance(
                    result,
                    (list, tuple)
                ):
                    parts = []
                    for item in result:
                        if item is None:
                            continue
                        if isinstance(
                            item,
                            str
                        ):
                            parts.append(
                                item
                            )
                    text = "\n".join(
                        parts
                    ).strip()
                else:
                    text = str(
                        result
                    ).strip()
                if text:
                    print(
                        "[VISION] Analysis received successfully"
                    )
                    return text
            except Exception as endpoint_error:
                last_error = endpoint_error
                print(
                    f"[VISION] Endpoint failed: "
                    f"{endpoint}"
                )
                print(
                    f"[VISION] "
                    f"{type(endpoint_error).__name__}: "
                    f"{endpoint_error}"
                )
        # --------------------------------------------------------
        # Nothing worked
        # --------------------------------------------------------
        raise RuntimeError(
            "Qwen Space API did not accept any known endpoint. "
            f"Last error: {last_error}"
        )
    except Exception as e:
        logger.exception(
            "[VISION ERROR]"
        )
        raise RuntimeError(
            f"{type(e).__name__}: {e}"
        )
# ============================================================
# ASYNC WRAPPER
# ============================================================
async def analyze_image_async(
    image_path: str
) -> str:
    return await asyncio.to_thread(
        qwen_analyze_image,
        image_path
    )
# ============================================================
# TELEGRAM COMMANDS
# ============================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = (
        "🧠 MARKETLENS v0.7\n\n"
        "Vision Engine подключён.\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я сохраню изображение и передам его "
        "в Qwen Vision для технического анализа."
    )
    await update.message.reply_text(
        text
    )
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = (
        "🧠 MARKETLENS v0.7\n\n"
        "/start — запуск\n"
        "/help — помощь\n\n"
        "📸 Отправь скриншот TradingView "
        "для анализа."
    )
    await update.message.reply_text(
        text
    )
# ============================================================
# SCREENSHOT HANDLER
# ============================================================
async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.message
    if not message or not message.photo:
        return
    try:
        # ----------------------------------------------------
        # Get highest quality Telegram photo
        # ----------------------------------------------------
        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(
            photo.file_id
        )
        # ----------------------------------------------------
        # Filename
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
        # Download
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
            f"[SCREENSHOT] Size: "
            f"{size_kb:.1f} KB"
        )
        # ----------------------------------------------------
        # Initial response
        # ----------------------------------------------------
        status_message = await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 Файл: {filename}\n"
            f"📦 Размер: {size_kb:.1f} KB\n\n"
            "🧠 Запускаю Vision Engine...\n"
            "⏳ Анализирую график."
        )
        # ----------------------------------------------------
        # Vision
        # ----------------------------------------------------
        try:
            analysis = await analyze_image_async(
                str(filepath)
            )
            await status_message.edit_text(
                "🧠 MARKETLENS v0.7\n\n"
                "📊 Анализ графика:\n\n"
                f"{analysis}"
            )
        except Exception as vision_error:
            logger.exception(
                "[VISION ANALYSIS ERROR]"
            )
            await status_message.edit_text(
                "❌ Vision Engine не смог "
                "обработать график.\n\n"
                f"Ошибка: "
                f"{type(vision_error).__name__}\n\n"
                "Проверь Render Logs."
            )
    except Exception as e:
        logger.exception(
            "[SCREENSHOT ERROR]"
        )
        try:
            await message.reply_text(
                "❌ Не удалось обработать "
                "скриншот.\n\n"
                f"Ошибка: {type(e).__name__}"
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
        update.message.text or ""
    )
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь именно скриншот "
        "графика TradingView.\n\n"
        "После этого MarketLens передаст "
        "изображение в Vision Engine."
    )
# ============================================================
# ERROR HANDLER
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
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        "🧠 MarketLens Vision v0.7 starting..."
    )
    # --------------------------------------------------------
    # Render HTTP server
    # --------------------------------------------------------
    Thread(
        target=start_http_server,
        daemon=True
    ).start()
    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
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
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT &
            ~filters.COMMAND,
            handle_text
        )
    )
    application.add_error_handler(
        error_handler
    )
    print(
        "🧠 MarketLens Vision v0.7 started"
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
    # --------------------------------------------------------
    # Polling
    # --------------------------------------------------------
    application.run_polling(
        drop_pending_updates=True
    )
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()