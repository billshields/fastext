# GottaWordFast — Ideas & Roadmap

## Bugs / Polish
- No loading indicator when CodeMirror CDN modules are being fetched in the editor

## Features

### Content Input
- ~~URL import — paste a URL and extract article text (readability-style)~~ ✅
- Support more file types (txt, docx, html)
- URL import: batch import — paste multiple URLs or a table of contents page and import all linked articles
- URL import: Cloudflare fallback — some sites block server-side fetching; option to use a headless browser (Playwright) for tougher sites

### Reader Experience
- ~~Progress scrubber — click/drag bar to jump to any position in the document~~ ✅
- ~~Chapter navigation — jump between chapters if the document has them~~ ✅ (buttons, scrubber markers, [ ] keyboard shortcuts)
- Sentence context preview — show the surrounding sentence below the RSVP display
- Comprehension check — periodic quiz/recall prompts after sections
- Dark/light theme presets instead of individual color pickers
- Peripheral word preview — show the next/previous word faintly on either side

### Reading Stats
- ~~WPM history graph — track speed over time per document and overall~~ ✅
- ~~Reading time dashboard — daily/weekly/monthly reading time~~ ✅
- ~~Documents completed count and streak tracking~~ ✅
- ~~Words read per session summary~~ ✅

### Browse / Catalog
- Connect to additional public domain platforms (Open Library, arXiv, Standard Ebooks, LibriVox)
- Local catalog cache — store Gutenberg/external API results in our own DB so browsing is instant; run API calls in the background when a user searches, serve cached results immediately, and refresh the cache with fresh upstream data for the next page load
- Bookshelf curation — featured/staff-pick collections on the browse page

### Library Management
- Tags / folders for organization

### Mobile Support
- ~~Tap to play/pause~~ ✅
- ~~Swipe left/right to rewind/forward~~ ✅
- ~~Responsive layout for small screens~~ ✅
- ~~Full-screen reading mode~~ ✅

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
