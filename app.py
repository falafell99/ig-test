"""Тест: может ли облачный сервер получить ролик Instagram через yt-dlp.

Открой в браузере:
  https://ВАШ-СЕРВИС.onrender.com/check?url=ССЫЛКА_НА_ПУБЛИЧНЫЙ_REEL
  https://ВАШ-СЕРВИС.onrender.com/check?url=ССЫЛКА&dl=1   (то же + пробует скачать файл)

Файлы никуда не сохраняются, после проверки ничего не остаётся.
"""

import tempfile
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, Query

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True, "how": "/check?url=ссылка_на_публичный_reel  (добавьте &dl=1, чтобы попробовать скачать файл)"}


@app.get("/check")
def check(url: str = Query(...), dl: int = Query(0)):
    result = {"url": url}

    # 1. Только метаданные: видит ли сервер ролик вообще
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        result["metadata"] = "ok"
        result["title"] = info.get("title")
        result["duration_sec"] = info.get("duration")
    except Exception as e:
        result["metadata"] = "error"
        result["error"] = str(e)[:500]
        return result

    # 2. Скачивание файла (по желанию)
    if dl:
        try:
            tmp = Path(tempfile.mkdtemp())
            opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": str(tmp / "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
            result["download"] = "ok"
            result["size_mb"] = round(path.stat().st_size / 1e6, 2)
        except Exception as e:
            result["download"] = "error"
            result["error"] = str(e)[:500]

    return result
