import re

import pdfplumber
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]?$')


def extract_pdf(file_path):
    """Yields (chapter_index, paragraph_index, word, sentence_end) tuples."""
    with pdfplumber.open(file_path) as pdf:
        para_idx = 0
        for page in pdf.pages:
            text = page.extract_text() or ''
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                words = para.split()
                for word in words:
                    se = bool(SENTENCE_END_RE.search(word))
                    yield (0, para_idx, word, se)
                para_idx += 1


def extract_epub(file_path):
    """Yields (chapter_index, paragraph_index, word, sentence_end) tuples."""
    book = epub.read_epub(file_path)
    chapter_idx = 0
    para_idx = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        if soup.find('nav') and not soup.find('p'):
            continue
        has_content = False
        for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4']):
            text = tag.get_text(strip=True)
            if not text:
                continue
            has_content = True
            words = text.split()
            for word in words:
                se = bool(SENTENCE_END_RE.search(word))
                yield (chapter_idx, para_idx, word, se)
            para_idx += 1
        if has_content:
            chapter_idx += 1
