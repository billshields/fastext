# SpeedReader — Ideas & Roadmap

## Bugs / Polish
- No loading indicator when CodeMirror CDN modules are being fetched in the editor
- Chunk size in reader settings doesn't persist across documents (stored per-session, not per-preference)

## Features

### Content Input
- Paste-to-read — let users paste raw text directly instead of requiring a file upload
- URL import — paste a URL and extract article text (readability-style)
- Support more file types (txt, docx, html)

### Reader Experience
- Keyboard shortcut overlay / help tooltip — users don't know Space, arrows, Up/Down exist
- Progress scrubber — click/drag bar to jump to any position in the document
- Chapter navigation — jump between chapters if the document has them (chapter_index is already stored)
- Sentence context preview — show the surrounding sentence below the RSVP display
- Comprehension check — periodic quiz/recall prompts after sections
- Dark/light theme presets instead of individual color pickers
- Peripheral word preview — show the next/previous word faintly on either side

### Reading Stats
- WPM history graph — track speed over time per document and overall
- Reading time dashboard — daily/weekly/monthly reading time
- Documents completed count and streak tracking
- Words read per session summary

### Library Management
- Search and filter documents
- Tags / folders for organization
- Sort by last read, upload date, progress, title
- Bulk delete

### Mobile Support
- Tap to play/pause
- Swipe left/right to rewind/forward
- Responsive layout for small screens
- Full-screen reading mode

### Social / Sharing
- Share reading speed results
- Public reading lists
- Reading challenges / goals

## Infrastructure
- Backend API tests — zero test coverage currently
- Frontend smoke tests
- Production deployment config (gunicorn, nginx, proper settings, HTTPS)
- Process manager (systemd/supervisor) instead of start.sh for production
- Static file bundling — CodeMirror currently loaded from CDN on every page load
- Database backups
- Rate limiting on API endpoints
- Email verification on registration
