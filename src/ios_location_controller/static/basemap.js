'use strict';

function createBasemap(map, warning, retryButton) {
  const attribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const sources = [
    {url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png', options:{maxZoom:19, attribution}},
    {url:'https://tile.openstreetmap.de/{z}/{x}/{y}.png', options:{maxZoom:19, maxNativeZoom:18,
      attribution:`${attribution} · <a href="https://www.openstreetmap.de/">OpenStreetMap DE</a>`}}
  ];
  let active = null, pendingFallback = null;

  function notice(text, retry = false) {
    warning.textContent = text;
    warning.hidden = !text;
    retryButton.hidden = !retry;
  }

  function select(index) {
    if (pendingFallback !== null) clearTimeout(pendingFallback);
    pendingFallback = null;
    const previous = active;
    active = null;
    if (previous) previous.remove();
    const source = sources[index], failedTiles = new Set();
    const layer = L.tileLayer(source.url, source.options);
    active = layer;
    let hasLoaded = false;
    notice(index ? '主底图加载失败，正在加载备用底图…' : '');

    function recover(event) {
      if (active !== layer) return;
      failedTiles.delete(event.tile);
      if (hasLoaded && !failedTiles.size && pendingFallback === null) notice('');
    }

    layer.on('tileerror', event => {
      if (active !== layer) return;
      failedTiles.add(event.tile);
      if (index + 1 < sources.length) {
        notice('主底图加载失败，正在尝试备用底图…');
        if (pendingFallback === null) {
          // Defer removal until Leaflet finishes processing this tile event.
          pendingFallback = setTimeout(() => {
            pendingFallback = null;
            if (active === layer) select(index + 1);
          }, 0);
        }
      } else {
        notice('部分或全部底图暂时无法加载；可点击“重试底图”。节点编辑、坐标输入和回放仍可使用。', true);
      }
    });
    layer.on('tileload', event => {
      if (active !== layer) return;
      hasLoaded = true;
      recover(event);
    });
    layer.on('tileunload', recover);
    layer.addTo(map);
  }

  const retry = () => select(0);
  retryButton.onclick = retry;
  select(0);
  return {retry};
}
