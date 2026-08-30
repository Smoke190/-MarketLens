import os
import threading
import base64
import json
import time
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
# =========================================================
# SETTINGS
# =========================================================
TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
VISION_BASE_URL = (
    "https://developer0hye-qwen2-5-vl-7b-instruct.hf.space"
)
VISION_CALL_URL = (
    VISION_BASE_URL
    + "/gradio_api/call/qwen_vl_inference"
)
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
# =========================================================
# RENDER HEALTH SERVER
# =========================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain"
        )
        self.end_headers()
        self.wfile.write(
            b"MarketLens Vision v0.5 is running"
        )
    def log_message(self, format, *args):
        pass
def start_web_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )
    server.serve_forever()
# =========================================================
# TELEGRAM START
# =========================================================
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🧠 MARKETLENS v0.5\n\n"
        "Vision Engine подключён.\n\n"
        "📸 Отправь скриншот TradingView."
    )
# =========================================================
# VISION ANALYSIS
# =========================================================
def analyze_chart(image_path):
    print("[VISION] Preparing image...")
    with open(image_path, "rb") as file:
        image_bytes = file.read()
    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")
    image_url = (
        "data:image/jpeg;base64,"
        + image_base64
    )
    prompt = """
Ты — Technical Engine системы MarketLens.
Проанализируй предоставленный скриншот
TradingView.
Работай ТОЛЬКО с информацией, которую
можно реально увидеть на изображении.
Определи:
1. Актив / валютную пару.
2. Таймфрейм.
3. Текущее направление:
ВВЕРХ / ВНИЗ / БОКОВИК / НЕОПРЕДЕЛЁННО.
4. Рыночную структуру:
HH / HL / LH / LL.
5. Ближайшую поддержку.
6. Ближайшее сопротивление.
7. Свечную структуру.
8. Разворотные свечные паттерны,
если они действительно видны.
9. Объём, если он присутствует.
10. Импульс или коррекцию.
11. Основной сценарий.
12. Альтернативный сценарий.
13. Условия подтверждения.
14. Условия отмены.
НЕ ПРИДУМЫВАЙ цены, уровни,
паттерны или объём.
Если график плохо виден,
напиши:
НЕДОСТАТОЧНО ДАННЫХ — НУЖЕН НОВЫЙ СКРИНШОТ.
Отвечай в формате:
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
Не обещай прибыль и не утверждай,
что движение цены гарантировано.
"""
    payload = {
        "data": [
            {
                "path": None,
                "url": image_url,
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
    print("[VISION] Sending request...")
    response = requests.post(
        VISION_CALL_URL,
        json=payload,
        timeout=60
    )
    print(
        f"[VISION] HTTP status: "
        f"{response.status_code}"
    )
    if response.status_code != 200:
        print(
            "[VISION ERROR] Response:"
        )
        print(
            response.text[:3000]
        )
        raise RuntimeError(
            "Vision API returned HTTP "
            + str(response.status_code)
        )
    result = response.json()
    print("[VISION] Job created")
    event_id = result.get("event_id")
    if not event_id:
        raise RuntimeError(
            "Vision API did not return event_id"
        )
    print(
        f"[VISION] Event ID: {event_id}"
    )
    # =====================================================
    # WAIT FOR RESULT
    # =====================================================
    events_url = (
        VISION_BASE_URL
        + "/gradio_api/call/"
        + "qwen_vl_inference/"
        + event_id
    )
    print(
        "[VISION] Waiting for result..."
    )
    with requests.get(
        events_url,
        stream=True,
        timeout=180,
        headers={
            "Accept": "text/event-stream"
        }
    ) as stream:
        if stream.status_code != 200:
            print(
                "[VISION ERROR] Event HTTP:"
            )
            print(
                stream.text[:3000]
            )
            raise RuntimeError(
                "Vision event stream HTTP "
                + str(stream.status_code)
            )
        current_event = None
        for raw_line in stream.iter_lines(
            decode_unicode=True
        ):
            if not raw_line:
                continue
            line = raw_line.strip()
            print(
                f"[VISION STREAM] {line[:500]}"
            )
            if line.startswith("event:"):
                current_event = (
                    line.split(
                        "event:",
                        1
                    )[1].strip()
                )
                continue
            if line.startswith("data:"):
                data_text = (
                    line.split(
                        "data:",
                        1
                    )[1].strip()
                )
                if current_event == "complete":
                    try:
                        data = json.loads(
                            data_text
                        )
                    except Exception:
                        data = data_text
                    print(
                        "[VISION] Complete"
                    )
                    return extract_result(
                        data
                    )
                if current_event == "error":
                    raise RuntimeError(
                        "Vision returned error: "
                        + data_text[:1000]
                    )
    raise RuntimeError(
        "Vision did not return a result"
    )
# =========================================================
# RESULT PARSER
# =========================================================
def extract_result(result):
    print(
        "[VISION] Parsing result..."
    )
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        if len(result) == 0:
            return "Vision вернул пустой результат."
        first = result[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in (
                "text",
                "value",
                "output"
            ):
                if key in first:
                    return str(
                        first[key]
                    )
        return str(first)
    if isinstance(result, dict):
        for key in (
            "output",
            "text",
            "value"
        ):
            if key in result:
                value = result[key]
                if isinstance(
                    value,
                    str
                ):
                    return value
                return str(value)
    return str(result)
# =========================================================
# RECEIVE SCREENSHOT
# =========================================================
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
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            "💾 Сохраняю изображение...\n"
            "🧠 Запускаю Vision Engine..."
        )
        photo = message.photo[-1]
        telegram_file = (
            await context.bot.get_file(
                photo.file_id
            )
        )
        timestamp = datetime.now(
            timezone.utc
        ).strftime(
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
            f"[SCREENSHOT] Saved: "
            f"{filepath}"
        )
        analysis = analyze_chart(
            filepath
        )
        if not analysis:
            analysis = (
                "❌ Vision Engine "
                "вернул пустой ответ."
            )
        if len(analysis) > 3900:
            analysis = analysis[:3900]
        await message.reply_text(
            analysis
            + "\n\n"
            "⚠️ Технический анализ "
            "не является гарантией "
            "движения цены."
        )
        print(
            "[MARKETLENS] Analysis sent "
            "to Telegram"
        )
    except Exception as error:
        print(
            "[ERROR] "
            f"{type(error).__name__}: "
            f"{error}"
        )
        await message.reply_text(
            "❌ Vision Engine не смог "
            "обработать график.\n\n"
            f"Ошибка: "
            f"{type(error).__name__}\n\n"
            "Проверь Render Logs."
        )
# =========================================================
# MAIN
# =========================================================
def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден "
            "в Environment Variables"
        )
    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()
    print(
        f"HTTP server started "
        f"on port {PORT}"
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
        "🧠 MarketLens Vision v0.5 started"
    )
    app.run_polling()
if __name__ == "__main__":
    main()