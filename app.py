"""Расшифровка и скачивание видео по ссылке Instagram. Сервер для Render (или локального запуска).

Запуск на Render: uvicorn app:app --host 0.0.0.0 --port $PORT
Локально:          python app.py

Переменные окружения (необязательно):
  WHISPER_MODEL=tiny|base|small   (по умолчанию base: помещается в 512 MB)
  COOKIES_BROWSER=chrome|safari|firefox|edge  (только локально, для приватных роликов)
"""

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DOWNLOADS = Path(tempfile.gettempdir()) / "downloads"
MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")
COOKIES_BROWSER = os.environ.get("COOKIES_BROWSER") or None

app = FastAPI(title="Расшифровка видео")

_model = None
_lock = threading.Lock()  # одна расшифровка за раз: памяти мало


def download_media(url, outdir, fmt):
    """Скачивает медиа через yt-dlp. Возвращает (путь к файлу, info)."""
    import yt_dlp

    opts = {
        "format": fmt,
        "outtmpl": str(Path(outdir) / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (COOKIES_BROWSER,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    return path, info


def run_whisper(media, lang):
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        segments_iter, info = _model.transcribe(
            str(media), language=lang, vad_filter=True, beam_size=1
        )
        segments = list(segments_iter)  # читаем файл внутри блокировки
    return segments, info


def save_upload(upload, dest_dir):
    name = Path(upload.filename or "upload").name or "upload"
    path = Path(dest_dir) / name
    with open(path, "wb") as out:
        shutil.copyfileobj(upload.file, out)
    return path


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL_NAME}


@app.post("/api/transcribe")
def transcribe_endpoint(
    url: str = Form(""),
    lang: str = Form(""),
    file: Optional[UploadFile] = File(None),
):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if file is not None and file.filename:
                media = save_upload(file, tmp)
            elif url.strip():
                media, _ = download_media(url.strip(), tmp, "bestaudio/best")
            else:
                raise HTTPException(400, "Вставьте ссылку или выберите файл.")
            segments, info = run_whisper(media, lang.strip() or None)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Не получилось расшифровать: {e}")

    return {
        "language": info.language,
        "segments": [
            {"start": s.start, "text": s.text.strip()}
            for s in segments
            if s.text.strip()
        ],
    }


@app.post("/api/download")
def download_endpoint(url: str = Form(...)):
    url = url.strip()
    if not url:
        raise HTTPException(400, "Вставьте ссылку.")
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    try:
        path, _ = download_media(url, DOWNLOADS, "best[ext=mp4]/best")
    except Exception as e:
        raise HTTPException(400, f"Не получилось скачать: {e}")
    return FileResponse(path, filename=path.name, media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
