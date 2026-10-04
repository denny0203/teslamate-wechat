const test = require('node:test');
const assert = require('node:assert/strict');
const { addressLabel } = require('../miniprogram/lib/address');
const { present } = require('../miniprogram/lib/format');
const { presentation } = require('../miniprogram/lib/detail');
test('列表带城市，详情只保留地点名，完整地址不会丢失',()=>{
 const full='上海市杨浦区五角场街道国科路4号财富国际广场';
 assert.equal(addressLabel(full,true),'上海·财富国际广场');
 assert.equal(addressLabel(full),'财富国际广场');
 const row={id:1,started_at:'2026-10-04T00:00:00Z',start_address:full,end_address:full};
 assert.equal(present([row]).groups[0].rows[0].start,'上海·财富国际广场');
 const detail=presentation({summary:row});assert.equal(detail.start,'财富国际广场');assert.equal(detail.fullStart,full);
});
test('无地点名使用道路门牌，省市行政层级和直辖市均支持',()=>{
 assert.equal(addressLabel('上海市杨浦区五角场街道国权路43号',true),'上海·国权路43号');
 assert.equal(addressLabel('浙江省杭州市西湖区蒋村街道文一西路969号淘宝城',true),'杭州·淘宝城');
 assert.equal(addressLabel('北京市朝阳区望京街道阜通东大街6号'),'阜通东大街6号');
});
test('保留地点内部的行政字样，不伪造缺失城市或地址',()=>{
 assert.equal(addressLabel('上海市杨浦区大桥街道得物上海总部互联·宝地'),'得物上海总部互联·宝地');
 assert.equal(addressLabel('财富国际广场',true),'财富国际广场');
 assert.equal(addressLabel(null,false,'起点未记录'),'起点未记录');
 assert.equal(addressLabel('上海市杨浦区国权路与国顺路交叉口'),'国权路与国顺路交叉口');
 assert.equal(addressLabel('上海市浦东新区南汇新城镇水芸路中国(上海)自由贸易试验区临港新片区'),'水芸路');
});
