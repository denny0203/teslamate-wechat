const assert = require('node:assert/strict');
const test = require('node:test');
const { windowStart, chinaParts, present } = require('../miniprogram/lib/format');
test('北京时间的七个自然日跨月，截止今天', () => {
  assert.equal(windowStart(Date.parse('2026-10-02T08:00:00Z')), '2026-09-25T16:00:00.000Z');
  assert.equal(windowStart(Date.parse('2026-10-01T16:00:00Z')), '2026-09-25T16:00:00.000Z');
  assert.equal(windowStart(Date.parse('2026-10-01T15:59:59Z')), '2026-09-24T16:00:00.000Z');
});
test('显示不依赖手机时区', () => {
  assert.deepEqual(chinaParts('2026-10-01T16:05:00Z'), {day:'2026-10-02',time:'00:05'});
});
test('未知里程、地址、未结束行程不伪装为零', () => {
  const result = present([{ id: 3, started_at:'2026-10-02T01:00:00Z', ended_at:null, distance_km:null },
    { id:2, started_at:'2026-10-01T15:50:00Z', ended_at:'2026-10-01T16:10:00Z', distance_km:12.34 }]);
  assert.equal(result.total, 2); assert.equal(result.distance, '12.3'); assert.equal(result.missingDistance, 1);
  assert.equal(result.groups.length, 2);
  assert.equal(result.groups[0].rows[0].distance, '里程未记录');
  assert.equal(result.groups[0].rows[0].start, '起点未记录');
  assert.equal(result.groups[1].rows[0].time, '23:50 → 10-02 00:10');
  assert.equal(result.groups[1].rows[0].duration, '20 分钟');
});
test('列表和详情均按完整分钟显示，不把23分50秒取成24分钟', () => {
  const r = present([{id:1,started_at:'2026-10-02T00:00:00Z',ended_at:'2026-10-02T00:23:50Z',distance_km:7.4}]);
  assert.equal(r.groups[0].rows[0].duration,'23 分钟');
});
