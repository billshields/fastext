# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

GottaWordFast is a Django-based RSVP (Rapid Serial Visual Presentation) speed reading web app. Users upload PDF/EPUB files or paste text, which gets chunked into individual words, then displayed one word at a time at a configurable WPM.

## Commands

```bash
# Activate venv (required before any command)
source venv/bin/activate

# Start all services (Redis, MySQL, Celery, Django dev server)
./start.sh

# Django dev server only
python manage.py runserver 0.0.0.0:8000

# Celery worker (needed for document processing)
celery -A config worker --loglevel=info

# Migrations
python manage.py makemigrations
python manage.py migrate

# Run tests (no test coverage exists yet)
python manage.py test
python manage.py test apps.documents
python manage.py test apps.reading
```

## Architecture

**Django project layout** — `config/` is the Django project package (settings, urls, celery, wsgi). `apps/` contains three apps. Settings use a split-settings pattern: `config/settings/base.py` with `config/settings/dev.py` overlay. Default settings module is `config.settings.dev`.

**Three Django apps:**
- `apps.users` — Custom User model (extends AbstractUser), UserPreferences (WPM, colors, font, TTS settings). Preferences auto-created via signal on user creation. JWT auth via simplejwt.
- `apps.documents` — Document upload/paste and processing. Documents go through status lifecycle: pending → processing → completed/failed. The `process_document` Celery task extracts words from PDF (pdfplumber) or EPUB (ebooklib+BeautifulSoup) into `DocumentChunk` rows (one row per word, with position, chapter/paragraph index, sentence_end flag). Text can also be edited in-browser, which re-chunks.
- `apps.reading` — ReadingSession tracks per-user per-document reading state (position, WPM, chunk_size, total_reading_time). One session per user-document pair. Words are fetched in batches of up to 500-1000 via the `/api/read/<id>/words/` endpoint.

**Frontend** — Vanilla JS (no framework) served via Django templates. Key files:
- `static/js/api.js` — API client wrapper with JWT token management and auto-refresh
- `static/js/app.js` — Library page (upload, search, sort, bulk delete)
- `static/js/reader.js` — RSVP reader engine (play/pause, WPM control, word display, progress saving)
- `static/js/tts.js` — Web Speech API text-to-speech integration
- `templates/editor.html` — CodeMirror-based document text editor (CDN-loaded)

**Data flow for reading:** Frontend fetches word batches → displays words one at a time at configured WPM → periodically POSTs position/reading_time back to server → prefetches next batch when buffer runs low.

## Key Technical Details

- Database: MySQL with utf8mb4 charset
- Auth: JWT tokens (30min access, 7-day refresh with rotation)
- Async: Celery with Redis broker for document processing
- File uploads stored in `media/uploads/YYYY/MM/`
- DocumentChunks bulk-created in batches of 5000
- Config via python-decouple (env vars or .env file)
- Custom user model: `AUTH_USER_MODEL = 'users.User'`
