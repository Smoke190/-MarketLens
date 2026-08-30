import os
import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
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
# MARKETLENS v0.9
# Telegram + Screenshot + Qwen Vision
# ============================================================
VERSION = "0.9"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set in Render Environment Variables"
    )
# ------------------------------------------------------------
# QWEN SPACE
# ------------------------------------------------------------
QWEN_SPACE = os.environ.get(
    "QWEN_SPACE",
    "developer0hye/Qwen2.5-VL-7B-Instruct"
)
QWEN_BASE_URL = os.environ.get(
    "QWEN_BASE_URL",
    f"https://{QWEN_SPACE}.hf.space"
)
QWEN_API_PATH = "/gradio_api/call/qwen_vl_inference"
# ------------------------------------------------------------
# DIRECT ENDPOINT OVERRIDE
# ------------------------------------------------------------
# If the Space changes its URL, you can put the complete URL
# into Render Environment Variables as:
#
# QWEN_API_URL
#
# Example:
# https://example.hf.space/gradio_api/call/qwen_vl_inference
QWEN_API_URL = os.environ.get(
    "QWEN_API_URL",
    QWEN_BASE_URL + QWEN_API_PATH
)
# ------------------------------------------------------------
# DIRECT FILE UPLOAD ENDPOINT
# ------------------------------------------------------------
QWEN_UPLOAD_URL = os.environ.get(
    "QWEN_UPLOAD_URL",
    QWEN_BASE_URL + "/gradio_api/upload"
)
# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------
VISION_TIMEOUT = int(
    os.environ.get("VISION_TIMEOUT", "180")
)
VISION_POLL_TIMEOUT = int(
    os.environ.get("VISION_POLL_TIMEOUT", "180")
)
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("MarketLens")
# ============================================================
# HEALTH SERVER
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
Ты — технический аналитик MarketLens.
Проанализируй предоставленный скриншот торгового графика.
Определи:
1. Направление движения:
   UP / DOWN / SIDEWAYS
2. Структуру рынка:
   - тренд
   - импульс
   - коррекция
   - пробой
   - ложный пробой
3. Ключевые уровни:
   - ближайшая поддержка
   - ближайшее сопротивление
