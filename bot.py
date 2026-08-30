import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
# ============================================================
# MARKETLENS v0.8
# Telegram + Qwen2.5-VL Gradio API
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ============================================================
# QWEN SPACE
# ============================================================
QWEN_SPACE_URL = (
    "https://developer0hye-qwen2-5-vl-7b-instruct.hf.space"
)
GRADIO_UPLOAD_URL = (
    f"{QWEN_SPACE_URL}/gradio_api/upload"
)
GRADIO_CALL_URL = (
    f"{QWEN_SPACE_URL}/gradio_api/call/qwen_vl_inference"
)
# ============================================================
# STORAGE
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
# HTTP HEALTH SERVER
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"MarketLens v0.8 is running"
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
# MARKET ANALYSIS PROMPT
# ============================================================
VISION_PROMPT = """
Ты — MarketLens Technical Engine.
Проанализируй изображение графика TradingView.
Главное:
1. Определи текущую структуру цены.
2. Определи направление движения:
   ВВЕРХ / ВНИЗ / НЕ ВХОДИТЬ.
3. Найди ближайшие уровни поддержки и сопротивления,
   если они видны на графике.
4. Проанализируй свечи и поведение цены.
5. Определи импульс, откат или возможный разворот.
6. Учитывай объём, только если он реально виден.
7. Определи ближайший наиболее вероятный сценарий.
8. Не выдумывай значения цены, уровни или индикаторы,
   которых невозможно прочитать.
9. Если график слишком плохого качества или информации
   недостаточно — прямо скажи, что нужен новый скриншот.
Ответ дай коротко и конкретно в формате:
📊 MARKETLENS ANALYSIS
Направление: ВВЕРХ / ВНИЗ / НЕ ВХОДИТЬ
Уверенность: XX%
Структура:
...
Уровни:
Поддержка: ...
Сопротивление: ...
Свечи:
...
Сценарий:
...
⚠️ Риск:
...
Не пиши длинную теорию.
Не гарантируй результат сделки.
"""
# ============================================================
# QWEN API
# ============================================================
def qwen_analyze_image(
    image_path: Path,
) -> str:
    print(
        "[VISION] Preparing image..."
    )
    if not image_path.exists():
        raise RuntimeError(
            "Screenshot file does not exist"
        )
    # --------------------------------------------------------
    # STEP 1 — Upload image to Gradio
    # --------------------------------------------------------
    print(
        "[VISION] Uploading image..."
    )
    with open(
        image_path,
        "rb",
    ) as image_file:
        response = requests.post(
            GRADIO_UPLOAD_URL,
            files={
                "files": (
                    image_path.name,
                    image_file,
                    "image/jpeg",
                )
            },
            timeout=120,
        )
    print(
        f"[VISION] Upload HTTP: {response.status_code}"
    )
    if response.status_code != 200:
        print(
            "[VISION ERROR] Upload response:"
        )
        print(response.text)
        raise RuntimeError(
            f"Qwen upload HTTP {response.status_code}"
        )
    try:
        upload_result = response.json()
    except Exception as e:
        print(
            "[VISION ERROR] Upload JSON:"
        )
        print(response.text)
        raise RuntimeError(
            "Qwen upload returned invalid JSON"
        ) from e
    print(
        "[VISION] Upload result:"
    )
    print(
        json.dumps(
            upload_result,
            ensure_ascii=False,
        )
    )
    # Gradio normally returns:
    # ["tmp/filename.jpg"]
    if isinstance(
        upload_result,
        list,
    ):
        if not upload_result:
            raise RuntimeError(
                "Qwen upload returned empty list"
            )
        uploaded_path = upload_result[0]
    elif isinstance(
        upload_result,
        dict,
    ):
        uploaded_path = (
            upload_result.get("path")
            or upload_result.get("name")
            or upload_result.get("url")
        )
    else:
        raise RuntimeError(
            "Unknown Qwen upload response"
        )
    if not uploaded_path:
        raise RuntimeError(
            "Could not determine uploaded image path"
        )
    print(
        f"[VISION] Uploaded path: {uploaded_path}"
    )
    # --------------------------------------------------------
    # STEP 2 — Prepare FileData
    # --------------------------------------------------------
    image_data = {
        "path": uploaded_path,
        "url": None,
        "size": image_path.stat().st_size,
        "orig_name": image_path.name,
        "mime_type": "image/jpeg",
        "is_stream": False,
        "meta": {
            "_type": "gradio.FileData"
        },
    }
    payload = {
        "data": [
            image_data,
            VISION_PROMPT,
        ]
    }
    # --------------------------------------------------------
    # STEP 3 — Create Gradio job
    # --------------------------------------------------------
    print(
        "[VISION] Sending request..."
    )
    response = requests.post(
        GRADIO_CALL_URL,
        json=payload,
        timeout=120,
    )
    print(
        f"[VISION] HTTP status: {response.status_code}"
    )
    if response.status_code not in (
        200,
        201,
    ):
        print(
            "[VISION ERROR] Response:"
        )
        print(response.text)
        raise RuntimeError(
            f"Qwen call HTTP {response.status_code}"
        )
    try:
        job = response.json()
    except Exception as e:
        print(
            "[VISION ERROR] Invalid job JSON:"
        )
        print(response.text)
        raise RuntimeError(
            "Qwen returned invalid job JSON"
        ) from e
    print(
        "[VISION] Job created"
    )
    print(
        json.dumps(
            job,
            ensure_ascii=False,
        )
    )
    event_id = job.get(
        "event_id"
    )
    if not event_id:
        raise RuntimeError(
            "Qwen did not return event_id"
        )
    print(
        f"[VISION] Event ID: {event_id}"
    )
    # --------------------------------------------------------
    # STEP 4 — Read SSE result
    # --------------------------------------------------------
    result_url = (
        f"{GRADIO_CALL_URL}/{event_id}"
    )
    print(
        "[VISION] Waiting for result..."
    )
    with requests.get(
        result_url,
        stream=True,
        timeout=180,
    ) as stream:
        if stream.status_code != 200:
            print(
                "[VISION ERROR] Result HTTP:"
            )
            print(
                stream.status_code
            )
            print(
                stream.text
            )
            raise RuntimeError(
                f"Qwen result HTTP {stream.status_code}"
            )
        event_name = None
        data_lines = []
        for raw_line in stream.iter_lines(
            decode_unicode=True
        ):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                continue
            print(
                f"[VISION STREAM] {line}"
            )
            if line.startswith(
                "event:"
            ):
                event_name = (
                    line[6:].strip()
                )
            elif line.startswith(
                "data:"
            ):
                data_lines.append(
                    line[5:].strip()
                )
                data_text = "\n".join(
                    data_lines
                )
                # ------------------------------------------------
                # COMPLETE
                # ------------------------------------------------
                if event_name == "complete":
                    try:
                        result_data = json.loads(
                            data_text
                        )
                    except Exception:
                        result_data = data_text
                    print(
                        "[VISION] Complete event received"
                    )
                    # Gradio returns:
                    # {"data": ["text"]}
                    if isinstance(
                        result_data,
                        dict,
                    ):
                        output = result_data.get(
                            "data"
                        )
                        if isinstance(
                            output,
                            list,
                        ) and output:
                            return str(
                                output[0]
                            )
                    if isinstance(
                        result_data,
                        list,
                    ) and result_data:
                        return str(
                            result_data[0]
                        )
                    return str(
                        result_data
                    )
                # ------------------------------------------------
                # ERROR
                # ------------------------------------------------
                if event_name == "error":
                    error_value = data_text
                    print(
                        "[VISION] Error event:"
                    )
                    print(
                        error_value
                    )
                    raise RuntimeError(
                        f"Vision returned error: {error_value}"
                    )
                # ------------------------------------------------
                # GENERIC DATA
                # ------------------------------------------------
                if event_name == "generating":
                    try:
                        result_data = json.loads(
                            data_text
                        )
                        if isinstance(
                            result_data,
                            list,
                        ) and result_data:
                            return str(
                                result_data[0]
                            )
                    except Exception:
                        pass
                # Reset after processing
                data_lines = []
    raise RuntimeError(
        "Qwen stream ended without result"
    )
