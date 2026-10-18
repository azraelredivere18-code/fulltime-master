const assert = require('node:assert/strict');
const metrics = require('../gui/templates/static/js/record_metrics.js');

const rows = [
    {submit: '是', source: 'BOSS直聘', create_time: '2026-10-10 09:00:00',
        submit_time: '2026-10-17T10:00:00', match_degree: '70%'},
    {submit: '是', source: '前程无忧', create_time: '2026-10-17 09:00:00',
        submit_time: '2026-10-17T11:00:00', match_degree: ''},
    {submit: '否', source: '智联招聘', create_time: '2026-10-17 09:00:00',
        remarks: '投递需要人工确认；未记录为成功'},
    {submit: '是', source: 'BOSS直聘', create_time: '2026-10-16 09:00:00',
        match_degree: '0%'},
];

assert.equal(metrics.submittedDay(rows[0]), '2026-10-17');
assert.equal(metrics.submittedDay(rows[2]), '');
assert.equal(metrics.dailyTrend(rows, '2026-10-17').counts.at(-1), 2);
assert.deepEqual(metrics.platformCounts(rows, '2026-10-17'),
    {'BOSS直聘': 1, '前程无忧': 1});
assert.deepEqual(metrics.matchDegreeCounts(rows, '2026-10-17'), {'70%-80%': 1});
assert.equal(metrics.filterByDate(rows, '2026-10-17', '2026-10-17').length, 3);
console.log('record metrics: OK');
