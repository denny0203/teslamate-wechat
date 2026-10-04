const api = require('../../lib/api');
const { present, chinaParts } = require('../../lib/format');
Page({
  data: { configured: false, loggedIn: false, email: '', password: '', busy: false, error: '', loaded: false, groups: [], total: 0, distance: '0.0', missingDistance: 0, synced: '', range: '',vehicle:null },
  onLoad() { this.setData({ configured: api.configured(), loggedIn: Boolean(api.session()) }); },
  onShow() { this.setData({loggedIn:Boolean(api.session())}); if(this.data.loggedIn)this.load();else this.setData({vehicle:null,loaded:false}); },
  onEmail(e) { this.setData({ email: e.detail.value }); },
  onPassword(e) { this.setData({ password: e.detail.value }); },
  async login() {
    if (this.data.busy) return;
    if (!this.data.email || !this.data.password) return this.setData({ error: '请填写账号和密码' });
    this.setData({ busy: true, error: '' });
    try { await api.signIn(this.data.email, this.data.password); this.setData({ loggedIn: true, password: '' }); }
    catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: false }); }
    if (this.data.loggedIn) {
      const app = getApp();
      const id = app.globalData.returnDriveId;
      app.globalData.returnDriveId = null;
      this.load();
      if (id) wx.navigateTo({url:`/pages/drive/drive?id=${encodeURIComponent(id)}`});
    }
  },
  async load() {
    if(this.data.busy){wx.stopPullDownRefresh();return;}
    const epoch=api.sessionGeneration();this.setData({busy:true,error:''});
    try {const results=await Promise.all([api.vehicles(),api.historyDrives()]);if(epoch!==api.sessionGeneration())return;
      const snapshot=results[0][0]||null;this.setData({vehicle:require('../../lib/overview').vehicle(snapshot,results[1]),loaded:true});
    }catch(error){if(epoch!==api.sessionGeneration())return;this.setData({error:error.message});if(!api.session()||error.status===401)this.logout();}
    finally{if(epoch===api.sessionGeneration())this.setData({busy:false});wx.stopPullDownRefresh();}
  },
  chargeInfo(){const c=this.data.vehicle&&this.data.vehicle.charge;if(!c)return;wx.showModal({title:'最近一次充电',content:`${c.time}\n${c.address||'地点未记录'}\n充入电量 ${c.energy}\n电量 ${c.battery}\n增加额定续航 ${c.range}`,showCancel:false});},
  estimateInfo(){wx.showModal({title:'预估可行驶距离',content:'当前额定续航×车辆能耗系数÷近30天有效行程的里程加权平均能耗。至少5趟、50公里，最近采集超过30分钟或缺少必要数据时暂无法估算。≈表示估算，睡眠不唤醒车辆。',showCancel:false});},
  openDrive(e) { const id = e.currentTarget.dataset.id; if (id) wx.navigateTo({ url: `/pages/drive/drive?id=${encodeURIComponent(id)}` }); },
  confirmLogout() { wx.showModal({title:"退出登录",content:"确认退出当前账号吗？",confirmText:"退出登录",confirmColor:"#315fff",success:result=>{if(result.confirm)this.logout();}}); },
  logout() { api.signOut(); this.setData({ busy:false, loggedIn: false, password: '', groups: [], total: 0, loaded: false, synced: '', distance: '0.0', missingDistance: 0,vehicle:null }); },
  onPullDownRefresh() { if (this.data.loggedIn) this.load(); else wx.stopPullDownRefresh(); }
});
