const { addressLabel } = require('./address');
const { chinaParts } = require('./format');
function value(n, min, max) {
  if (n == null || n === '' || typeof n === 'boolean') return null;
  const v = Number(n);
  return Number.isFinite(v) && (min == null || v >= min) && (max == null || v <= max) ? v : null;
}
function unit(n, text, digits = 0, min, max) {
  const v = value(n, min, max);
  return v == null ? '未记录' : `${v.toFixed(digits)} ${text}`;
}
function validTime(v) { return v && Number.isFinite(new Date(v).getTime()); }
function point(p) {
  return p && value(p.latitude, -90, 90) != null && value(p.longitude, -180, 180) != null && !(Number(p.latitude) === 0 && Number(p.longitude) === 0);
}
function presentation(detail) {
  const row = detail.summary || {};
  const start = validTime(row.started_at) ? chinaParts(row.started_at) : null;
  const end = validTime(row.ended_at) ? chinaParts(row.ended_at) : null;
  let seconds = start && end ? (new Date(row.ended_at)-new Date(row.started_at))/1000 : null;
  const durationInvalid = row.duration_invalid || (seconds != null && seconds < 0);
  const duration = durationInvalid ? '数据异常' : seconds == null ? '未记录' : seconds < 60 ? '不足1分钟' : seconds < 3600 ? `${Math.floor(seconds/60)}分钟` : `${Math.floor(seconds/3600)}小时${Math.floor(seconds%3600/60)}分`;
  const km = value(row.distance_km, 0);
  const average = seconds > 0 && km != null ? km/seconds*3600 : null;
  const rangeStart = value(row.start_range_km, 0), rangeEnd = value(row.end_range_km, 0);
  const rangeDiff = rangeStart == null || rangeEnd == null ? '变化未记录' : `${rangeEnd > rangeStart ? '增加' : '减少'} ${Math.abs(rangeStart-rangeEnd).toFixed(0)} km`;
  return { day: start ? start.day : '日期未记录', dayTitle: start ? `${Number(start.day.slice(5,7))}月${Number(start.day.slice(8))}日` : '本日',
    start: addressLabel(row.start_address, false, '起点未记录'), end: addressLabel(row.end_address, false, '终点未记录'),
    fullStart: row.start_address || '起点未记录', fullEnd: row.end_address || '终点未记录',
    time: start ? `${start.time} – ${end ? (end.day === start.day ? '' : end.day+' ')+end.time : '尚未结束'}` : '时间未记录',
    rangeSummary: rangeStart == null || rangeEnd == null ? '未记录' : `${rangeEnd > rangeStart ? '增加' : ''}${Math.abs(rangeStart-rangeEnd).toFixed(0)}km (${rangeStart.toFixed(0)}–${rangeEnd.toFixed(0)})`,
    energyUsed: unit(row.energy_used_kwh,'度',1,0), averageConsumption: unit(row.average_consumption_wh_km,'Wh/km',0,0),
    maximumSpeedNumber: value(row.speed_max,0) == null ? '未记录' : value(row.speed_max,0).toFixed(0),
    maximumSpeed: unit(row.speed_max,'km/h',0,0), averageSpeed: unit(average,'km/h'),
    outsideTemperature: unit(row.outside_temp_avg,'℃',1), insideTemperature: unit(row.inside_temp_avg,'℃',1),
    distance: km == null ? '未记录' : km.toFixed(1), duration,
    metrics: [{ title:'电量与续航', rows:[{label:'起止电量',value:`${unit(row.start_battery, '%', 0, 0, 100)} → ${unit(row.end_battery, '%', 0, 0, 100)}`},
      {label:'额定续航',value:`${unit(rangeStart, 'km')} → ${unit(rangeEnd, 'km')}`}, {label:'续航变化',value:rangeDiff}] },
      {title:'车速', rows:[{label:'全程平均车速',value:unit(average,'km/h')},{label:'采样最高车速',value:unit(row.speed_max,'km/h',0,0)}]},
      {title:'温度', rows:[{label:'平均车外温度',value:unit(row.outside_temp_avg,'℃',1)},{label:'平均车内温度',value:unit(row.inside_temp_avg,'℃',1)}]}],
    synced: validTime(detail.synced_at) ? `${chinaParts(detail.synced_at).day} ${chinaParts(detail.synced_at).time}` : '尚未同步' };
}
function mapData(detail) {
  if (!['ready','empty'].includes(detail.status)) return { polylines:[], markers:[], fitPoints:[] };
  if (detail.coordinate_system !== 'gcj02') throw new Error('轨迹坐标格式异常');
  const segments = Array.isArray(detail.segments) ? detail.segments : [];
  const polylines = [], all = [], isolated = [];
  for (const segment of segments) {
    if (!Array.isArray(segment) || segment.some(p => !point(p))) throw new Error('轨迹数据格式异常');
    const points = segment.map(p=>({latitude:Number(p.latitude),longitude:Number(p.longitude)}));
    all.push(...points);
    if (points.length === 1) isolated.push(points[0]);
    // Overlap a boundary point only within the SAME contiguous segment.
    for (let i=0; i<points.length-1; i+=1999) polylines.push({ points:points.slice(i,i+2000), color:'#6B97FFFF', width:4, borderColor:'#9BBBFF80', borderWidth:1, level:'abovelabels' });
  }
  const endpoints = detail.endpoints || {};
  const markers = isolated.map((p,i)=>Object.assign({id:i+3,iconPath:'/assets/point.png',width:16,height:16,callout:{content:'采集点',display:'BYCLICK',padding:6,borderRadius:6}},p));
  for (const [side,id,color,label] of [['start',1,'#279c73','起'],['end',2,'#d66d45','终']]) {
    if (point(endpoints[side])) markers.push(Object.assign({id,iconPath:`/assets/${side}.png`,width:24,height:24,
      callout:{content:label,color:'#FFFFFF',bgColor:color,display:'ALWAYS',padding:7,borderRadius:12,fontSize:13}}, endpoints[side]));
  }
  const fit = all.concat(markers.map(({latitude,longitude})=>({latitude,longitude})));
  if (!fit.length) return {polylines,markers,fitPoints:[]};
  // Native includePoints needs a bounding extent, not every raw position.
  const bounds=fit.reduce((b,p)=>({minLat:Math.min(b.minLat,p.latitude),maxLat:Math.max(b.maxLat,p.latitude),minLon:Math.min(b.minLon,p.longitude),maxLon:Math.max(b.maxLon,p.longitude)}),{minLat:90,maxLat:-90,minLon:180,maxLon:-180});
  return {polylines,markers,fitPoints:fit.length===1?fit:[{latitude:bounds.minLat,longitude:bounds.minLon},{latitude:bounds.maxLat,longitude:bounds.maxLon}]};
}
function routeMessage(detail, map) {
  if (detail.unavailable) return '详情服务正在接入，概况可以先看';
  if (detail.status === 'pending') return '轨迹同步中，请稍后刷新';
  if (detail.status === 'failed') return '轨迹加载失败，概况仍可查看';
  if (detail.status === 'unfinished') return '行程尚未结束，结束并同步后可查看轨迹';
  if (detail.status === 'empty') return '这趟行程未采集到轨迹';
  const quality = detail.quality || {};
  const samplingGap = quality.gaps > 0;
  const anomalies = quality.jumps > 0 || quality.filtered_points > 0;
  if (samplingGap && anomalies) return '部分采样中断或位置异常，已分段展示';
  if (samplingGap) return '部分采样间隔超过2分钟，已分段展示';
  if (anomalies) return '部分位置数据异常，已分段展示';
  if (!map.polylines.length && map.markers.length) return '仅采集到孤立位置点，无法绘制连续路线';
  if (!map.fitPoints.length) return '这趟行程未采集到轨迹';
  return '轨迹来自车辆采集';
}
module.exports = { presentation, mapData, routeMessage };
