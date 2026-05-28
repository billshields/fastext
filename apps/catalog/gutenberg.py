import re

import requests

GUTENDEX_URL = 'https://gutendex.com/books/'
GUTENBERG_TEXT_URL = 'https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt'
GUTENBERG_TEXT_FALLBACK_URL = 'https://www.gutenberg.org/files/{id}/{id}-0.txt'

START_MARKER = re.compile(r'\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG', re.IGNORECASE)
END_MARKER = re.compile(r'\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG', re.IGNORECASE)

CHAPTER_RE = re.compile(
    r'^(?:CHAPTER|Chapter|BOOK|Book|PART|Part)\s+[IVXLCDM\d]+',
    re.MULTILINE,
)

SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]?$')


VALID_SORTS = {'popular', 'ascending', 'descending'}


def search_gutenberg(query='', page=1, sort='popular', topic=''):
    params = {'languages': 'en', 'page': page}
    if query:
        params['search'] = query
    if sort and sort in VALID_SORTS and sort != 'popular':
        params['sort'] = sort
    if topic:
        params['topic'] = topic

    import time
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(GUTENDEX_URL, params=params, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            last_exc = e
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
    else:
        raise last_exc
    data = resp.json()

    results = []
    for book in data.get('results', []):
        authors = book.get('authors', [])
        author = authors[0]['name'] if authors else ''
        subjects = book.get('subjects', [])

        formats = book.get('formats', {})
        cover_url = formats.get('image/jpeg', '')

        results.append({
            'gutenberg_id': book['id'],
            'title': book.get('title', ''),
            'author': author,
            'language': 'en',
            'subjects': subjects[:5],
            'cover_url': cover_url,
            'download_count': book.get('download_count', 0),
        })

    return {
        'count': data.get('count', 0),
        'next': data.get('next'),
        'previous': data.get('previous'),
        'results': results,
    }


def download_gutenberg_text(gutenberg_id):
    url = GUTENBERG_TEXT_URL.format(id=gutenberg_id)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException:
        url = GUTENBERG_TEXT_FALLBACK_URL.format(id=gutenberg_id)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

    # Handle encoding
    resp.encoding = resp.apparent_encoding or 'utf-8'
    return resp.text


def strip_gutenberg_boilerplate(text):
    start_match = START_MARKER.search(text)
    if start_match:
        after_marker = text[start_match.end():]
        newline_pos = after_marker.find('\n')
        if newline_pos != -1:
            text = after_marker[newline_pos + 1:]

    end_match = END_MARKER.search(text)
    if end_match:
        text = text[:end_match.start()]

    return text.strip()


def parse_and_chunk(text):
    paragraphs = re.split(r'\n\s*\n', text)
    chapter_idx = 0
    para_idx = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if CHAPTER_RE.match(paragraph):
            chapter_idx += 1

        words = paragraph.split()
        for word in words:
            sentence_end = bool(SENTENCE_END_RE.search(word))
            yield (word, chapter_idx, para_idx, sentence_end)

        para_idx += 1
