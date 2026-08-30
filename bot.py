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
# MARKETLENS v0.6
# Stable Telegram bot + screenshot storage
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Render Environment Variables")
# Folder for screenshots
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
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
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"MarketLens v0.6 is running")
    def log_message(self, format, *args):
        return
def start_http_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )
    print(f"HTTP server started on port {port}")
    server.serve_forever()
# ============================================================
# TELEGRAM COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧠 MARKETLENS v0.6\n\n"
        "Я готов принимать графики.\n\n"
        "📸 Отправь мне скриншот TradingView.\n\n"
        "💾 Я сохраню изображение.\n"
        "🧠 Следующий этап — подключение Vision Engine."
    )
    await update.message.reply_text(text)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧠 MARKETLENS v0.6\n\n"
        "Доступные команды:\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот TradingView."
    )
    await update.message.reply_text(text)
# ============================================================
# SCREENSHOT HANDLER
# ============================================================
async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        message = update.message
        if not message or not message.photo:
            return
        # Get highest quality Telegram photo
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        filename = (
            f"chart_"
            f"{message.from_user.id}_"
            f"{timestamp}.jpg"
        )
        filepath = SCREENSHOTS_DIR / filename
        await file.download_to_drive(
            custom_path=str(filepath)
        )
        size_kb = filepath.stat().st_size / 1024
        print(
            f"[SCREENSHOT] Saved: {filepath}"
        )
        print(
            f"[SCREENSHOT] Size: {size_kb:.1f} KB"
        )
        # ----------------------------------------------------
        # USER RESPONSE
        # ----------------------------------------------------
        await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 Файл: {filename}\n"
            f"📦 Размер: {size_kb:.1f} KB\n\n"
            "✅ Изображение сохранено.\n\n"
            "🧠 MarketLens Vision v0.6\n"
            "График подготовлен для анализа."
        )
    except Exception as e:
        logger.exception(
            "[SCREENSHOT ERROR]"
        )
        await update.message.reply_text(
            "❌ Не удалось сохранить скриншот.\n\n"
            f"Ошибка: {type(e).__name__}"
        )
# ============================================================
# TEXT HANDLER
# ============================================================
async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    text = update.message.text or ""
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь мне именно скриншот графика TradingView.\n\n"
        "После получения изображения я сохраню его "
        "и подготовлю к техническому анализу."
    )
# ============================================================
# ERROR HANDLER
# ============================================================
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    logger.error(
        "Telegram error: %s",
        context.error,
    )
# ============================================================
# MAIN
# ============================================================
def main():
    print("🧠 MarketLens Vision v0.6 starting...")
    # Start Render health server
    Thread(
        target=start_http_server,
        daemon=True,
    ).start()
    # Create Telegram application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    # Commands
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
    # Photos
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )
    # Text
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )
    application.add_error_handler(
        error_handler
    )
    print("🧠 MarketLens Vision v0.6 started")
    print("📸 Screenshot engine: READY")
    print("💾 Screenshot storage: READY")
    print("👁️ Vision Engine: STANDBY")
    # Start polling
    application.run_polling(
        drop_pending_updates=True
    )
if __name__ == "__main__":
    main()