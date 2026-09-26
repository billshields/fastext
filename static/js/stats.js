(() => {
    if (!api.isAuthenticated()) {
        window.location.href = '/';
        return;
    }

    gwfTheme.render(document.getElementById('theme-switcher'));

    function getThemeColors() {
        const style = getComputedStyle(document.documentElement);
        return {
            text: style.getPropertyValue('--text-color').trim(),
            border: style.getPropertyValue('--secondary-bg').trim(),
            ui: style.getPropertyValue('--ui-color').trim(),
            accent: style.getPropertyValue('--accent-color').trim(),
        };
    }

    function applyChartDefaults() {
        const c = getThemeColors();
        Chart.defaults.color = c.text;
        Chart.defaults.borderColor = c.border;
    }

    applyChartDefaults();

    let readingTimeChart = null;
    let wpmChart = null;

    // --- Helpers ---

    function formatTime(seconds) {
        if (seconds < 60) return seconds + 's';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return h + 'h ' + m + 'm';
        return m + 'm';
    }

    function formatNumber(n) {
        return n.toLocaleString();
    }

    // --- Overview ---

    async function loadOverview() {
        try {
            const data = await api.get('/api/stats/overview/');
            document.getElementById('stat-time').textContent = formatTime(data.total_reading_time);
            document.getElementById('stat-words').textContent = formatNumber(data.total_words_read);
            document.getElementById('stat-completed').textContent = data.documents_completed;
            document.getElementById('stat-streak').textContent = data.current_streak;

            const longestEl = document.getElementById('stat-longest-streak');
            if (data.longest_streak > 0) {
                longestEl.textContent = 'Longest: ' + data.longest_streak;
            }

            const todayEl = document.getElementById('today-summary');
            if (data.today_reading_time > 0) {
                todayEl.textContent = 'Today: ' + formatTime(data.today_reading_time) + ' read, ' + formatNumber(data.today_words_read) + ' words';
            } else {
                todayEl.textContent = 'No reading yet today.';
            }
        } catch (err) {
            console.error('Failed to load overview', err);
        }
    }

    // --- Reading Time Chart ---

    async function loadReadingTimeChart(period) {
        try {
            const data = await api.get('/api/stats/reading-time/?period=' + period);

            const labels = data.data.map(d => {
                const date = new Date(d.date + 'T00:00:00');
                if (period === 'year') {
                    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                }
                return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
            });
            const values = data.data.map(d => Math.round(d.reading_time / 60));

            if (readingTimeChart) {
                readingTimeChart.data.labels = labels;
                readingTimeChart.data.datasets[0].data = values;
                readingTimeChart.update();
            } else {
                const ctx = document.getElementById('reading-time-chart').getContext('2d');
                readingTimeChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Minutes',
                            data: values,
                            backgroundColor: getThemeColors().ui,
                            borderRadius: 4,
                        }],
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false },
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: { display: true, text: 'Minutes' },
                            },
                        },
                    },
                });
            }
        } catch (err) {
            console.error('Failed to load reading time chart', err);
        }
    }

    // Period toggle
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadReadingTimeChart(btn.dataset.period);
        });
    });

    // --- WPM Chart ---

    async function loadWpmChart(documentId) {
        try {
            let url = '/api/stats/wpm-history/';
            if (documentId) url += '?document_id=' + documentId;
            const data = await api.get(url);

            const labels = data.data.map(d => {
                const date = new Date(d.date + 'T00:00:00');
                return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            });
            const values = data.data.map(d => d.wpm);

            if (wpmChart) {
                wpmChart.data.labels = labels;
                wpmChart.data.datasets[0].data = values;
                wpmChart.update();
            } else {
                const ctx = document.getElementById('wpm-chart').getContext('2d');
                const accentColor = getThemeColors().accent;
                wpmChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'WPM',
                            data: values,
                            borderColor: accentColor,
                            backgroundColor: accentColor + '1a',
                            fill: true,
                            tension: 0.3,
                            pointRadius: 3,
                        }],
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false },
                        },
                        scales: {
                            y: {
                                beginAtZero: false,
                                title: { display: true, text: 'WPM' },
                            },
                        },
                    },
                });
            }
        } catch (err) {
            console.error('Failed to load WPM chart', err);
        }
    }

    document.getElementById('wpm-doc-filter').addEventListener('change', (e) => {
        loadWpmChart(e.target.value);
    });

    // --- Document Stats Table ---

    async function loadDocumentStats() {
        try {
            const data = await api.get('/api/stats/documents/');
            const container = document.getElementById('doc-stats-list');

            // Populate WPM chart filter dropdown
            const select = document.getElementById('wpm-doc-filter');
            data.forEach(doc => {
                const opt = document.createElement('option');
                opt.value = doc.document_id;
                opt.textContent = doc.title;
                select.appendChild(opt);
            });

            if (data.length === 0) {
                container.innerHTML = '<p class="loading-msg">No documents yet.</p>';
                return;
            }

            container.innerHTML = '';

            for (const doc of data) {
                const progress = Math.round(doc.progress * 100);
                const status = doc.completed_at ? 'Completed' : (doc.progress > 0 ? 'In progress' : 'Not started');
                const statusClass = doc.completed_at ? 'badge-completed' : 'badge-processing';

                const row = document.createElement('div');
                row.className = 'doc-stat-row';
                row.innerHTML = `
                    <div class="doc-stat-info">
                        <span class="doc-stat-title">${escapeHtml(doc.title)}</span>
                        <span class="badge ${statusClass}">${status}</span>
                    </div>
                    <div class="doc-stat-metrics">
                        <span class="doc-stat-metric">${formatNumber(doc.words_read)} / ${formatNumber(doc.total_words)} words</span>
                        <span class="doc-stat-metric">${formatTime(doc.reading_time)}</span>
                        <span class="doc-stat-metric">${doc.avg_wpm} WPM avg</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
                `;
                container.appendChild(row);
            }
        } catch (err) {
            console.error('Failed to load document stats', err);
        }
    }

    // --- Init ---

    loadOverview();
    loadReadingTimeChart('week');
    loadWpmChart('');
    loadDocumentStats();
})();
