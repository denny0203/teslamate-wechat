const config = require('../config');
const { windowStart, chinaParts } = require('./format');
const SESSION = 'tesla-mvp-session-v1';
let refreshing = null;
let generation = 0;
let recentRows = [];
function configured() { return /^https:\/\//.test(config.url) && Boolean(config.anonKey); }
function session() { return wx.getStorageSync(SESSION) || null; }
function signOut() { generation += 1; recentRows = []; wx.removeStorageSync(SESSION); }
function sessionGeneration() { return generation; }
function ensureGeneration(value) { if (generation !== value || !session()) { const error = new Error('登录已过期，请重新登录'); error.status = 401; throw error; } }
function request(path, method = 'GET', data, token) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: config.url.replace(/\/$/, '') + path, method, data, timeout: 15000,
      header: { apikey: config.anonKey, Authorization: `Bearer ${token || config.anonKey}`, 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data);
        const error = new Error(res.statusCode === 401 ? '登录已过期，请重新登录' : '请求失败，请稍后重试');
        error.status = res.statusCode;
        reject(error);
      },
      fail() { reject(new Error('连接失败，请检查网络后重试')); }
    });
  });
}
function save(data) {
  if (!data.access_token || !data.refresh_token) throw new Error('登录结果异常');
  const value = { access_token: data.access_token, refresh_token: data.refresh_token, expires_at: data.expires_at || Math.floor(Date.now() / 1000) + data.expires_in };
  wx.setStorageSync(SESSION, value);
  return value;
}
async function signIn(email, password) {
  const epoch = generation;
  try { const data = await request('/auth/v1/token?grant_type=password', 'POST', { email: email.trim(), password }); if (epoch !== generation) throw new Error('登录已取消'); save(data); }
  catch (error) { if (error.status === 400 || error.status === 401) throw new Error('账号或密码不正确'); throw error; }
}
async function accessToken() {
  let current = session();
  if (!current) throw new Error('请先登录');
  if (current.expires_at * 1000 > Date.now() + 60000) return current.access_token;
  const epoch = generation;
  if (!refreshing) refreshing = request('/auth/v1/token?grant_type=refresh_token', 'POST', { refresh_token: current.refresh_token })
    .then(data => { ensureGeneration(epoch); return save(data); }).catch(error => { if (epoch === generation && (error.status === 400 || error.status === 401)) signOut(); throw error; })
    .finally(() => { refreshing = null; });
  const value = await refreshing;
  ensureGeneration(epoch);
  return value.access_token;
}
async function listDrives() {
  const epoch = generation;
  const token = await accessToken();
  ensureGeneration(epoch);
  const now = new Date().toISOString();
  const from = windowStart(new Date(now).getTime());
  const rows = [];
  const limit = 500;
  for (let offset = 0; ; offset += limit) {
    ensureGeneration(epoch);
    const page = await request(`/rest/v1/app_drives?select=id,car_id,started_at,ended_at,start_address,end_address,distance_km&started_at=gte.${encodeURIComponent(from)}&started_at=lte.${encodeURIComponent(now)}&order=started_at.desc,id.desc&limit=${limit}&offset=${offset}`, 'GET', undefined, token);
    if (!Array.isArray(page)) throw new Error('行程数据格式异常');
    rows.push(...page);
    if (page.length < limit) break;
    if (offset >= 10000) throw new Error('行程数量异常，请联系维护者');
  }
  ensureGeneration(epoch);
  const status = await request('/rest/v1/app_sync_status?select=last_success_at,latest_drive_at&limit=1', 'GET', undefined, token);
  ensureGeneration(epoch);
  recentRows = rows;
  return { rows, status: status[0] || null, from, to: now };
}
async function readTable(path) {
  const epoch=generation, token=await accessToken(); ensureGeneration(epoch);
  const rows=await request('/rest/v1/'+path,'GET',undefined,token); ensureGeneration(epoch);
  if(!Array.isArray(rows)) throw new Error('数据格式异常'); return rows;
}
const HISTORY_FIELDS='id,car_id,started_at,ended_at,start_address,end_address,distance_km,energy_used_kwh,range_used_km';
async function recentDrives() {
 const rows=await readTable(`app_drives?select=${HISTORY_FIELDS}&ended_at=not.is.null&order=started_at.desc,id.desc&limit=30`);
 recentRows=rows; return rows;
}
async function historyDrives() {
 const epoch=generation,rows=[];
 for(let offset=0;;offset+=500){
  const page=await readTable(`app_drives?select=${HISTORY_FIELDS}&ended_at=not.is.null&order=started_at.desc,id.desc&limit=500&offset=${offset}`);
  ensureGeneration(epoch);rows.push(...page); if(page.length<500)break;
  if(offset>=100000)throw new Error('历史记录过多，请联系维护者');
 }
 ensureGeneration(epoch);recentRows=rows; return rows;
}
async function vehicles(){return readTable('app_vehicles?select=car_id,payload,synced_at&order=car_id.asc');}
async function drivesForDay(id){
 const epoch=generation;
 const d=await readTable(`app_drives?select=id,car_id,started_at&id=eq.${safeId(id)}&limit=1`);
 if(!d.length)return [];
 const day=chinaParts(d[0].started_at).day,from=new Date(day+'T00:00:00+08:00'),to=new Date(from.getTime()+86400000);
 const rows=[];
 for(let offset=0;;offset+=500){
  const page=await readTable(`app_drives?select=${HISTORY_FIELDS}&car_id=eq.${safeId(d[0].car_id)}&started_at=gte.${encodeURIComponent(from.toISOString())}&started_at=lt.${encodeURIComponent(to.toISOString())}&order=started_at.desc,id.desc&limit=500&offset=${offset}`);
  ensureGeneration(epoch);rows.push(...page);if(page.length<500)break;
 }
 recentRows=rows;return rows;
}
function safeId(id){if(!/^[1-9]\d{0,15}$/.test(String(id)))throw new Error('记录编号无效');return String(id);}
async function routePage(period,offset=0){
 let filter='';
 if(period){
  const monthly=/^\d{4}-(0[1-9]|1[0-2])$/.test(period),daily=/^\d{4}-(0[1-9]|1[0-2])-\d{2}$/.test(period);
  if(!monthly&&!daily)throw new Error('日期范围无效');
  const from=new Date((monthly?period+'-01':period)+'T00:00:00+08:00');
  if(!Number.isFinite(from.getTime())||chinaParts(from.toISOString()).day!==(monthly?period+'-01':period))throw new Error('日期范围无效');
  const year=Number(period.slice(0,4)),month=Number(period.slice(5,7));
  const to=daily?new Date(from.getTime()+86400000):new Date(Date.UTC(year,month,1)-8*3600000);
  filter=`&payload->summary->>started_at=gte.${encodeURIComponent(from.toISOString().replace('.000Z','.000000Z'))}&payload->summary->>started_at=lt.${encodeURIComponent(to.toISOString().replace('.000Z','.000000Z'))}`;
 }
 return readTable(`app_drive_details?select=id,car_id,status,payload,synced_at&status=eq.ready${filter}&order=id.desc&limit=10&offset=${Number(offset)||0}`);
}
function dayDrives(id) {
  if (!session()) return [];
  const current = recentRows.find(row => String(row.id) === String(id));
  if (!current) return [];
  const day = chinaParts(current.started_at).day;
  return recentRows.filter(row => row.car_id === current.car_id && chinaParts(row.started_at).day === day);
}
async function driveDetail(id) {
  if (!/^[1-9]\d{0,15}$/.test(String(id))) throw new Error('这趟行程暂时无法查看');
  const epoch = generation;
  const token = await accessToken();
  ensureGeneration(epoch);
  const rows = await request(`/rest/v1/app_drives?select=id,car_id,started_at,ended_at,start_address,end_address,distance_km&id=eq.${id}&limit=1`, 'GET', undefined, token);
  ensureGeneration(epoch);
  if (!Array.isArray(rows) || !rows.length) throw new Error('这趟行程暂时无法查看');
  let details;
  try { details = await request(`/rest/v1/app_drive_details?select=id,car_id,version,status,payload,synced_at&id=eq.${id}&limit=1`, 'GET', undefined, token); }
  catch (error) {
    ensureGeneration(epoch);
    if (error.status === 404) return { summary: rows[0], status: rows[0].ended_at ? 'pending' : 'unfinished', unavailable: true };
    if (error.status === 401) throw error;
    return { summary: rows[0], status: 'failed', error: error.message };
  }
  ensureGeneration(epoch);
  if (!Array.isArray(details)) throw new Error('行程数据格式异常');
  if (!details.length) return { summary: rows[0], status: rows[0].ended_at ? 'pending' : 'unfinished' };
  const snapshot = details[0];
  if (snapshot.car_id !== rows[0].car_id || !snapshot.payload || !snapshot.payload.summary || String(snapshot.payload.summary.id) !== String(id) || snapshot.payload.summary.car_id !== snapshot.car_id || snapshot.payload.status !== snapshot.status) throw new Error('行程数据格式异常');
  return Object.assign({}, snapshot.payload, { version: snapshot.version, synced_at: snapshot.synced_at });
}
module.exports = { configured, session, signIn, signOut, listDrives, driveDetail, dayDrives, sessionGeneration, recentDrives, historyDrives, vehicles, drivesForDay, routePage };
