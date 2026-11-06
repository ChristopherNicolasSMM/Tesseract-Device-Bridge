/* Run locally: node tests/js/test_layout_preferences.cjs */
'use strict';
const assert = require('node:assert/strict');
const api = require('../../reusable/ui_preferences/static/layout.js');
const custom = {version:1, mode:'custom', width:1640};
assert.deepEqual(api.normalize(custom), custom);
assert.equal(api.width(api.normalize({version:1, mode:'custom', width:99999})), '2560px');
assert.equal(api.width(api.normalize({version:1, mode:'custom', width:1})), '960px');
assert.equal(api.normalize({version:1, mode:'custom', width:'expression(alert(1))'}), null);
assert.equal(api.normalize({version:1, mode:'javascript:', width:1400}), null);
assert.equal(api.normalize({version:1, mode:'custom', width:Infinity}), null);
assert.equal(api.normalize({version:2, mode:'full', width:1400}), null);
assert.equal(api.width({mode:'full'}), '100%');
assert.equal(api.width(api.defaults()), null);
let cookie = '';
const localA = new Map(), localB = new Map();
function browser(storage) {
  return {getCookie:()=>cookie, setCookie:value=>{cookie=value.split(';')[0];},
    getItem:key=>storage.get(key), setItem:(key,value)=>storage.set(key,value)};
}
const setup = browser(localA), panel = browser(localB);
assert.equal(api.save(setup, custom), true);
assert.deepEqual(api.read(panel), custom); // Same-host cookie works across ports.
api.save(panel, {version:1, mode:'wide', width:1400});
assert.equal(api.read(setup).mode, 'wide');
api.save(panel, api.defaults());
assert.deepEqual(api.read(setup), api.defaults()); // Reset must beat stale storage on another port.
cookie = api.KEY + '=%malformed';
assert.deepEqual(api.read(setup), custom); // A corrupt cookie cannot inject CSS.
const denied = {getCookie(){throw Error();},setCookie(){throw Error();},getItem(){throw Error();},setItem(){throw Error();}};
assert.deepEqual(api.read(denied), api.defaults());
assert.equal(api.save(denied, custom), false);
const silent = {getCookie:()=>'',setCookie(){},getItem:()=>null,setItem(){}};
assert.equal(api.save(silent, custom), false);
console.log('Layout preference behavior: OK');
