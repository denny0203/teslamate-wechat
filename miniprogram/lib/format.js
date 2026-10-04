const { addressLabel } = require('./address');
const DAY = 86400000;
const pad = n => String(n).padStart(2, '0');
function chinaParts(value) {
  const date = new Date(new Date(value).getTime() + 8 * 3600000);
  return {
    day: `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`,
    time: `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`
  };
}
function windowStart(now = Date.now()) {
  // 北京时间今天及前六天，截止当前时刻。
  return new Date(Math.floor((now + 8 * 3600000) / DAY) * DAY - 8 * 3600000 - 6 * DAY).toISOString();
}
function present(rows) {
  const groups = [];
  let distance = 0;
  let missingDistance = 0;
  for (const row of rows) {
    const start = chinaParts(row.started_at);
    const end = row.ended_at ? chinaParts(row.ended_at) : null;
    const km = row.distance_km == null ? null : Number(row.distance_km);
    if (km == null || !Number.isFinite(km)) missingDistance += 1;
    else distance += km;
    const minutes = end ? Math.max(0, Math.floor((new Date(row.ended_at) - new Date(row.started_at)) / 60000)) : null;
    let group = groups[groups.length - 1];
    if (!group || group.day !== start.day) { group = { day: start.day, rows: [] }; groups.push(group); }
    group.rows.push({
      id: row.id, time: start.time + ' → ' + (end ? (end.day === start.day ? '' : end.day.slice(5) + ' ') + end.time : '未结束'),
      start: addressLabel(row.start_address, true, '起点未记录'), end: addressLabel(row.end_address, true, '终点未记录'),
      distance: km == null || !Number.isFinite(km) ? '里程未记录' : `${km.toFixed(1)} 公里`,
      duration: minutes == null ? '时长未记录' : `${minutes} 分钟`
    });
  }
  return { groups, total: rows.length, distance: distance.toFixed(1), missingDistance };
}
module.exports = { chinaParts, windowStart, present };
