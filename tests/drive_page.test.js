const assert=require('node:assert/strict'),test=require('node:test'),vm=require('node:vm'),fs=require('node:fs');
const fmt=require('../miniprogram/lib/format'),detail=require('../miniprogram/lib/detail');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  let spec,loggedIn=true;const pending=[],app={globalData:{}};
  const api={session:()=>loggedIn,signOut:()=>{loggedIn=false},driveDetail:id=>new Promise((resolve,reject)=>pending.push({id,resolve,reject})),dayDrives:()=>[],listDrives:async()=>({})};
  const wx={createMapContext:()=>({includePoints(){},getScale(){}}),createSelectorQuery:()=>({in(){return this},select(){return this},boundingClientRect(){return this},exec(cb){cb([null,null])}}),stopPullDownRefresh(){},reLaunch(){},showToast(){},showModal(){}};
  const ctx=vm.createContext({require:name=>name==='../../lib/api'?api:name==='../../lib/format'?fmt:name==='../../map.config'?{subkey:'',layerStyle:1}:detail,wx,getApp:()=>app,Page:v=>spec=v,setTimeout,clearTimeout,console});
  vm.runInContext(fs.readFileSync('miniprogram/pages/drive/drive.js','utf8'),ctx);
  const page=Object.assign({},spec,{data:structuredClone(spec.data),setData(values,cb){for(const [k,v] of Object.entries(values)){const match=k.match(/^polyline\[(\d+)\]$/);if(match)this.data.polyline[Number(match[1])]=v;else this.data[k]=v}if(cb)cb()}});
  page.onLoad({id:'1'});
  return {page,pending,app};
}
function snapshot(id,km){return {status:'ready',coordinate_system:'gcj02',summary:{id,car_id:1,started_at:'2026-10-02T00:00:00Z',ended_at:'2026-10-02T00:10:00Z',distance_km:km},segments:[],endpoints:{},quality:{}}}
test('快速切换后旧请求不能把概况或轨迹覆盖到新行程',async()=>{
  const h=harness();const first=h.page.load();h.page.selectDrive({currentTarget:{dataset:{id:'2'}}});assert.deepEqual(h.pending.map(p=>p.id),['1','2']);h.pending[1].resolve(snapshot(2,20));await tick();assert.equal(h.page.data.overview.distance,'20.0');h.pending[0].resolve(snapshot(1,10));await first;assert.equal(h.page.data.overview.distance,'20.0');assert.equal(h.page.driveId,'2');h.page.onUnload();
});
test('登录过期清除轨迹并保留重登录后的目标行程ID',async()=>{
  const h=harness();const promise=h.page.load();const error=new Error('expired');error.status=401;h.pending[0].reject(error);await promise;assert.equal(h.page.data.hasSummary,false);assert.equal(h.page.data.polyline.length,0);assert.equal(h.app.globalData.returnDriveId,'1');
});
test('离开页面后返回的请求不能恢复私人详情',async()=>{
  const h=harness();const promise=h.page.load();let writes=0;const original=h.page.setData.bind(h.page);h.page.setData=(...args)=>{writes++;original(...args)};h.page.onUnload();h.pending[0].resolve(snapshot(1,10));await promise;assert.equal(h.page.data.hasSummary,false);assert.equal(h.page.data.overview,null);assert.equal(writes,0);
});
test('大量缺段按批传输，避免每个短片段等待一次计时器',async()=>{
  const h=harness();let calls=0,largest=0;const original=h.page.setData.bind(h.page);
  h.page.setData=(data,cb)=>{const lines=Object.entries(data).filter(([k])=>k.startsWith('polyline['));if(lines.length){calls++;largest=Math.max(largest,lines.reduce((n,[k,v])=>n+v.points.length,0))}original(data,cb)};
  const lines=Array.from({length:250},()=>({points:[{latitude:30,longitude:120},{latitude:30,longitude:120.001}]}));
  h.page.renderRoute(lines,h.page.requestId,0);
  await new Promise(resolve=>setTimeout(resolve,80));
  assert.equal(h.page.data.polyline.length,250);assert.equal(calls,3);assert(largest<=2000);h.page.onUnload();
});
