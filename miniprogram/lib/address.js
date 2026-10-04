// Presentation only: keep the original address available for inspection.
function addressLabel(full, withCity = false, fallback = '地址未记录') {
  if (typeof full !== 'string' || !full.trim()) return fallback;
  const original = full.trim();
  let rest = original.replace(/^中国/, '');
  let city = '';
  const municipality = rest.match(/^(北京市|上海市|天津市|重庆市)/);
  if (municipality) { city = municipality[1]; rest = rest.slice(city.length); }
  else {
    rest = rest.replace(/^[\u4e00-\u9fff]{2,8}(?:省|自治区)/, '');
    const match = rest.match(/^([\u4e00-\u9fff]{2,12}?(?:市|自治州|地区|盟))/);
    if (match) { city = match[1]; rest = rest.slice(city.length); }
  }
  // Strip only leading administrative levels, never occurrences inside a POI.
  rest = rest.replace(/^[\u4e00-\u9fff]{1,10}?(?:自治县|区|县)/, '');
  rest = rest.replace(/^[\u4e00-\u9fff]{1,12}?(?:街道|乡|镇)/, '');
  const road = rest.match(/^(.{1,24}?(?:大道|公路|胡同|路|街|巷))(\d+[A-Za-z]?(?:[-—]\d+)?号(?:院)?|\d+弄\d*号?)?/);
  let place = rest;
  if (road) {
    const tail = rest.slice(road[0].length).trim();
    // Avoid treating bare house numbers or a road junction as a place name.
    if (tail && !/^(?:\d|与|交叉|交口|附近|中国.*自由贸易试验区)/.test(tail)) place = tail;
    else place = /^中国.*自由贸易试验区/.test(tail) ? road[0] : road[0] + tail;
  }
  place = place.trim() || original;
  const cityLabel = city.replace(/市$/, '');
  return withCity && cityLabel ? `${cityLabel}·${place}` : place;
}
module.exports = { addressLabel };
