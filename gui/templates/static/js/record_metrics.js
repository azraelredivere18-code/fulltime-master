(function (root, factory) {
    const metrics = factory();
    if (typeof module === 'object' && module.exports) module.exports = metrics;
    else root.RecordMetrics = metrics;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    function day(value) {
        const text = String(value || '');
        return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : '';
    }
    function submittedDay(row) {
        if (!row || row.submit !== '是') return '';
        return day(row.submit_time) || day(row.create_time);
    }
    function filterByDate(rows, start, end) {
        if (!start || !end) return rows.slice();
        return rows.filter(row => {
            const recordDay = submittedDay(row) || day(row.create_time);
            return recordDay >= start && recordDay <= end;
        });
    }
    function dailyTrend(rows, today) {
        const labels = [], counts = [];
        const base = new Date(Number(today.slice(0, 4)), Number(today.slice(5, 7)) - 1,
            Number(today.slice(8, 10)));
        for (let offset = 6; offset >= 0; offset--) {
            const date = new Date(base);
            date.setDate(base.getDate() - offset);
            const label = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'),
                String(date.getDate()).padStart(2, '0')].join('-');
            labels.push(label);
            counts.push(rows.filter(row => submittedDay(row) === label).length);
        }
        return {labels, counts};
    }
    function platformCounts(rows, today) {
        const result = {};
        rows.forEach(row => {
            if (submittedDay(row) !== today || !row.source) return;
            result[row.source] = (result[row.source] || 0) + 1;
        });
        return result;
    }
    function matchDegreeCounts(rows, today) {
        const result = {};
        rows.forEach(row => {
            if (submittedDay(row) !== today || row.match_degree === '' ||
                row.match_degree === null || row.match_degree === undefined) return;
            const degree = Number(String(row.match_degree).replace('%', ''));
            if (!Number.isFinite(degree) || degree < 0 || degree > 100) return;
            const start = Math.min(90, Math.floor(degree / 10) * 10);
            const label = start + '%-' + (start + 10) + '%';
            result[label] = (result[label] || 0) + 1;
        });
        return result;
    }
    return {submittedDay, filterByDate, dailyTrend, platformCounts, matchDegreeCounts};
});
