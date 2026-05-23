# GottaWordFast — Ideas & Roadmap

## Bugs / Polish
- No loading indicator when CodeMirror CDN modules are being fetched in the editor

## Features

### Content Input
- URL import — paste a URL and extract article text (readability-style)
- Support more file types (txt, docx, html)

### Reader Experience
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
- Tags / folders for organization

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
