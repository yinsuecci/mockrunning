'use strict';
const $ = id => document.getElementById(id);
let mode = 'editor', draft = [], loaded = [], status = null, busy = false;
let map, routeLine, liveMarker, nodeLayers = [], lastDeviceKey = '', initialized = false;
let placeResults = [];
function message(text, kind = '') { $('message').textContent = text; $('message').className = kind; }
window.addEventListener('error', e => message(`界面错误：${e.message}`, 'error'));
window.addEventListener('unhandledrejection', e => message(`操作失败：${e.reason?.message || e.reason}`, 'error'));
async function api(action, data) {
  const response = await fetch(`/api/${action}`, {method: data === undefined ? 'GET' : 'POST',
    headers: data === undefined ? {} : {'Content-Type': 'application/json'},
    body: data === undefined ? undefined : JSON.stringify(data), cache: 'no-store', signal: AbortSignal.timeout(45000)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
async function operation(text, fn) {
  if (busy) return;
  busy = true; controls(); message(text);
  try { await fn(); } catch (e) { message(e.message, 'error'); }
  finally { busy = false; controls(); }
}
const coord = p => [p.lat, p.lng];
function saveDraft() {
  try { localStorage.setItem('route-studio-draft-v2', JSON.stringify({points: draft, name: $('route-name').value})); }
  catch { message('浏览器存储不可用，请导出 GPX 保留草稿。', 'error'); }
}
function setMode(value) {
  mode = value;
  $('editor-panel').hidden = value !== 'editor'; $('player-panel').hidden = value !== 'player';
  for (const tab of ['editor', 'player']) {
    $(`tab-${tab}`).classList.toggle('active', value === tab);
    $(`tab-${tab}`).setAttribute('aria-selected', String(value === tab));
  }
  $('map-note').textContent = value === 'editor' ? '单击添加节点 · 拖动节点调整 · 节点弹窗可删除' : '回放预览 · 路线只读 · 橙点为最近发送的模拟位置';
  if (map) { map.getContainer().style.cursor = value === 'editor' ? 'crosshair' : ''; renderRoute(); map.invalidateSize(); }
  controls();
}
function renderRoute() {
  if (!map) return;
  nodeLayers.forEach(m => m.remove()); nodeLayers = [];
  const points = mode === 'editor' ? draft : loaded;
  routeLine.setLatLngs(points.map(coord));
  // A large imported GPX stays editable without creating thousands of DOM markers.
  const stride = Math.max(1, Math.ceil(points.length / 400));
  points.forEach((p, i) => {
    if (i % stride && i !== points.length - 1) return;
    const marker = L.marker(coord(p), {draggable: mode === 'editor',
      icon: L.divIcon({className:'node-icon', html:String(i + 1), iconSize:[28,28], iconAnchor:[14,14]}),
      title:`节点 ${i + 1}`}).addTo(map);
    const popup = document.createElement('div');
    popup.textContent = `#${i + 1} / ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
    if (mode === 'editor') {
      const button = document.createElement('button'); button.textContent = '删除节点';
      button.onclick = () => { draft.splice(i, 1); edited(); }; popup.append(document.createElement('br'), button);
      marker.on('dragend', () => { const c = marker.getLatLng(); draft[i] = {lat:c.lat,lng:c.lng}; edited(); });
    }
    marker.bindPopup(popup); nodeLayers.push(marker);
  });
  let meters = 0;
  for (let i = 1; i < draft.length; i++) meters += map.distance(coord(draft[i-1]), coord(draft[i]));
  $('node-count').textContent = draft.length;
  $('route-distance').textContent = meters < 1000 ? `${Math.round(meters)} m` : `${(meters/1000).toFixed(2)} km`;
  $('nodes').replaceChildren();
  draft.slice(0, 400).forEach((p, i) => {
    const row = document.createElement('li'), label = document.createElement('span'), remove = document.createElement('button');
    label.textContent = `#${i+1}  ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
    remove.textContent = '删除'; remove.onclick = () => { draft.splice(i,1); edited(); };
    row.append(label, remove); $('nodes').append(row);
  });
  if (draft.length > 400) { const li=document.createElement('li'); li.textContent='大轨迹仅抽样显示编号；全部节点仍会导出和回放。'; $('nodes').append(li); }
  controls();
}
function edited() { saveDraft(); renderRoute(); message(`草稿已保存 · ${draft.length} 个节点`, 'success'); }
function addNode(lat, lng) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat)>85 || Math.abs(lng)>180) throw new Error('请输入有效坐标');
  if (draft.length >= 10000) throw new Error('最多支持 10000 个节点');
  draft.push({lat,lng}); edited();
}
function fit() {
  const points = mode === 'editor' ? draft : loaded;
  if (points.length && map) { map.stop(); map.fitBounds(points.map(coord), {padding:[60,60],maxZoom:17,animate:false}); }
}
function locatePhone() {
  const point = status?.real_current || status?.current;
  if (!map || !status?.connected || !point) {
    message('暂无手机坐标：USB 定位接口不能读取真实 GPS；载入路线后可显示已发送的模拟位置。', 'error');
    return;
  }
  map.stop();
  map.setView(coord(point), Math.max(map.getZoom(), 17), {animate:false});
}
function controls() {
  const playing = status?.state === 'playing', paused = status?.state === 'paused';
  $('undo').disabled = busy || !draft.length; $('clear').disabled = busy || !draft.length;
  $('export').disabled = busy || draft.length < 2;
  $('use-route').disabled = busy || draft.length < 2 || playing || paused;
  $('connect').disabled = busy || !!status?.connected || ($('transport').value === 'auto' && !$('devices').value);
  $('connection-options').disabled = busy || !!status?.connected;
  $('disconnect').disabled = busy || !status?.connected;
  $('devices').disabled = busy || !!status?.connected;
  $('player-import').disabled = busy || playing || paused;
  $('clear-loaded-route').disabled = busy || !loaded.length;
  $('start').disabled = busy || playing || !status?.connected || loaded.length < 2;
  $('start').textContent = paused ? '继续移动' : '开始移动';
  $('pause').disabled = busy || !playing;
  $('stop').disabled = busy || !status?.connected;
  $('parameters').disabled = busy || playing;
  $('place-search').disabled = busy;
  $('place-switch').disabled = busy || !status?.connected || playing || !placeResults[$('place-results').selectedIndex];
}
function renderPlaceResults(results) {
  placeResults = results;
  const select = $('place-results');
  select.replaceChildren();
  if (!results.length) select.add(new Option('没有找到地点', ''));
  results.forEach((item, index) => select.add(new Option(item.name, String(index))));
  controls();
}
function settings() {
  const data = {};
  for (const input of $('settings').querySelectorAll('[name]')) data[input.name] = input.type === 'checkbox' ? input.checked : Number(input.value);
  return data;
}
function fillSettings(data) {
  for (const input of $('settings').querySelectorAll('[name]')) {
    if (input.type === 'checkbox') input.checked = data[input.name]; else input.value = data[input.name];
  }
  $('pace').value = +(60/data.speed_kmh).toFixed(4);
}
function renderStatus(data) {
  const firstPosition = data.connected && data.current &&
    (!status?.connected || !status.current || status.udid !== data.udid);
  status = data;
  $('service').textContent = '本地服务已连接';
  const devices = data.devices.filter(d => (d.platform || 'ios') === $('platform').value);
  const key = JSON.stringify(devices) + $('platform').value;
  if (key !== lastDeviceKey) {
    const previous = $('devices').value; $('devices').replaceChildren();
    devices.forEach(d => $('devices').add(new Option(`${d.udid} · ${d.type}`, d.udid)));
    if (!devices.length) $('devices').add(new Option('未发现设备，可选择无线地址连接', ''));
    else if (devices.some(d=>d.udid===previous)) $('devices').value=previous;
    lastDeviceKey=key;
  }
  $('device-state').textContent = data.connected ? '定位服务已连接' : data.state === 'connecting' ? '正在建立定位连接…' : '尚未连接定位服务';
  $('device-help').textContent = data.error || data.discovery_error || data.wda_error || '发现 USB 手机不等于已连接定位服务。';
  const diagnostics = data.diagnostics;
  $('capability-help').textContent = diagnostics?.mock === true
    ? 'Android 测试定位：系统 mock 标记保留；陀螺仪、加速度计及卫星原始数据未模拟。不保证融合定位采用测试源。'
    : 'iOS / 未连接：当前接口不提供 hAcc 设置、系统传感器或卫星原始数据注入；不保证第三方应用接受模拟位置。';
  $('injection-status').textContent = Object.entries(diagnostics?.injections || {}).map(([name, point]) =>
    `${name}: ${point.lat.toFixed(6)}, ${point.lng.toFixed(6)} · 测试 hAcc ${point.accuracy_m} m`).join(' / ');
  const states = {idle:'等待连接',ready:'准备就绪',playing:'正在移动',paused:'已暂停',completed:'已到达终点',error:'运行错误',connecting:'连接中'};
  $('play-state').textContent = states[data.state] || data.state;
  $('live-speed').textContent = `${data.speed_kmh.toFixed(2)} km/h`;
  $('progress').value = data.total_m ? 100*data.distance_m/data.total_m : 0;
  $('progress-text').textContent = `${data.distance_m.toFixed(1)} / ${data.total_m.toFixed(1)} m · ${data.elapsed_s.toFixed(1)} s · ${data.laps} 圈`;
  $('loaded-route').textContent = data.route.points.length ? `${data.route.name} · ${data.route.points.length} 节点` : '未载入路线';
  const changed = JSON.stringify(loaded) !== JSON.stringify(data.route.points);
  loaded = data.route.points;
  if (changed && mode === 'player') renderRoute();
  if (!initialized) { fillSettings(data.settings); initialized = true; }
  const displayedPosition = data.real_current || data.current;
  if (displayedPosition) {
    $('position').textContent = data.real_current
      ? `手机实测：${data.real_current.lat.toFixed(6)}, ${data.real_current.lng.toFixed(6)}`
      : `已发送：${data.current.lat.toFixed(6)}, ${data.current.lng.toFixed(6)}`;
    if (map) {
      liveMarker.setLatLng(coord(displayedPosition));
      if (!map.hasLayer(liveMarker)) liveMarker.addTo(map);
      if (firstPosition || (data.real_current && !status?.real_current)) locatePhone();
      else if ($('follow').checked && mode === 'player') map.panTo(coord(displayedPosition));
    }
  } else { $('position').textContent = '尚未发送模拟坐标'; if (liveMarker) liveMarker.remove(); }
  controls();
}
async function poll() {
  try { renderStatus(await api('status')); }
  catch (e) { $('service').textContent = '本地服务不可用'; message(e.message,'error'); }
  setTimeout(poll,1000);
}
async function uploadRoute(points, name) {
  renderStatus(await api('route',{points,name})); setMode('player');
  if (status.connected && status.current) locatePhone(); else fit();
  message(status.connected ? '路线已载入，已发送起点坐标。可调整参数后开始。' : '路线已载入并保存，连接手机后将发送起点坐标。','success');
}
async function importFile(file, target) {
  if (!file) return;
  if (file.size > 2000000) throw new Error('GPX 文件不能超过 2 MB');
  const route = await api('import',{gpx:await file.text(),name:file.name.replace(/\.gpx$/i,'')});
  if (target === 'editor') { draft=route.points; $('route-name').value=route.name; edited(); fit(); }
  else await uploadRoute(route.points,route.name);
}
function exportRoute() {
  const escape = str => str.replace(/[<>&"']/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&apos;'}[c]));
  const name = $('route-name').value || 'route';
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Route Studio" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>${escape(name)}</name><trkseg>\n${draft.map(p=>`<trkpt lat="${p.lat.toFixed(8)}" lon="${p.lng.toFixed(8)}"/>`).join('\n')}\n</trkseg></trk></gpx>`;
  const url=URL.createObjectURL(new Blob([xml],{type:'application/gpx+xml'})), a=document.createElement('a');
  a.href=url; a.download=name.replace(/[\\/:*?"<>|]/g,'_')+'.gpx'; document.body.append(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),10000); message(`已导出 ${draft.length} 个节点。运动参数在回放页单独设置。`,'success');
}
$('tab-editor').onclick=()=>setMode('editor'); $('tab-player').onclick=()=>{setMode('player');if(status?.connected && status.current) locatePhone(); else fit();};
$('route-name').oninput=saveDraft;
$('fit').onclick=fit;
$('locate-phone').onclick=locatePhone;
$('follow').onchange=()=>{if($('follow').checked) locatePhone();};
$('undo').onclick=()=>{draft.pop();edited();}; $('clear').onclick=()=>{draft=[];edited();};
$('add-coordinate').onclick=()=>operation('添加节点…',async()=>addNode(Number($('node-lat').value),Number($('node-lng').value)));
$('export').onclick=exportRoute;
$('use-route').onclick=()=>operation('载入路线…',()=>uploadRoute(draft,$('route-name').value||'Route'));
$('clear-loaded-route').onclick=()=>operation('正在清空已载入路线…',async()=>{
  renderStatus(await api('clear-route',{}));
  message('已清空回放路线并停止模拟定位；编辑草稿未受影响。','success');
});
for (const target of ['editor','player']) {
  $(`${target}-import`).onclick=()=>$(`${target}-file`).click();
  $(`${target}-file`).onchange=e=>{const file=e.target.files[0]; e.target.value=''; operation('解析 GPX…',()=>importFile(file,target));};
}
$('speed').oninput=()=>{if(Number($('speed').value)>0)$('pace').value=+(60/Number($('speed').value)).toFixed(4);};
$('pace').oninput=()=>{if(Number($('pace').value)>0)$('speed').value=+(60/Number($('pace').value)).toFixed(4);};
$('settings').onsubmit=e=>{e.preventDefault();operation('保存参数…',async()=>{renderStatus(await api('settings',settings()));message('参数已保存；随机种子在下次重新开始时生效。','success');});};
$('place-search').onclick=()=>operation('搜索地点…',async()=>{const query=$('place-query').value.trim();const result=await api('search',{query});renderPlaceResults(result.results);if(result.results.length){$('place-results').selectedIndex=0;const p=result.results[0];map.setView([p.lat,p.lng],16,{animate:false});message(`找到 ${result.results.length} 个地点，请选择后切换定位。`,'success');}else message('没有找到匹配地点。','error');});
$('place-query').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('place-search').click();}};
$('place-results').onchange=()=>{const p=placeResults[$('place-results').selectedIndex];if(p){map.setView([p.lat,p.lng],16,{animate:false});}controls();};
$('place-switch').onclick=()=>operation('切换手机定位…',async()=>{const p=placeResults[$('place-results').selectedIndex];if(!p)throw new Error('请选择搜索结果');renderStatus(await api('position',{lat:p.lat,lng:p.lng}));locatePhone();message(`已切换到：${p.name}`,'success');});
function connectionOptions() {
  const wireless = $('transport').value === 'wireless', android = $('platform').value === 'android';
  $('ios-wireless').hidden = !wireless || android;
  $('android-wireless').hidden = !wireless || !android;
  $('android-test-options').hidden = !android;
  $('devices').hidden = wireless;
  $('connection-help').textContent = android
    ? '需要 ADB 和已授权设备；自动检测系统测试定位接口（建议 Android 12+）。无需 root/APK，不支持的 ROM 会明确报错。'
    : 'iPhone 需要已配对且开发者服务可用。无线地址模式连接现有 RSD 隧道。';
  if (status) renderStatus(status);
  controls();
}
$('platform').onchange = connectionOptions;
$('transport').onchange = connectionOptions;
$('devices').onchange = controls;
$('pair-device').onclick = () => operation('正在配对 Android…', async () => {
  const code = $('pair-code').value; $('pair-code').value = '';
  await api('pair', {address:$('pair-address').value.trim(), code});
  message('配对成功，请使用无线调试连接地址连接手机。', 'success');
});
$('connect').onclick=()=>operation('正在建立手机定位连接…',async()=>{
  const data = {platform:$('platform').value};
  if (data.platform === 'android') {
    for (const input of $('android-test-options').querySelectorAll('input')) {
      if (!input.value || !input.reportValidity()) throw new Error('请输入有效的 Android 测试参数');
    }
    data.android_options = {provider:$('android-provider').value,
      gps_accuracy:Number($('gps-accuracy').value), network_accuracy:Number($('network-accuracy').value),
      network_interval:Number($('network-interval').value)};
  }
  if ($('transport').value === 'auto') data.udid = $('devices').value;
  else if (data.platform === 'android') {
    data.address = $('adb-address').value.trim();
    if (!data.address) throw new Error('请输入无线调试连接地址');
  } else {
    data.rsd_host = $('rsd-host').value.trim(); data.rsd_port = Number($('rsd-port').value);
    if (!data.rsd_host || !data.rsd_port) throw new Error('请输入 RSD 地址和端口');
  }
  renderStatus(await api('connect',data));
  message(status.current?'定位服务已连接，起点已发送。':'定位服务已连接，请导入路线。','success');
});
$('start').onclick=()=>{
  if (!$('settings').reportValidity()) return;
  operation('启动回放…',async()=>{await api('settings',settings());renderStatus(await api('start',{}));message('开始发送模拟位置。','success');});
};
for (const [id,text] of [['pause','已暂停，当前位置保持不变。'],['stop','已停止并请求清除模拟定位。'],['disconnect','已断开定位服务。']]) {
  $(id).onclick=()=>operation('执行中…',async()=>{renderStatus(await api(id,{}));message(text,'success');});
}
try {
  const saved=JSON.parse(localStorage.getItem('route-studio-draft-v2')||'null');
  if(saved && Array.isArray(saved.points) && saved.points.length<=10000 && saved.points.every(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lng)&&Math.abs(p.lat)<=85&&Math.abs(p.lng)<=180)){
    draft=saved.points;$('route-name').value=saved.name||'我的路线';
  }
} catch { message('旧草稿无法读取，已打开空白编辑器。','error'); }
try {
  map=L.map('map',{worldCopyJump:true}).setView([31.2304,121.4737],15);
  createBasemap(map, $('map-warning'), $('retry-map'));
  routeLine=L.polyline([],{color:'#d55b32',weight:4}).addTo(map);
  liveMarker=L.circleMarker([0,0],{radius:15,color:'#d55b32',weight:3,fillColor:'#d55b32',fillOpacity:.35,interactive:false});
  map.on('click', e=>{if(mode==='editor'){try{const p=e.latlng.wrap();addNode(p.lat,p.lng);}catch(error){message(error.message,'error');}}});
  setMode('editor');fit();
} catch(e) { message(`地图初始化失败：${e.message}。手机控制仍可使用。`,'error'); }
poll();
