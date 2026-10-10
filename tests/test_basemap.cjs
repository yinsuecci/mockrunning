const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
  const layers = [], timers = new Map(), map = {layers:new Set()};
  let nextTimer = 0;
  const warning = {hidden:true, textContent:''}, retry = {hidden:true};
  const context = vm.createContext({
    setTimeout(fn) { const id = ++nextTimer; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    L:{tileLayer(url, options) {
      const handlers = new Map();
      const layer = {
        url, options,
        on(name, fn) { handlers.set(name, fn); return this; },
        fire(name, tile = {}) { handlers.get(name)?.({tile}); },
        addTo(target) { target.layers.add(this); return this; },
        remove() { map.layers.delete(this); this.fire('tileunload'); }
      };
      layers.push(layer);
      return layer;
    }}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/ios_location_controller/static/basemap.js'), 'utf8'), context);
  context.createBasemap(map, warning, retry);
  return {layers, timers, map, warning, retry, flush() {
    const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn());
  }};
}

function useFallback(h) {
  h.layers[0].fire('tileerror');
  h.flush();
  return h.layers[1];
}

test('healthy primary tiles need no fallback or warning', () => {
  const h = setup();
  h.layers[0].fire('tileload');
  assert.equal(h.warning.hidden, true);
  assert.equal(h.retry.hidden, true);
  assert.equal(h.layers.length, 1);
  assert.equal(h.timers.size, 0);
});

test('a failed primary switches once and successful fallback clears the warning', () => {
  const h = setup();
  h.layers[0].fire('tileerror');
  h.layers[0].fire('tileerror');
  assert.equal(h.timers.size, 1);
  h.flush();
  const fallback = h.layers[1];
  assert.match(fallback.url, /tile\.openstreetmap\.de/);
  assert.equal(fallback.options.maxNativeZoom, 18);
  assert.equal(fallback.options.maxZoom, 19);
  assert.match(fallback.options.attribution, /OpenStreetMap DE/);
  assert.equal(h.map.layers.has(h.layers[0]), false);
  assert.equal(h.map.layers.has(fallback), true);
  fallback.fire('tileload');
  assert.equal(h.warning.hidden, true);
});

test('late errors from the removed primary do not change the recovered map', () => {
  const h = setup(), fallback = useFallback(h);
  fallback.fire('tileload');
  h.layers[0].fire('tileerror');
  assert.equal(h.warning.hidden, true);
  assert.equal(h.timers.size, 0);
  assert.equal(h.layers.length, 2);
});

test('both sources failing offers a manual retry and retries the primary', () => {
  const h = setup(), fallback = useFallback(h);
  fallback.fire('tileerror');
  assert.equal(h.warning.hidden, false);
  assert.equal(h.retry.hidden, false);
  assert.equal(h.timers.size, 0);
  h.retry.onclick();
  assert.equal(h.layers.length, 3);
  assert.match(h.layers[2].url, /tile\.openstreetmap\.org/);
  assert.equal(h.map.layers.size, 1);
  assert.equal(h.retry.hidden, true);
  h.layers[2].fire('tileload');
  assert.equal(h.warning.hidden, true);
});

test('one successful tile does not hide an outstanding partial failure', () => {
  const h = setup(), fallback = useFallback(h), missingTile = {};
  fallback.fire('tileerror', missingTile);
  fallback.fire('tileload');
  assert.equal(h.warning.hidden, false);
  fallback.fire('tileunload', missingTile);
  assert.equal(h.warning.hidden, true);
  assert.equal(h.retry.hidden, true);
});

test('a formerly failed tile recovering removes the stale error', () => {
  const h = setup(), fallback = useFallback(h), tile = {};
  fallback.fire('tileerror', tile);
  fallback.fire('tileload', tile);
  assert.equal(h.warning.hidden, true);
  assert.equal(h.retry.hidden, true);
});

test('manual retry cancels a pending fallback from the old layer', () => {
  const h = setup();
  h.layers[0].fire('tileerror');
  h.retry.onclick();
  h.flush();
  assert.equal(h.layers.length, 2);
  assert.match(h.layers[1].url, /tile\.openstreetmap\.org/);
  assert.equal(h.map.layers.size, 1);
});
