const api = require('../../lib/api');
const { present } = require('../../lib/format');
const { presentation, mapData, routeMessage } = require('../../lib/detail');
const mapStyle = require('../../map.config');
const customStyleEnabled = typeof mapStyle.subkey === 'string' && mapStyle.subkey.trim().length > 0
  && Number.isInteger(mapStyle.layerStyle) && mapStyle.layerStyle > 0;
const INITIAL = { busy:false, hasSummary:false, overview:null, error:'', status:'loading',
  notice:'正在读取行程与轨迹…', polyline:[], markers:[], fitPoints:[], latitude:30.25, longitude:120.15,
  scale:13, sheet:false, dayRows:[], mapVisible:false, mapError:false, drawing:false,
  mapSubkey:customStyleEnabled ? mapStyle.subkey.trim() : '',
  mapLayerStyle:customStyleEnabled ? mapStyle.layerStyle : 1, mapStyleError:false };
Page({
  data: Object.assign({}, INITIAL),
  onLoad(options) { this.driveId = String(options.id || ''); this.requestId = 0; this.map = wx.createMapContext('drive-map', this); },
  onShow() { if (!api.session()) this.loginRequired(); else if (!this.data.hasSummary) this.load(); },
  onUnload() {
    this.requestId += 1;
    clearTimeout(this.renderTimer);
    // The view is already being destroyed; do not send another map update.
    this.data = Object.assign({}, INITIAL);
  },
  loginRequired() {
    this.requestId += 1;
    clearTimeout(this.renderTimer);
    this.setData(Object.assign({}, INITIAL));
    getApp().globalData.returnDriveId = this.driveId;
    wx.reLaunch({ url:'/pages/index/index' });
  },
  async load() {
    if (this.data.busy) return;
    const requestId = ++this.requestId;
    clearTimeout(this.renderTimer);
    this.setData({busy:true,error:'',sheet:false,drawing:false});
    try {
      const detail = await api.driveDetail(this.driveId);
      if (requestId !== this.requestId) return;
      let map;
      try { map = mapData(detail); }
      catch (error) { map = {polylines:[],markers:[],fitPoints:[]}; detail.status='failed'; }
      const overview = presentation(detail);
      this.setData({ hasSummary:true, overview, status:detail.status, notice:routeMessage(detail,map),
        polyline:[], markers:map.markers, fitPoints:map.fitPoints, mapVisible:map.fitPoints.length>0,
        mapError:false, latitude:map.fitPoints.length ? map.fitPoints[0].latitude : 30.25,
        longitude:map.fitPoints.length ? map.fitPoints[0].longitude : 120.15,
        drawing:map.polylines.length>0 }, () => {
          if (requestId !== this.requestId) return;
          this.fit();
          this.renderRoute(map.polylines, requestId, 0);
        });
      this.updateDayRows();
    } catch (error) {
      if (requestId !== this.requestId) return;
      if (error.status===401 || !api.session()) { api.signOut(); this.loginRequired(); return; }
      this.setData({error:error.message || '加载失败，请稍后重试'});
    } finally {
      if (requestId===this.requestId) this.setData({busy:false});
      wx.stopPullDownRefresh();
    }
  },
  renderRoute(lines, requestId, index) {
    if (requestId!==this.requestId) return;
    if (index===lines.length) { this.setData({drawing:false}); return; }
    // Each bridge message contains at most 2,000 points; never joins a gap.
    const batch = {};
    let next=index, points=0;
    // Many short pieces must be batched too; one timer per piece is too slow.
    while (next<lines.length && next-index<100 && points+lines[next].points.length<=2000) {
      batch[`polyline[${next}]`]=lines[next];
      points+=lines[next].points.length;
      next+=1;
    }
    this.setData(batch, () => {
      if (requestId!==this.requestId) return;
      this.renderTimer=setTimeout(()=>this.renderRoute(lines,requestId,next),16);
    });
  },
  updateDayRows() {
    const groups = present(api.dayDrives(this.driveId)).groups;
    const rows = groups.length ? groups[0].rows : [];
    this.setData({dayRows:rows.map(row=>Object.assign({},row,{current:String(row.id)===this.driveId}))});
  },
  fit() {
    if (!this.data.mapVisible || !this.data.fitPoints.length) return;
    const requestId=this.requestId;
    wx.createSelectorQuery().in(this).select('.overview-card').boundingClientRect()
      .select('.map-area').boundingClientRect().exec(rects=>{
        if (requestId!==this.requestId || !rects || !rects[1]) return;
        const card=rects[0], area=rects[1];
        const top=card ? Math.max(16,card.bottom-area.top+16) : 24;
        this.map.includePoints({points:this.data.fitPoints, padding:[top,88,100,32],
          fail:()=>{ if(requestId===this.requestId) this.setData({mapError:true}); }});
      });
  },
  mapFailed() { this.setData({mapError:true}); },
  mapStyleFailed(e) {
    if (customStyleEnabled && e.detail && e.detail.ability === 'layer-style') this.setData({mapStyleError:true});
  },
  mapStyleReady(e) {
    if (e.detail && e.detail.ability === 'layer-style') this.setData({mapStyleError:false});
  },
  retryMap() { this.setData({mapVisible:false,mapError:false,mapStyleError:false},()=>this.setData({mapVisible:true},()=>this.fit())); },
  zoom(e) { this.map.getScale({success:r=>this.setData({scale:Math.min(20,Math.max(3,r.scale+Number(e.currentTarget.dataset.delta)))})}); },
  showEnergyInfo() {
    wx.showModal({title:'能耗与车速说明',content:'≈ 表示估算值，与 TeslaMate 的额定续航计算口径一致：消耗电量 = 起止额定续航差 × 车辆能耗系数；平均能耗 = 消耗电量 ÷ 行驶里程。续航回升或所需数据缺失时不显示能耗。最大车速为采样最高值，平均车速包含停车等待。',showCancel:false,confirmText:'知道了'});
  },
  showAddress() {
    if (!this.data.overview) return;
    wx.showModal({title:'起终点名称',content:`起点：${this.data.overview.fullStart}\n终点：${this.data.overview.fullEnd}`,showCancel:false,confirmText:'知道了'});
  },
  async showDay() {
    {
      try { await api.drivesForDay(this.driveId); this.updateDayRows(); }
      catch (error) { if (!api.session() || error.status===401) { api.signOut(); this.loginRequired(); } else wx.showToast({title:'本日行程加载失败',icon:'none'}); return; }
    }
    if (!this.data.dayRows.length) { wx.showToast({title:'当天暂无其他记录',icon:'none'}); return; }
    this.setData({sheet:true});
  },
  closeDay() { this.setData({sheet:false}); },
  noop() {},
  selectDrive(e) {
    const id=String(e.currentTarget.dataset.id);
    if (id===this.driveId) { this.closeDay(); return; }
    // Allow a newer request to supersede an earlier pending request.
    this.driveId=id;
    this.requestId+=1;
    clearTimeout(this.renderTimer);
    this.setData(Object.assign({},INITIAL));
    this.load();
  },
  onPullDownRefresh() { this.load(); }
});
