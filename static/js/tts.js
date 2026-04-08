class TTSController {
    constructor({ onWordBoundary, onBatchEnd, onError }) {
        this.onWordBoundary = onWordBoundary;
        this.onBatchEnd = onBatchEnd;
        this.onError = onError;
        this.enabled = false;
        this.voice = null;
        this.voiceName = '';
        this.rate = 1.0;
        this.speaking = false;
        this._utterance = null;
        this._wordOffsets = [];
    }

    isSupported() {
        return !!window.speechSynthesis;
    }

    getVoices() {
        return new Promise((resolve) => {
            const voices = speechSynthesis.getVoices();
            if (voices.length > 0) {
                resolve(voices);
                return;
            }
            speechSynthesis.onvoiceschanged = () => {
                resolve(speechSynthesis.getVoices());
            };
        });
    }

    setVoice(voiceName) {
        this.voiceName = voiceName;
        const voices = speechSynthesis.getVoices();
        this.voice = voices.find(v => v.name === voiceName) || null;
    }

    setRate(wpm) {
        this.rate = Math.max(0.5, Math.min(4.0, wpm / 160));
    }

    getBatchSize() {
        return Math.max(20, Math.floor(75 * this.rate));
    }

    speak(words, startPos) {
        this.stop();

        this._wordOffsets = [];
        let charPos = 0;
        words.forEach((w, i) => {
            this._wordOffsets.push({
                charStart: charPos,
                charEnd: charPos + w.word.length,
                enginePos: startPos + i,
            });
            charPos += w.word.length + 1;
        });

        const batchText = words.map(w => w.word).join(' ');

        const utterance = new SpeechSynthesisUtterance(batchText);
        utterance.rate = this.rate;
        if (this.voice) utterance.voice = this.voice;

        utterance.onboundary = (event) => {
            if (event.name !== 'word') return;
            const charIdx = event.charIndex;
            const wordInfo = this._wordOffsets.find(
                w => charIdx >= w.charStart && charIdx < w.charEnd
            );
            if (wordInfo) {
                this.onWordBoundary(wordInfo.enginePos);
            }
        };

        utterance.onend = () => {
            if (!this.speaking) return; // canceled, not a natural end
            this.speaking = false;
            this.onBatchEnd();
        };

        utterance.onerror = (event) => {
            if (event.error === 'canceled' || event.error === 'interrupted' || !this.speaking) return;
            this.speaking = false;
            this.onError(event.error);
        };

        this._utterance = utterance;
        this.speaking = true;
        speechSynthesis.speak(utterance);
    }

    pause() {
        speechSynthesis.cancel();
        this.speaking = false;
        this._utterance = null;
    }

    resume() {
        // Not used — pause() cancels, so play always restarts via speak()
    }

    stop() {
        speechSynthesis.cancel();
        this.speaking = false;
        this._utterance = null;
    }
}
