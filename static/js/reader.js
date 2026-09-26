class RSVPEngine {
    constructor({ displayEls, wpm, chunkSize, onPositionChange, onNeedMoreWords, onFinished }) {
        this.beforeEl = displayEls.before;
        this.pivotEl = displayEls.pivot;
        this.afterEl = displayEls.after;
        this.words = new Map();
        this.wpm = wpm;
        this.chunkSize = chunkSize;
        this.currentPos = 0;
        this.totalWords = 0;
        this.playing = false;
        this.timerId = null;
        this.onPositionChange = onPositionChange;
        this.onNeedMoreWords = onNeedMoreWords;
        this.onFinished = onFinished;
        this.sentencePause = false;
        this.longWordPause = false;
        this._prefetchRequested = new Set();
    }

    get msPerWord() {
        return 60000 / this.wpm;
    }

    loadWords(wordList) {
        wordList.forEach(w => {
            this.words.set(w.pos, { word: w.word, se: w.se });
        });
    }

    setPosition(pos) {
        this.currentPos = pos;
        this._displayCurrentWord();
    }

    play() {
        if (this.playing) return;
        this.playing = true;
        this._tick();
    }

    pause() {
        this.playing = false;
        if (this.timerId) {
            clearTimeout(this.timerId);
            this.timerId = null;
        }
    }

    rewind(count = 10) {
        this.currentPos = Math.max(0, this.currentPos - count);
        this._displayCurrentWord();
        this._checkPrefetch();
        this.onPositionChange(this.currentPos);
    }

    forward(count = 10) {
        this.currentPos = Math.min(this.totalWords - 1, this.currentPos + count);
        this._displayCurrentWord();
        this._checkPrefetch();
        this.onPositionChange(this.currentPos);
    }

    _tick() {
        if (!this.playing) return;

        if (this.currentPos >= this.totalWords) {
            this.pause();
            if (this.onFinished) this.onFinished();
            return;
        }

        const chunk = this._getChunk();
        if (!chunk) {
            // Words haven't arrived yet — wait for the prefetch instead of stopping
            this._checkPrefetch();
            this.timerId = setTimeout(() => this._tick(), 100);
            return;
        }

        this._displayWord(chunk.text);
        this.onPositionChange(this.currentPos);

        let delay = this.msPerWord * this.chunkSize;

        if (this.sentencePause && chunk.sentenceEnd) {
            delay *= 1.5;
        }

        if (this.longWordPause && chunk.text.length > 8) {
            delay += (chunk.text.length - 8) * 20;
        }

        this._checkPrefetch();

        this.timerId = setTimeout(() => {
            this.currentPos += this.chunkSize;
            this._tick();
        }, delay);
    }

    _getChunk() {
        return this._getChunkAt(this.currentPos);
    }

    _displayCurrentWord() {
        const chunk = this._getChunk();
        if (chunk) {
            this._displayWord(chunk.text);
        }
    }

    _displayWord(text) {
        // Calculate ORP (optimal recognition point) at roughly 1/3 of word
        const pivotIdx = Math.max(0, Math.floor(text.length / 3) - 1);
        this.beforeEl.textContent = text.substring(0, pivotIdx);
        this.pivotEl.textContent = text[pivotIdx] || '';
        this.afterEl.textContent = text.substring(pivotIdx + 1);
    }

    _checkPrefetch() {
        // Fetch when there's a missing word within 100 positions either side.
        // Scanning the neighbourhood (rather than the min/max of everything
        // loaded) also fills gaps left behind by scrubber jumps.
        const ahead = Math.min(this.totalWords, this.currentPos + 100);
        for (let pos = this.currentPos; pos < ahead; pos++) {
            if (!this.words.has(pos)) {
                this._requestWords(pos);
                break;
            }
        }

        const behind = Math.max(0, this.currentPos - 100);
        for (let pos = this.currentPos - 1; pos >= behind; pos--) {
            if (!this.words.has(pos)) {
                this._requestWords(Math.max(0, pos - 499));
                break;
            }
        }
    }

    _requestWords(start) {
        if (this._prefetchRequested.has(start)) return;
        this._prefetchRequested.add(start);
        // Only dedupe while in flight, so a failed fetch is retried on a later check
        Promise.resolve(this.onNeedMoreWords(start))
            .finally(() => this._prefetchRequested.delete(start));
    }

    displayWordAtPosition(pos) {
        // Snap to chunk boundary and display full chunk
        const chunkStart = pos - (pos % this.chunkSize);
        const chunk = this._getChunkAt(chunkStart);
        if (!chunk) return;
        this.currentPos = chunkStart;
        this._displayWord(chunk.text);
        this.onPositionChange(this.currentPos);
        this._checkPrefetch();
    }

    _getChunkAt(pos) {
        // The last chunk of a document may be shorter than chunkSize
        const end = Math.min(pos + this.chunkSize, this.totalWords);
        const words = [];
        for (let p = pos; p < end; p++) {
            const w = this.words.get(p);
            if (!w) return null;
            words.push(w);
        }
        if (words.length === 0) return null;
        return {
            text: words.map(w => w.word).join(' '),
            sentenceEnd: words[words.length - 1].se,
        };
    }

    getWordsFromPosition(pos, count) {
        const result = [];
        for (let i = 0; i < count; i++) {
            const w = this.words.get(pos + i);
            if (!w) break;
            result.push({ word: w.word, se: w.se, pos: pos + i });
        }
        return result;
    }
}
