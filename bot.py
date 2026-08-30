import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
ContextTypes,
filters,
)

from gradio_client import Client, handle_file

=========================

CONFIG

=========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

VISION_SPACE = “developer0hye/Qwen2.5-VL-7B-Instruct”

PORT = int(os.environ.get(“PORT”, “10000”))

SCREENSHOT_DIR = “screenshots”
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

=========================

HTTP SERVER FOR RENDER

=========================

class HealthHandler(BaseHTTPRequestHandler):

def do_GET(self):
    self.send_response(200)
    self.send_header("Content-Type", "text/plain; charset=utf-8")
    self.end_headers()
    self.wfile.write(b"MarketLens is alive")
def log_message(self, format, *args):
    return

def start_http_server():
server = HTTPServer((“0.0.0.0”, PORT), HealthHandler)
print(f”HTTP server started on port {PORT}”, flush=True)
server.serve_forever()

=========================

VISION ENGINE

=========================

def analyze_chart(image_path: str) -> str:

print("[VISION] Connecting to Qwen Space...", flush=True)
client = Client(VISION_SPACE)
prompt = """

Analyze this TradingView trading chart.

Give a concise technical analysis.

Identify:

1. Market trend
2. Current market structure
3. Nearest support
4. Nearest resistance
5. Important candlestick behavior
6. Volume behavior if visible
7. Most likely direction: UP, DOWN, or RANGE
8. Confidence from 0 to 100%
9. What would invalidate the scenario

Do not invent information that is not visible on the chart.

Answer in Russian.
“””

print("[VISION] Sending chart...", flush=True)
result = client.predict(
    image_path=handle_file(image_path),
    text_input=prompt,
    api_name="/qwen_vl_inference"
)
print("[VISION] Response received", flush=True)
if result is None:
    raise RuntimeError("Qwen returned an empty response")
return str(result)

=========================

TELEGRAM

=========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

await update.message.reply_text(
    "🧠 MARKETLENS v0.6\n\n"
    "Я готов анализировать TradingView.\n\n"
    "📸 Отправь скриншот графика."
)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

message = update.message
if not message or not message.photo:
    return
try:
    await message.reply_text(
        "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
        "💾 Сохраняю изображение...\n"
        "🧠 Подготавливаю Vision-анализ..."
    )
    photo = message.photo[-1]
    file = await photo.get_file()
    user_id = update.effective_user.id if update.effective_user else 0
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )
    filename = f"chart_{user_id}_{timestamp}.jpg"
    image_path = os.path.join(
        SCREENSHOT_DIR,
        filename
    )
    await file.download_to_drive(image_path)
    size = os.path.getsize(image_path)
    print(
        f"[SCREENSHOT] Saved: {image_path} "
        f"({size / 1024:.1f} KB)",
        flush=True
    )
    await message.reply_text(
        "💾 Изображение сохранено.\n\n"
        "🧠 Vision Engine анализирует график..."
    )
    result = analyze_chart(image_path)
    await message.reply_text(
        "🧠 MARKETLENS ANALYSIS\n\n"
        + result
    )
except Exception as e:
    print(
        f"[ERROR] {type(e).__name__}: {e}",
        flush=True
    )
    await message.reply_text(
        "❌ Vision Engine не смог обработать график.\n\n"
        f"Ошибка: {type(e).__name__}\n\n"
        "Проверь Render Logs."
    )

=========================

MAIN

=========================

def main():

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is missing"
    )
threading.Thread(
    target=start_http_server,
    daemon=True
).start()
print(
    "🧠 MarketLens Vision v0.6 started",
    flush=True
)
application = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)
application.add_handler(
    CommandHandler("start", start)
)
application.add_handler(
    MessageHandler(
        filters.PHOTO,
        photo_handler
    )
)
print(
    "🤖 Telegram polling started",
    flush=True
)
application.run_polling(
    drop_pending_updates=True
)

if name == “main”:
main()