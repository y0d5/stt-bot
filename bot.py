import os
import re
import time
import logging
import tempfile
import requests
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── 로깅 설정 ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── 환경변수 ────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ASSEMBLYAI_API_KEY = os.environ["ASSEMBLYAI_API_KEY"]

ASSEMBLYAI_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
ASSEMBLYAI_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"

HEADERS = {"authorization": ASSEMBLYAI_API_KEY}

# ── 상수 ────────────────────────────────────────────────────
DEFAULT_LANG = "ko"
SPEAKER_LABELS = {
    "A": "화자 1",
    "B": "화자 2",
    "C": "화자 3",
    "D": "화자 4",
}
MERGE_SECONDS = 30


# ── AssemblyAI 파이프라인 ────────────────────────────────────
def upload_file(path: str) -> str:
    with open(path, "rb") as f:
        response = requests.post(ASSEMBLYAI_UPLOAD_URL, headers=HEADERS, data=f)
    response.raise_for_status()
    return response.json()["upload_url"]


def request_transcript(upload_url: str, language: str = DEFAULT_LANG) -> str:
    payload = {
        "audio_url": upload_url,
        "speaker_labels": True,
        "language_detection": True,
    }
    response = requests.post(ASSEMBLYAI_TRANSCRIPT_URL, json=payload, headers=HEADERS)
    response.raise_for_status()
    return response.json()["id"]


def poll_transcript(transcript_id: str) -> dict:
    url = f"{ASSEMBLYAI_TRANSCRIPT_URL}/{transcript_id}"
    while True:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        status = data["status"]
        if status == "completed":
            return data
        elif status == "error":
            raise RuntimeError(f"AssemblyAI 오류: {data.get('error')}")
        logger.info(f"변환 중... ({status})")
        time.sleep(3)


def format_transcript(data: dict) -> str:
    utterances = data.get("utterances", [])
    if not utterances:
        return data.get("text", "")

    lines = []
    current_speaker = None
    current_texts = []
    current_start = None

    for utt in utterances:
        speaker = SPEAKER_LABELS.get(utt["speaker"], f"화자 {utt['speaker']}")
        start_ms = utt["start"]
        start_sec = start_ms // 1000
        text = utt["text"].strip()

        if (speaker != current_speaker or
                (current_start is not None and start_sec - current_start >= MERGE_SECONDS)):
            if current_texts:
                mm, ss = divmod(current_start, 60)
                lines.append(f"{current_speaker} {mm:02d}:{ss:02d}\n{''.join(current_texts).strip()}")
            current_speaker = speaker
            current_texts = []
            current_start = start_sec

        current_texts.append(" " + text)

    if current_texts:
        mm, ss = divmod(current_start, 60)
        lines.append(f"{current_speaker} {mm:02d}:{ss:02d}\n{''.join(current_texts).strip()}")

    return "\n\n".join(lines)


def transcribe_with_diarization(path: str, language: str = DEFAULT_LANG) -> str:
    logger.info("AssemblyAI 업로드 중...")
    upload_url = upload_file(path)
    logger.info("변환 요청 중...")
    transcript_id = request_transcript(upload_url, language)
    logger.info(f"transcript_id: {transcript_id}")
    data = poll_transcript(transcript_id)
    return format_transcript(data)


# ── 오디오 처리 파이프라인 ────────────────────────────────────
async def process_audio(update: Update, file_id: str, language: str = DEFAULT_LANG):
    msg = update.effective_message
    status = await msg.reply_text("🎙️ 파일 수신 중…")

    with tempfile.TemporaryDirectory() as tmpdir:
        tg_file = await update.get_bot().get_file(file_id)
        suffix = Path(tg_file.file_path).suffix or ".m4a"
        local_path = os.path.join(tmpdir, f"audio{suffix}")
        await tg_file.download_to_drive(local_path)

        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        logger.info(f"다운로드 완료: {size_mb:.1f} MB")
        await status.edit_text("⚙️ 화자 분리 및 변환 중… (1~2분 소요)")

        text = transcribe_with_diarization(local_path, language)

    await status.delete()
    for i in range(0, len(text), 4000):
        await msg.reply_text(text[i : i + 4000])


# ── 커맨드 핸들러 ────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙️ *STT 봇 (화자 구분 지원)*\n\n"
        "음성 메시지 또는 오디오 파일을 전송하면\n"
        "화자별로 구분하여 텍스트로 변환해 드립니다.\n\n"
        "📌 *지원 포맷:* m4a · mp3 · wav · ogg · flac\n"
        "📌 *파일 크기:* 20MB 이하\n\n"
        "━━━━━━━━━━━━━━━\n"
        "/lang ko — 한국어 (기본)\n"
        "/lang en — 영어\n"
        "/lang ja — 일본어\n",
        parse_mode="Markdown",
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /lang ko | en | ja")
        return
    lang = context.args[0].lower()
    valid = {"ko": "한국어", "en": "영어", "ja": "일본어"}
    if lang not in valid:
        await update.message.reply_text(f"지원 언어: {', '.join(valid.keys())}")
        return
    context.user_data["lang"] = lang
    await update.message.reply_text(f"✅ 언어 설정: {valid[lang]}")


# ── 메시지 핸들러 ────────────────────────────────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await process_audio(update, update.message.voice.file_id, lang)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await process_audio(update, update.message.audio.file_id, lang)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    audio_exts = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".mp4"}
    suffix = Path(doc.file_name or "").suffix.lower()
    if suffix not in audio_exts:
        await update.message.reply_text("⚠️ 지원하지 않는 파일 형식입니다.")
        return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await process_audio(update, doc.file_id, lang)


# ── 구글 드라이브 링크 처리 ──────────────────────────────────
def extract_gdrive_id(url: str):
    for pattern in [r"/file/d/([a-zA-Z0-9_-]+)", r"id=([a-zA-Z0-9_-]+)"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def download_gdrive_file(file_id: str, dest_path: str) -> bool:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    session = requests.Session()
    response = session.get(url, stream=True)
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            url = f"https://drive.google.com/uc?export=download&confirm={value}&id={file_id}"
            response = session.get(url, stream=True)
            break
    if response.status_code != 200:
        return False
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)
    return True


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if "drive.google.com" not in text:
        await update.message.reply_text("⚠️ 구글 드라이브 링크만 지원됩니다.")
        return
    file_id = extract_gdrive_id(text)
    if not file_id:
        await update.message.reply_text("⚠️ 링크에서 파일 ID를 찾을 수 없습니다.")
        return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    msg = update.effective_message
    status = await msg.reply_text("🔗 구글 드라이브에서 다운로드 중…")
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, "audio.m4a")
        success = download_gdrive_file(file_id, local_path)
        if not success:
            await status.edit_text("❌ 다운로드 실패. 공유 설정을 '링크가 있는 모든 사용자'로 변경해 주세요.")
            return
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        await status.edit_text(f"⚙️ 다운로드 완료 ({size_mb:.1f}MB), 화자 분리 및 변환 중…")
        text_result = transcribe_with_diarization(local_path, lang)
    await status.delete()
    for i in range(0, len(text_result), 4000):
        await msg.reply_text(text_result[i : i + 4000])


# ── 메인 ────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    logger.info("STT 봇 시작 (화자 구분 모드)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
