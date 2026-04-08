// Reader page orchestration
(function () {
    if (!api.isAuthenticated()) {
        window.location.href = '/';
        return;
    }

    // Extract doc ID from URL: /read/123/
    const pathParts = window.location.pathname.split('/');
    const docId = parseInt(pathParts[2]);
    if (!docId) {
        window.location.href = '/library/';
        return;
    }

    let engine = null;
    let saveTimer = null;
    let lastSavedPos = 0;
    let sessionReadingTime = 0;
    let readingStartTime = null;
    let ttsController = null;
    let ttsEnabled = false;

    const elements = {
        before: document.getElementById('rsvp-before'),
        pivot: document.getElementById('rsvp-pivot'),
        after: document.getElementById('rsvp-after'),
        playPause: document.getElementById('btn-play-pause'),
        wpmSlider: document.getElementById('wpm-slider'),
        wpmLabel: document.getElementById('wpm-label'),
        title: document.getElementById('doc-title'),
        progress: document.getElementById('progress-indicator'),
        settingsPanel: document.getElementById('settings-panel'),
        helpOverlay: document.getElementById('help-overlay'),
        helpHint: document.getElementById('help-hint'),
    };

    // Initialize reader
    async function init() {
        try {
            const data = await api.get(`/api/documents/${docId}/read/`);
            const session = data.session;

            elements.title.textContent = session.document_title;
            elements.wpmSlider.value = session.wpm;

            engine = new RSVPEngine({
                displayEls: { before: elements.before, pivot: elements.pivot, after: elements.after },
                wpm: session.wpm,
                chunkSize: session.chunk_size,
                onPositionChange: onPositionChange,
                onNeedMoreWords: loadMoreWords,
                onFinished: onFinished,
            });

            engine.totalWords = session.total_words;
            engine.loadWords(data.words);
            engine.setPosition(session.current_position);
            lastSavedPos = session.current_position;

            if (window.speechSynthesis && typeof TTSController !== 'undefined') {
                ttsController = new TTSController({
                    onWordBoundary: (enginePos) => {
                        engine.displayWordAtPosition(enginePos);
                    },
                    onBatchEnd: () => {
                        const nextPos = engine.currentPos + 1;
                        if (nextPos < engine.totalWords) {
                            speakFromPosition(nextPos);
                        } else {
                            onFinished();
                        }
                    },
                    onError: (error) => {
                        console.warn('TTS error:', error);
                        ttsEnabled = false;
                        document.getElementById('set-tts-enabled').checked = false;
                    },
                });
            }

            updateProgress();
            await loadPreferences();
            initHelpHint();
        } catch (err) {
            elements.before.textContent = '';
            elements.pivot.textContent = 'Error loading document';
            elements.after.textContent = '';
        }
    }

    async function loadPreferences() {
        try {
            const prefs = await api.get('/api/auth/preferences/');
            applyPreferences(prefs);

            // Set settings panel values
            document.getElementById('set-bg-color').value = prefs.background_color;
            document.getElementById('set-text-color').value = prefs.text_color;
            document.getElementById('set-ui-color').value = prefs.ui_color;
            document.getElementById('set-font').value = prefs.font_family;
            document.getElementById('set-font-size').value = prefs.font_size;
            document.getElementById('font-size-label').textContent = prefs.font_size + 'px';
            document.getElementById('set-chunk-size').value = prefs.chunk_size;

            const pivotEl = document.getElementById('set-pivot-highlight');
            const focusEl = document.getElementById('set-focus-line');
            const sentenceEl = document.getElementById('set-sentence-pause');
            const longWordEl = document.getElementById('set-long-word-pause');
            pivotEl.checked = !!prefs.pivot_highlight;
            focusEl.checked = !!prefs.focus_line;
            sentenceEl.checked = !!prefs.sentence_pause;
            longWordEl.checked = !!prefs.long_word_pause;
            applyPivotHighlight(prefs.pivot_highlight);
            applyFocusLine(prefs.focus_line);
            if (engine) {
                engine.sentencePause = !!prefs.sentence_pause;
                engine.longWordPause = !!prefs.long_word_pause;
            }

            // TTS settings
            ttsEnabled = !!prefs.tts_enabled;
            document.getElementById('set-tts-enabled').checked = ttsEnabled;
            updateSpeedLabel(parseInt(elements.wpmSlider.value));
            if (ttsController) {
                ttsController.getVoices().then(voices => {
                    populateVoiceSelect(voices, prefs.tts_voice || '');
                    if (prefs.tts_voice) ttsController.setVoice(prefs.tts_voice);
                });
            }
        } catch (err) {
            // Use defaults
        }
    }

    function applyPivotHighlight(enabled) {
        elements.pivot.classList.toggle('highlight', !!enabled);
    }

    function applyFocusLine(enabled) {
        document.querySelector('.rsvp-focus-line').classList.toggle('visible', !!enabled);
    }

    function applyPreferences(prefs) {
        const root = document.documentElement;
        root.style.setProperty('--bg-color', prefs.background_color);
        root.style.setProperty('--text-color', prefs.text_color);
        root.style.setProperty('--ui-color', prefs.ui_color);
        root.style.setProperty('--font-family', prefs.font_family);
        root.style.setProperty('--font-size', prefs.font_size + 'px');
    }

    function onPositionChange(position) {
        updateProgress();
        scheduleProgressSave(position);
    }

    function updateProgress() {
        if (!engine) return;
        const pct = engine.totalWords > 0
            ? Math.round((engine.currentPos / engine.totalWords) * 100)
            : 0;
        elements.progress.textContent = pct + '%';
    }

    function onFinished() {
        if (ttsController) ttsController.stop();
        ttsPlaying = false;
        elements.playPause.innerHTML = '&#9654;';
        elements.playPause.classList.add('btn-play');
        immediateSave(engine.currentPos);
    }

    function speakFromPosition(pos) {
        if (!ttsController) return;
        const batchSize = ttsController.getBatchSize();
        const words = engine.getWordsFromPosition(pos, batchSize);
        if (words.length === 0) {
            onFinished();
            return;
        }
        ttsController.speak(words, pos);
    }

    let ttsPlaying = false;

    function isPlaying() {
        return engine.playing || ttsPlaying;
    }

    async function loadMoreWords(startPos) {
        try {
            const data = await api.get(`/api/documents/${docId}/words/?start=${startPos}&count=500`);
            engine.loadWords(data.words);
        } catch (err) {
            // Will retry on next prefetch check
        }
    }

    // Progress saving
    let pendingPosition = null;
    function scheduleProgressSave(position) {
        pendingPosition = position;
        if (saveTimer) return;
        saveTimer = setTimeout(() => {
            saveTimer = null;
            if (pendingPosition !== lastSavedPos) {
                doSave(pendingPosition);
            }
        }, 5000);
    }

    function immediateSave(position) {
        if (saveTimer) {
            clearTimeout(saveTimer);
            saveTimer = null;
        }
        doSave(position);
    }

    async function doSave(position) {
        const readingTime = readingStartTime
            ? Math.round((Date.now() - readingStartTime) / 1000)
            : 0;
        try {
            await api.post(`/api/documents/${docId}/progress/`, {
                position: position,
                reading_time: readingTime,
            });
            lastSavedPos = position;
            if (readingStartTime) {
                sessionReadingTime += readingTime;
                readingStartTime = Date.now();
            }
        } catch (err) {
            // Silent fail, will retry
        }
    }

    // Controls
    elements.playPause.addEventListener('click', () => {
        if (!engine) return;
        if (isPlaying()) {
            // PAUSE
            if (ttsEnabled && ttsController) {
                ttsController.stop();
                ttsPlaying = false;
            } else {
                engine.pause();
            }
            elements.playPause.innerHTML = '&#9654;';
            elements.playPause.classList.add('btn-play');
            immediateSave(engine.currentPos);
            readingStartTime = null;
        } else {
            // PLAY
            if (ttsEnabled && ttsController) {
                ttsController.setRate(engine.wpm);
                speakFromPosition(engine.currentPos);
                ttsPlaying = true;
            } else {
                engine.play();
            }
            elements.playPause.innerHTML = '&#9646;&#9646;';
            elements.playPause.classList.remove('btn-play');
            readingStartTime = Date.now();
        }
    });

    document.getElementById('btn-rewind').addEventListener('click', () => {
        if (!engine) return;
        const wasPlaying = isPlaying();
        if (ttsEnabled && ttsController) ttsController.stop();
        engine.rewind(engine.chunkSize * 10);
        if (wasPlaying && ttsEnabled && ttsController) speakFromPosition(engine.currentPos);
    });

    document.getElementById('btn-forward').addEventListener('click', () => {
        if (!engine) return;
        const wasPlaying = isPlaying();
        if (ttsEnabled && ttsController) ttsController.stop();
        engine.forward(engine.chunkSize * 10);
        if (wasPlaying && ttsEnabled && ttsController) speakFromPosition(engine.currentPos);
    });

    // Custom drag for WPM slider — tracks cursor even when drifting vertically
    (function () {
        const slider = elements.wpmSlider;
        const min = +slider.min, max = +slider.max, step = +slider.step;
        let dragging = false;

        function valueFromX(clientX) {
            const rect = slider.getBoundingClientRect();
            const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            const raw = min + ratio * (max - min);
            return Math.round(raw / step) * step;
        }

        slider.addEventListener('pointerdown', (e) => {
            dragging = true;
            slider.value = valueFromX(e.clientX);
            slider.dispatchEvent(new Event('input'));
            e.preventDefault();
        });

        document.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            slider.value = valueFromX(e.clientX);
            slider.dispatchEvent(new Event('input'));
        });

        document.addEventListener('pointerup', () => {
            dragging = false;
        });
    })();

    elements.wpmSlider.addEventListener('input', (e) => {
        const wpm = parseInt(e.target.value);
        updateSpeedLabel(wpm);
        if (engine) engine.wpm = wpm;
        if (ttsController) ttsController.setRate(wpm);
        api.patch(`/api/documents/${docId}/session/`, { wpm }).catch(() => {});
    });

    function updateSpeedLabel(wpm) {
        elements.wpmLabel.textContent = `${wpm} WPM`;
        const ttsCap = document.getElementById('tts-speed-cap');
        if (ttsCap) {
            ttsCap.hidden = !(ttsEnabled && wpm > 700);
        }
    }

    // Settings panel
    document.getElementById('btn-settings').addEventListener('click', () => {
        elements.settingsPanel.hidden = !elements.settingsPanel.hidden;
    });

    document.getElementById('btn-close-settings').addEventListener('click', () => {
        elements.settingsPanel.hidden = true;
    });

    // Settings change handlers
    const settingsInputs = ['set-bg-color', 'set-text-color', 'set-ui-color'];
    settingsInputs.forEach(id => {
        document.getElementById(id).addEventListener('input', debounce(saveAndApplyPrefs, 300));
    });

    document.getElementById('set-font').addEventListener('change', saveAndApplyPrefs);

    document.getElementById('set-font-size').addEventListener('input', (e) => {
        document.getElementById('font-size-label').textContent = e.target.value + 'px';
        debounce(saveAndApplyPrefs, 300)();
    });

    document.getElementById('set-chunk-size').addEventListener('change', (e) => {
        const chunkSize = parseInt(e.target.value);
        if (engine) engine.chunkSize = chunkSize;
        api.patch(`/api/documents/${docId}/session/`, { chunk_size: chunkSize }).catch(() => {});
        saveAndApplyPrefs();
    });

    document.getElementById('set-pivot-highlight').addEventListener('change', (e) => {
        applyPivotHighlight(e.target.checked);
        saveAndApplyPrefs();
    });

    document.getElementById('set-focus-line').addEventListener('change', (e) => {
        applyFocusLine(e.target.checked);
        saveAndApplyPrefs();
    });

    document.getElementById('set-sentence-pause').addEventListener('change', (e) => {
        if (engine) engine.sentencePause = e.target.checked;
        saveAndApplyPrefs();
    });

    document.getElementById('set-long-word-pause').addEventListener('change', (e) => {
        if (engine) engine.longWordPause = e.target.checked;
        saveAndApplyPrefs();
    });

    document.getElementById('set-tts-enabled').addEventListener('change', (e) => {
        ttsEnabled = e.target.checked;
        updateSpeedLabel(parseInt(elements.wpmSlider.value));
        if (ttsEnabled && engine.playing) {
            engine.pause();
            if (ttsController) {
                ttsController.setRate(engine.wpm);
                speakFromPosition(engine.currentPos);
                ttsPlaying = true;
            }
        }
        if (!ttsEnabled && ttsPlaying && ttsController) {
            ttsController.stop();
            ttsPlaying = false;
            engine.play();
        }
        saveAndApplyPrefs();
    });

    document.getElementById('set-tts-voice').addEventListener('change', (e) => {
        if (ttsController) ttsController.setVoice(e.target.value);
        saveAndApplyPrefs();
    });

    function saveAndApplyPrefs() {
        const prefs = {
            background_color: document.getElementById('set-bg-color').value,
            text_color: document.getElementById('set-text-color').value,
            ui_color: document.getElementById('set-ui-color').value,
            font_family: document.getElementById('set-font').value,
            font_size: parseInt(document.getElementById('set-font-size').value),
            chunk_size: parseInt(document.getElementById('set-chunk-size').value),
            pivot_highlight: document.getElementById('set-pivot-highlight').checked,
            focus_line: document.getElementById('set-focus-line').checked,
            sentence_pause: document.getElementById('set-sentence-pause').checked,
            long_word_pause: document.getElementById('set-long-word-pause').checked,
            tts_enabled: document.getElementById('set-tts-enabled').checked,
            tts_voice: document.getElementById('set-tts-voice').value,
        };
        applyPreferences(prefs);
        api.patch('/api/auth/preferences/', prefs).catch(() => {});
    }

    function populateVoiceSelect(voices, selectedName) {
        const select = document.getElementById('set-tts-voice');
        select.innerHTML = '';
        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.name;
            opt.textContent = `${v.name} (${v.lang})`;
            if (v.name === selectedName) opt.selected = true;
            select.appendChild(opt);
        });
    }

    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    // Help overlay
    let helpVisible = false;
    let wasPlayingBeforeHelp = false;

    function showHelp() {
        wasPlayingBeforeHelp = engine && isPlaying();
        if (wasPlayingBeforeHelp) {
            elements.playPause.click(); // pause via existing logic
        }
        elements.helpOverlay.hidden = false;
        helpVisible = true;
        dismissHelpHint();
    }

    function hideHelp() {
        elements.helpOverlay.hidden = true;
        helpVisible = false;
    }

    function toggleHelp() {
        helpVisible ? hideHelp() : showHelp();
    }

    function dismissHelpHint() {
        if (elements.helpHint) {
            elements.helpHint.classList.add('hidden');
            localStorage.setItem('speedreader_help_seen', '1');
        }
    }

    function initHelpHint() {
        if (localStorage.getItem('speedreader_help_seen')) {
            if (elements.helpHint) elements.helpHint.classList.add('hidden');
        }
    }

    document.getElementById('btn-help').addEventListener('click', toggleHelp);
    elements.helpOverlay.querySelector('.help-overlay-backdrop').addEventListener('click', hideHelp);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

        if (e.key === '?') {
            e.preventDefault();
            toggleHelp();
            return;
        }

        if (e.code === 'Escape') {
            if (helpVisible) {
                e.preventDefault();
                hideHelp();
            }
            return;
        }

        if (helpVisible) return;

        switch (e.code) {
            case 'Space':
                e.preventDefault();
                elements.playPause.click();
                break;
            case 'ArrowLeft':
                if (engine) {
                    const wasPlayingL = isPlaying();
                    if (ttsEnabled && ttsController) ttsController.stop();
                    engine.rewind(engine.chunkSize);
                    if (wasPlayingL && ttsEnabled && ttsController) speakFromPosition(engine.currentPos);
                }
                break;
            case 'ArrowRight':
                if (engine) {
                    const wasPlayingR = isPlaying();
                    if (ttsEnabled && ttsController) ttsController.stop();
                    engine.forward(engine.chunkSize);
                    if (wasPlayingR && ttsEnabled && ttsController) speakFromPosition(engine.currentPos);
                }
                break;
            case 'ArrowUp':
                elements.wpmSlider.value = Math.min(1000, parseInt(elements.wpmSlider.value) + 25);
                elements.wpmSlider.dispatchEvent(new Event('input'));
                break;
            case 'ArrowDown':
                elements.wpmSlider.value = Math.max(100, parseInt(elements.wpmSlider.value) - 25);
                elements.wpmSlider.dispatchEvent(new Event('input'));
                break;
        }
    });

    // Save on page close
    window.addEventListener('beforeunload', () => {
        if (ttsController) ttsController.stop();
        if (engine) {
            api.beacon(`/api/documents/${docId}/progress/`, {
                position: engine.currentPos,
                reading_time: readingStartTime ? Math.round((Date.now() - readingStartTime) / 1000) : 0,
            });
        }
    });

    init();
})();