# ============================================================
# ASYNC VISION WRAPPER
# ============================================================
async def analyze_with_vision(
    image_path: Path,
) -> str:
    return await asyncio.to_thread(
        qwen_analyze_image,
        image_path,
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
        "🧠 MARKETLENS v0.8\n\n"
        "Vision Engine подключён.\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я попробую определить:\n"
        "• направление цены\n"
        "• поддержку и сопротивление\n"
        "• структуру рынка\n"
        "• свечное движение\n"
        "• ближайший сценарий\n"
        "• уровень уверенности"
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
    await update.message.reply_text(
        "🧠 MARKETLENS v0.8\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот графика."
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
        # Download
        # ----------------------------------------------------
        photo = message.photo[-1]
        telegram_file = (
            await context.bot.get_file(
                photo.file_id
            )
        )
        now = datetime.now(
            timezone.utc
        )
        timestamp = now.strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        filename = (
            f"chart_"
            f"{message.from_user.id}_"
            f"{timestamp}.jpg"
        )
        filepath = (
            SCREENSHOTS_DIR
            / filename
        )
        await telegram_file.download_to_drive(
            custom_path=str(filepath)
        )
        size_kb = (
            filepath.stat().st_size
            / 1024
        )
        print(
            f"[SCREENSHOT] Saved: {filepath}"
        )
        print(
            f"[SCREENSHOT] Size: {size_kb:.1f} KB"
        )
        # ----------------------------------------------------
        # Tell user analysis started
        # ----------------------------------------------------
        await message.reply_text(
            "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
            f"💾 {filename}\n"
            f"📦 {size_kb:.1f} KB\n\n"
            "🧠 MarketLens Vision v0.8\n"
            "⏳ Анализирую график..."
        )
        # ----------------------------------------------------
        # Vision
        # ----------------------------------------------------
        print(
            "[VISION] Starting analysis..."
        )
        result = await analyze_with_vision(
            filepath
        )
        # ----------------------------------------------------
        # Result
        # ----------------------------------------------------
        if not result or not str(
            result
        ).strip():
            raise RuntimeError(
                "Vision returned empty result"
            )
        print(
            "[VISION] Analysis received"
        )
        await message.reply_text(
            str(result)
        )
    except Exception as e:
        logger.exception(
            "[VISION ERROR]"
        )
        await message.reply_text(
            "❌ Vision Engine не смог "
            "обработать график.\n\n"
            f"Ошибка: {type(e).__name__}\n\n"
            "Проверь Render Logs."
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
        update.message.text
        or ""
    )
    if text.startswith("/"):
        return
    await update.message.reply_text(
        "📸 Отправь скриншот графика "
        "TradingView.\n\n"
        "После получения изображения "
        "MarketLens запустит Vision Engine."
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
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        "🧠 MarketLens Vision v0.8 starting..."
    )
    # --------------------------------------------------------
    # Render health server
    # --------------------------------------------------------
    Thread(
        target=start_http_server,
        daemon=True,
    ).start()
    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------
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
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )
    # Errors
    application.add_error_handler(
        error_handler
    )
    print(
        "🧠 MarketLens Vision v0.8 started"
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
        "🤖 Qwen Space:"
        " developer0hye/Qwen2.5-VL-7B-Instruct"
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