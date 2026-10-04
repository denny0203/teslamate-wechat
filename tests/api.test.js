const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const format = require('../miniprogram/lib/format');
function harness(initial, respond) {
  let stored = initial;
  const calls = [];
  const context = { module: {exports: {}}, require: name => name === '../config' ? {url:'https://example.invalid',anonKey:'test-public-placeholder'} : format,
    wx: {getStorageSync: () => stored, setStorageSync: (_, value) => { stored = value; }, removeStorageSync: () => {stored = null;},
      request(options) { calls.push(options); queueMicrotask(() => respond(options)); } }, Date, Promise, Error, encodeURIComponent };
  vm.runInNewContext(fs.readFileSync('miniprogram/lib/api.js','utf8'), context);
  return { api: context.module.exports, calls, stored: () => stored };
}
test('过期会话先刷新，分页读取不会漏掉第501条；同步时间单独读取', async () => {
  const h = harness({access_token:'test-old',refresh_token:'test-refresh',expires_at:1}, o => {
    if (o.url.includes('grant_type=refresh_token')) return o.success({statusCode:200,data:{access_token:'test-new',refresh_token:'test-refresh-next',expires_in:3600}});
    if (o.url.includes('app_sync_status')) return o.success({statusCode:200,data:[{last_success_at:'2026-10-02T00:00:00Z'}]});
    assert.equal(o.header.Authorization,'Bearer test-new');
    o.success({statusCode:200,data:o.url.includes('offset=0') ? Array.from({length:500},(_,i)=>({id:i})) : [{id:500}]});
  });
  const r = await h.api.listDrives();
  assert.equal(r.rows.length,501); assert.equal(h.calls.length,4);
  assert.equal(h.stored().access_token,'test-new');
  assert.match(h.calls[1].url,/started_at=gte\./); assert.match(h.calls[1].url,/started_at=lte\./);
});
test('刷新被拒绝后清除本地会话，不继续请求私有行程', async () => {
  const h = harness({access_token:'test-old',refresh_token:'test-refresh',expires_at:1}, o => o.success({statusCode:400,data:{}}));
  await assert.rejects(h.api.listDrives()); assert.equal(h.stored(),null); assert.equal(h.calls.length,1);
});
test('断网不伪装成空行程，也不删除有效会话', async () => {
  const initial={access_token:'test-valid',refresh_token:'test-refresh',expires_at:Math.floor(Date.now()/1000)+3600};
  const h=harness(initial,o=>o.fail());
  await assert.rejects(h.api.listDrives(),/连接失败/); assert.equal(h.stored(),initial);
});

test('详情只读当前用户可见摘要及对应原子快照，包含车辆归属校验',async()=>{
  const h=harness({access_token:'test',refresh_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>{
    if(o.url.includes('app_drive_details'))return o.success({statusCode:200,data:[{id:2,car_id:1,version:'test-version',status:'ready',payload:{summary:{id:2,car_id:1,distance_km:5},status:'ready',coordinate_system:'gcj02',segments:[]}}]});
    o.success({statusCode:200,data:[{id:2,car_id:1,ended_at:'2026-10-02T00:00:00Z'}]});
  });
  const d=await h.api.driveDetail(2);assert.equal(d.summary.distance_km,5);assert.equal(d.version,'test-version');assert.equal(h.calls.length,2);
});
test('无快照是待同步；新表尚未部署时保留摘要并标记服务接入中',async()=>{
  for(const unavailable of [false,true]){
    const h=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.success(o.url.includes('app_drive_details')?{statusCode:unavailable?404:200,data:[]}: {statusCode:200,data:[{id:2,car_id:1,ended_at:'2026-10-02T00:00:00Z'}]}));
    const d=await h.api.driveDetail(2);assert.equal(d.status,'pending');assert.equal(Boolean(d.unavailable),unavailable);
  }
});
test('详情网络失败保留概况；不存在的记录不请求轨迹',async()=>{
  const h=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.url.includes('app_drive_details')?o.fail():o.success({statusCode:200,data:[{id:2,car_id:1}]}));assert.equal((await h.api.driveDetail(2)).status,'failed');
  const absent=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.success({statusCode:200,data:[]}));await assert.rejects(absent.api.driveDetail(2),/无法查看/);assert.equal(absent.calls.length,1);
});
test('拒绝查询注入和错误车辆快照',async()=>{
  const h=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.success({statusCode:200,data:o.url.includes('app_drive_details')?[{car_id:9,payload:{summary:{id:2}}}]:[{id:2,car_id:1}]}));await assert.rejects(h.api.driveDetail('2&owner_id=eq.other'));assert.equal(h.calls.length,0);await assert.rejects(h.api.driveDetail(2),/格式异常/);
});
test('退出时在途刷新不能重新写入旧会话',async()=>{
  let pending;
  const h=harness({access_token:'test-old',refresh_token:'test-refresh',expires_at:1},o=>{pending=o;});
  const promise=h.api.listDrives();await new Promise(resolve=>setImmediate(resolve));h.api.signOut();pending.success({statusCode:200,data:{access_token:'test-new',refresh_token:'test-refresh-next',expires_in:3600}});await assert.rejects(promise);assert.equal(h.stored(),null);assert.equal(h.calls.length,1);
});
test('最近用车限制30次已结束记录，月份轨迹边界使用相同六位UTC精度',async()=>{
 const h=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.success({statusCode:200,data:[]}));
 await h.api.recentDrives();assert.match(h.calls[0].url,/limit=30/);assert.match(h.calls[0].url,/ended_at=not.is.null/);assert.doesNotMatch(h.calls[0].url,/started_at=gte/);
 await h.api.routePage('2026-10');const url=decodeURIComponent(h.calls[1].url);assert.match(url,/2026-09-30T16:00:00.000000Z/);assert.match(url,/2026-10-31T16:00:00.000000Z/);await assert.rejects(h.api.routePage('2026-13'));
});
test('按日轨迹使用北京时间半开区间，跨月闰日正确且拒绝不存在日期',async()=>{
 const h=harness({access_token:'test',expires_at:Math.floor(Date.now()/1000)+3600},o=>o.success({statusCode:200,data:[]}));
 await h.api.routePage('2026-10-01');let url=decodeURIComponent(h.calls[0].url);
 assert.match(url,/started_at=gte.2026-09-30T16:00:00.000000Z/);assert.match(url,/started_at=lt.2026-10-01T16:00:00.000000Z/);
 await h.api.routePage('2024-02-29');url=decodeURIComponent(h.calls[1].url);assert.match(url,/2024-02-28T16:00:00.000000Z/);assert.match(url,/2024-02-29T16:00:00.000000Z/);
 await assert.rejects(h.api.routePage('2026-02-29'));await assert.rejects(h.api.routePage('2026-10-01&owner_id=eq.other'));assert.equal(h.calls.length,2);
});
