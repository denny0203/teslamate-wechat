const test = require('node:test');
const assert = require('node:assert/strict');
const { presentation, mapData, routeMessage } = require('../miniprogram/lib/detail');
const point=(latitude=30,longitude=120)=>({latitude,longitude});
const detail = () => ({status:'ready',coordinate_system:'gcj02',summary:{id:1,car_id:1,started_at:'2026-10-01T15:59:30Z',ended_at:'2026-10-01T16:00:00Z',distance_km:1,start_battery:0,end_battery:null,inside_temp_avg:0,outside_temp_avg:-5},segments:[[point(),point(30,120.001)]],endpoints:{start:point(),end:point(30,120.001)}});
test('跨日时间、真实零、负温度与短行程均正确，不用取整分钟算平均速度',()=>{
  const r=presentation(detail());assert.equal(r.day,'2026-10-01');assert.equal(r.time,'23:59 – 2026-10-02 00:00');assert.equal(r.duration,'不足1分钟');assert.equal(r.metrics[1].rows[0].value,'120 km/h');assert.equal(r.metrics[0].rows[0].value,'0 % → 未记录');assert.equal(r.metrics[2].rows[0].value,'-5.0 ℃');assert.equal(r.metrics[2].rows[1].value,'0.0 ℃');
});
test('每片段独立画线，单点不会连线，起终点以真实端点为准',()=>{
  const d=detail();d.segments=[[point(),point(30,120.001)],[point(30,120.1)], [point(30,120.2),point(30,120.201)]];d.quality={gaps:1,jumps:0,filtered_points:0};const m=mapData(d);assert.equal(m.polylines.length,2);assert.equal(m.markers.length,3);assert.match(routeMessage(d,m),/采样间隔/);assert.equal(m.polylines[1].points[0].longitude,120.2);
});
test('长片段分批时只在同一片段重叠边界，不截去转折或路线末端',()=>{
  const d=detail();d.segments=[Array.from({length:4200},(_,i)=>point(30,120+i*.00001))];const m=mapData(d);assert.deepEqual(m.polylines.map(p=>p.points.length),[2000,2000,202]);assert.deepEqual(m.polylines[0].points.at(-1),m.polylines[1].points[0]);assert.deepEqual(m.polylines.at(-1).points.at(-1),d.segments[0].at(-1));
});
test('坐标系不符或无效坐标拒绝展示，不能画错位置',()=>{
  const d=detail();d.coordinate_system='wgs84';assert.throws(()=>mapData(d),/坐标/);d.coordinate_system='gcj02';d.segments=[[{latitude:NaN,longitude:120}]];assert.throws(()=>mapData(d),/数据/);
});
test('无轨迹、同步中、未结束与失败都有不同结果',()=>{
  for(const status of ['empty','pending','unfinished','failed']){const d=detail();d.status=status;d.segments=[];if(status==='empty')d.endpoints={};const m=mapData(d);assert.equal(m.polylines.length,0);assert.equal(m.fitPoints.length,0);assert(routeMessage(d,m));}
});

test('采样中断和位置异常分开提示，正常轨迹不提示缺段',()=>{
 const d=detail(),m=mapData(d);
 d.quality={gaps:0,jumps:0,filtered_points:0};assert.equal(routeMessage(d,m),'轨迹来自车辆采集');
 d.quality.jumps=1;assert.match(routeMessage(d,m),/位置数据异常/);assert.doesNotMatch(routeMessage(d,m),/采样间隔/);
 d.quality.gaps=1;assert.match(routeMessage(d,m),/采样中断或位置异常/);
 d.quality.jumps=0;assert.match(routeMessage(d,m),/间隔超过2分钟/);
});

test('紧凑摘要保留真实续航变化，缺失值不补零，续航增加不当作消耗',()=>{
 const d=detail();d.summary.start_range_km=387;d.summary.end_range_km=336;d.summary.speed_max=96;
 let r=presentation(d);assert.equal(r.rangeSummary,'51km (387–336)');assert.equal(r.maximumSpeed,'96 km/h');assert.equal(r.outsideTemperature,'-5.0 ℃');
 d.summary.end_range_km=400;r=presentation(d);assert.equal(r.rangeSummary,'增加13km (387–400)');
 d.summary.start_range_km=null;assert.equal(presentation(d).rangeSummary,'未记录');
});

test('能耗按估算字段显示，缺失值不冒充零',()=>{
 const d=detail();d.summary.energy_used_kwh=0.79866;d.summary.average_consumption_wh_km=177.48;
 const r=presentation(d);assert.equal(r.energyUsed,'0.8 度');assert.equal(r.averageConsumption,'177 Wh/km');
 delete d.summary.energy_used_kwh;assert.equal(presentation(d).energyUsed,'未记录');
 d.summary.energy_used_kwh=0;assert.equal(presentation(d).energyUsed,'0.0 度');
});
