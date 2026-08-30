import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from gradio_client import Client, handle_file

BOT_TOKEN = os.environ.get(“BOT_TOKEN”)
VISION_SPACE = “developer0hye/Qwen2.5-VL-7B-Instruct”

PORT = int(os.environ.get(“PORT”, “10000”))

SCREENSHOT_DIR = “screenshots”
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

class HealthHandler(BaseHTTPRequestHandler):

def do_GET(self):
    self.send_response(200)
    self.send_header("Content-Type", "text/plain")
    self.end_headers()
    self.wfile.write(b"MarketLens is alive")
def log_message(self, format, *args):
    pass

def start_http_server():
server = HTTPServer((“0.0.0.0”, PORT), HealthHandler)
print(“HTTP server started on port “ + str(PORT), flush=True)
server.serve_forever()

def analyze_chart(image_path):

print("[VISION] Connecting to Qwen...", flush=True)
client = Client(VISION_SPACE)
prompt = """

Ты технический аналитик.

Проанализируй изображение графика TradingView.

Определи:

1. Таймфрейм, если он виден.
2. Основной тренд.
3. Рыночную структуру.
4. Ближайшую поддержку.
5. Ближайшее сопротивление.
6. Поведение последних свечей.
7. Объём, если он виден.
8. Возможное направление движения: UP, DOWN или RANGE.
9. Уверенность от 0 до 100%.
10. Уровень, пробой которого отменит сценарий.

Не придумывай данные, которых нет на изображении.

Ответ дай на русском языке.
Будь кратким и конкретным.
“””

print("[VISION] Sending image...", flush=True)
result = client.predict(
    image_path=handle_file(image_path),
    text_input=prompt,
    api_name="/qwen_vl_inference"
)
print("[VISION] Result received", flush=True)
if result is None:
    raise RuntimeError("Qwen returned empty result")
return str(result)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

await update.message.reply_text(
    "🧠 MARKETLENS v0.6\n\n"
    "Готов анализировать TradingView.\n\n"
    "📸 Отправь скриншот графика."
)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

try:
    message = update.message
    if message is None or not message.photo:
        return
    await message.reply_text(
        "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
        "💾 Сохраняю изображение..."
    )
    photo = message.photo[-1]
    telegram_file = await photo.get_file()
    user_id = 0
    if update.effective_user:
        user_id = update.effective_user.id
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )
    filename = (
        "chart_"
        + str(user_id)
        + "_"
        + timestamp
        + ".jpg"
    )
    image_path = os.path.join(
        SCREENSHOT_DIR,
        filename
    )
    await telegram_file.download_to_drive(image_path)
    size = os.path.getsize(image_path)
    print(
        "[SCREENSHOT] Saved: "
        + image_path
        + " ("
        + str(round(size / 1024, 1))
        + " KB)",
        flush=True
    )
    await message.reply_text(
        "💾 Изображение сохранено.\n\n"
        "🧠 Qwen Vision анализирует график..."
    )
    result = analyze_chart(image_path)
    await message.reply_text(
        "🧠 MARKETLENS ANALYSIS\n\n"
        + result
    )
except Exception as error:
    print(
        "[VISION ERROR] "
        + type(error).__name__
        + ": "
        + str(error),
        flush=True
    )
    await update.message.reply_text(
        "❌ Vision Engine не смог обработать график.\n\n"
        "Ошибка: "
        + type(error).__name__
        + "\n\n"
        + str(error)
    )

def main():

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not configured in Render Environment Variables"
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