4. Поведение свечей.
5. Объём, если он присутствует на графике.
6. Вероятный ближайший сценарий.
7. Что должно произойти для подтверждения сценария.
Не выдумывай данные, которых не видно.
Ответ дай коротко и структурированно.
Формат:
📊 MARKETLENS ANALYSIS
Направление: UP / DOWN / SIDEWAYS
Тренд:
...
Уровень поддержки:
...
Уровень сопротивления:
...
Сигнал:
...
Подтверждение:
...
Риск:
...
Важно:
анализ является вероятностным и не гарантирует движение цены.
"""
# ============================================================
# HELPERS
# ============================================================
def extract_text_from_result(data):
    """
    Пытается извлечь текст из разных вариантов ответа Gradio.
    """
    if data is None:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        if not data:
            return None
        parts = []
        for item in data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in (
                    "text",
                    "value",
                    "output",
                    "content"
                ):
                    if key in item:
                        parts.append(
                            str(item[key])
                        )
        if parts:
            return "\n".join(parts)
        return str(data)
    if isinstance(data, dict):
        for key in (
            "text",
            "value",
            "output",
            "content",
            "result"
        ):
            if key in data:
                return str(data[key])
        return str(data)
    return str(data)
def parse_event_stream(response):
    """
    Разбор SSE stream от Gradio.
    """
    result = None
    error = None
    for raw_line in response.iter_lines(
        decode_unicode=True
    ):
        if not raw_line:
            continue
        line = raw_line.strip()
        if line.startswith("event:"):
            event_type = line[
                len("event:"):].strip()
            if event_type == "error":
                error = "Qwen Space returned error event"
            elif event_type == "complete":
                pass
        elif line.startswith("data:"):
            data_text = line[
                len("data:"):].strip()
            logger.info(
                "[VISION STREAM] data: %s",
                data_text[:1000]
            )
            if data_text == "null":
                if error:
                    error = (
                        "Qwen Space returned "
                        "error with null data"
                    )
                continue
            try:
                import json
                parsed = json.loads(
                    data_text
                )
                result = extract_text_from_result(
                    parsed
                )
            except Exception:
                result = data_text
    if error and not result:
        raise RuntimeError(error)
    return result
# ============================================================
# UPLOAD IMAGE
# ============================================================
def upload_image(image_path):
    logger.info(
        "[VISION] Uploading image..."
    )
    if not Path(image_path).exists():
        raise RuntimeError(
            "Image file does not exist"
        )
    with open(
        image_path,
        "rb"
    ) as f:
        files = {
            "files": (
                Path(image_path).name,
                f,
                "image/jpeg"
            )
        }
        response = requests.post(
            QWEN_UPLOAD_URL,
            files=files,
            timeout=VISION_TIMEOUT
        )
    logger.info(
        "[VISION] Upload HTTP: %s",
        response.status_code
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Qwen upload failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )
    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(
            "Qwen upload returned invalid JSON: "
            f"{response.text[:1000]}"
        ) from e
    logger.info(
        "[VISION] Upload result: %s",
        str(data)[:1000]
    )
    if isinstance(data, list) and data:
        uploaded_path = data[0]
    elif isinstance(data, dict):
        uploaded_path = (
            data.get("path")
            or data.get("url")
        )
    else:
        uploaded_path = None
    if not uploaded_path:
        raise RuntimeError(
            "Could not determine uploaded image path"
        )
    return uploaded_path
# ============================================================
# CREATE QWEN JOB
# ============================================================
def create_qwen_job(
    uploaded_path,
    prompt
):
    logger.info(
        "[VISION] Creating Qwen job..."
    )
    payload = {
        "data": [
            {
                "path": uploaded_path,
                "url": None,
                "size": None,
                "orig_name": Path(
                    uploaded_path
                ).name,
                "mime_type": "image/jpeg",
                "is_stream": False,
                "meta": {
                    "_type": "gradio.FileData"
                }
            },
            prompt
        ]
    }
    response = requests.post(
        QWEN_API_URL,
        json=payload,
        timeout=VISION_TIMEOUT
    )
    logger.info(
        "[VISION] API HTTP: %s",
        response.status_code
    )
    logger.info(
        "[VISION] API response: %s",
        response.text[:2000]
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Qwen API failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:1500]}"
        )
    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(
            "Qwen API returned invalid JSON: "
            f"{response.text[:1500]}"
        ) from e
    event_id = data.get(
        "event_id"
    )
    if not event_id:
        raise RuntimeError(
            "Qwen API did not return event_id: "
            f"{data}"
        )
    logger.info(
        "[VISION] Event ID: %s",
        event_id
    )
    return event_id
# ============================================================
# WAIT FOR RESULT
# ============================================================
def wait_for_qwen_result(
    event_id
):
    result_url = (
        QWEN_API_URL
        + "/"
        + event_id
    )
    logger.info(
        "[VISION] Waiting for result..."
    )
    try:
        with requests.get(
            result_url,
            stream=True,
            timeout=VISION_POLL_TIMEOUT
        ) as response:
            logger.info(
                "[VISION] Stream HTTP: %s",
                response.status_code
            )
            if response.status_code != 200:
                raise RuntimeError(
                    "Qwen result stream failed: "
                    f"HTTP {response.status_code}: "
                    f"{response.text[:1500]}"
                )
            result = parse_event_stream(
                response
            )
    except requests.RequestException as e:
        raise RuntimeError(
            f"Qwen result connection failed: {e}"
        ) from e
    if not result:
        raise RuntimeError(
            "Qwen returned an empty result"
        )
    return result
# ============================================================
# FULL VISION PIPELINE
# ============================================================
def qwen_analyze_image(
    image_path
):
    logger.info(
        "[VISION] Starting analysis..."
    )
    logger.info(
        "[VISION] Space: %s",
        QWEN_SPACE
    )
    logger.info(
        "[VISION] API: %s",
        QWEN_API_URL
    )
    uploaded_path = upload_image(
        image_path
    )
    event_id = create_qwen_job(
        uploaded_path,
        VISION_PROMPT
    )
    result = wait_for_qwen_result(
        event_id
    )
    return result
async def analyze_with_vision(
    image_path
):
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
    if not update.message:
        return
    await update.message.reply_text(
        "🧠 MARKETLENS v0.9\n\n"
        "Vision Engine подключён.\n\n"
        "📸 Отправь скриншот TradingView.\n\n"
        "Я сохраню его и отправлю "
        "в Qwen Vision для анализа."
    )
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    await update.message.reply_text(
        "🧠 MARKETLENS v0.9\n\n"
        "/start — запуск\n"
        "/help — помощь\n\n"
        "📸 Просто отправь скриншот графика."
    )
# ============================================================
# PHOTO HANDLER
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
        # Download Telegram image
        # ----------------------------------------------------
        photo = message.photo[-1]
        telegram_file = await (
            context.bot.get_file(
                photo.file_id
            )
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
        logger.info(
            "[SCREENSHOT] Saved: %s",
            filepath
        )
        logger.info(
            "[SCREENSHOT] Size: %.1f KB",
            size_kb
        )
        # ----------------------------------------------------
        # Inform user
        # ----------------------------------------------------
        status_message = await (
            message.reply_text(
                "📸 СКРИНШОТ ПОЛУЧЕН\n\n"
                f"💾 Файл: {filename}\n"
                f"📦 Размер: {size_kb:.1f} KB\n\n"
                "🧠 MarketLens Vision v0.9\n"
                "⏳ Анализирую график..."
            )
        )
        # ----------------------------------------------------
        # Vision
        # ----------------------------------------------------
        try:
            result = await analyze_with_vision(
                filepath
            )
            logger.info(
                "[VISION] Analysis completed"
            )
            await status_message.edit_text(
                "🧠 MARKETLENS v0.9\n\n"
                f"{result}"
            )
        except Exception as vision_error:
            logger.exception(
                "[VISION ERROR]"
            )
            error_text = str(
                vision_error
            )
            await status_message.edit_text(
                "❌ Vision Engine не смог "
                "обработать график.\n\n"
                f"Ошибка: {error_text[:1200]}\n\n"
                "Проверь Render Logs."
            )
    except Exception as e:
        logger.exception(
            "[PHOTO ERROR]"
        )
        try:
            await message.reply_text(
                "❌ Ошибка обработки "
                "скриншота.\n\n"
                f"{type(e).__name__}: {e}"
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
        "📸 Отправь скриншот "
        "TradingView.\n\n"
        "MarketLens v0.9 автоматически "
        "отправит его в Vision Engine."
    )
# ============================================================
# ERROR HANDLER
# ============================================================
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    error = context.error
    if error:
        logger.error(
            "Telegram error: %s",
            error
        )
        # 409 Conflict is usually caused
        # by another bot process polling
        # the same Telegram bot token.
        if "Conflict" in str(error):
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
    # --------------------------------------------------------
    # Render health server
    # --------------------------------------------------------
    threading.Thread(
        target=start_http_server,
        daemon=True
    ).start()
    # --------------------------------------------------------
    # Startup information
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
        f"🔗 Qwen API: {QWEN_API_URL}"
    )
    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    # --------------------------------------------------------
    # Commands
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
    # Photos
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )
    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text
        )
    )
    # --------------------------------------------------------
    # Errors
    # --------------------------------------------------------
    application.add_error_handler(
        error_handler
    )
    # --------------------------------------------------------
    # Start polling
    # --------------------------------------------------------
    print(
        "🤖 Telegram polling starting..."
    )
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()