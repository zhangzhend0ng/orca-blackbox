// cdp.js — minimal CDP driver for the CLI web UI (Flutter/CanvasKit) over a
// --remote-debugging-port instance. Page state lives in the browser; each
// invocation attaches to the same page target and runs one command.
//
// Usage: node cdp.js [--port 9224] [--target <url/title substring>] [--watch [--post ms]] <cmd> [args]
//   --watch                    after the command, report WS frames / navigations /
//                              window.open / exceptions / non-asset HTTP for --post ms
//   nav <url> [settleMs]        navigate; wait for semantics, then settle
//   info                        visibility / rAF rate / glass pane / canvases
//   sem [--all]                 semantics nodes: id role label rect text listeners
//   eval <js> | eval -f <file>  evaluate (command-line API on: getEventListeners)
//   semclick <text-or-label>    click() first semantics node whose own text or
//                               aria-label equals the argument
//   xy <x> <y>                  real CDP mouse click at viewport coords
//   shot <out.png>              screenshot (PNG written to file)
//   targets                     list debuggable targets
const fs = require('fs');

const argv = process.argv.slice(2);
const opt = { port: 9224, target: null, watch: false, post: 5000, max: 200 };
const rest = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--port') opt.port = argv[++i];
  else if (argv[i] === '--target') opt.target = argv[++i];
  else if (argv[i] === '--watch') opt.watch = true;
  else if (argv[i] === '--post') opt.post = parseInt(argv[++i], 10);
  else if (argv[i] === '--max') opt.max = parseInt(argv[++i], 10);
  else rest.push(argv[i]);
}
const cmd = rest[0];
const args = rest.slice(1);

function die(msg) { console.error(msg); process.exit(2); }

// Side effects worth seeing while poking the UI: WS frames, page/iframe
// navigations, window.opens, uncaught exceptions, non-asset HTTP requests.
function describeEvent(m) {
  const p = m.params || {};
  const cut = (s) => String(s || '').substring(0, opt.max);
  if (m.method === 'Network.webSocketFrameSent') return 'WS> ' + cut((p.response || {}).payloadData);
  if (m.method === 'Network.webSocketFrameReceived') return 'WS< ' + cut((p.response || {}).payloadData);
  if (m.method === 'Network.webSocketCreated') return 'WS-CREATE ' + p.url;
  if (m.method === 'Network.webSocketClosed') return 'WS-CLOSE';
  if (m.method === 'Page.windowOpen') return 'WINDOW-OPEN ' + JSON.stringify(p).substring(0, 240);
  if (m.method === 'Page.frameNavigated') return 'NAV ' + (p.frame.parentId ? '(iframe) ' : '') + (p.frame.url || '').substring(0, 200);
  if (m.method === 'Page.frameAttached') return 'FRAME-ATTACHED ' + JSON.stringify(p).substring(0, 200);
  if (m.method === 'Runtime.exceptionThrown') return 'EXC ' + ((p.exceptionDetails.exception || {}).description || p.exceptionDetails.text || '').substring(0, 300);
  if (m.method === 'Runtime.consoleAPICalled' && (p.type === 'error' || p.type === 'warning')) return 'CONSOLE-' + p.type + ' ' + p.args.map((a) => a.value !== undefined ? String(a.value) : (a.description || a.type)).join(' ').substring(0, 300);
  if (m.method === 'Network.requestWillBeSent') {
    const u = p.request.url;
    return /flutter_web|assets\/|canvaskit|\.wasm|fonts|gstatic/.test(u) ? null : 'HTTP ' + p.request.method + ' ' + u.substring(0, 200);
  }
  if (m.method === 'Network.responseReceived' && p.response.status >= 400) return 'HTTP' + p.response.status + ' ' + p.response.url.substring(0, 200);
  return null;
}

async function pageWsUrl() {
  const list = await (await fetch(`http://127.0.0.1:${opt.port}/json/list`)).json();
  const pages = list.filter((t) => t.type === 'page');
  const t = opt.target
    ? pages.find((p) => p.url.includes(opt.target) || (p.title || '').includes(opt.target))
    : pages[0];
  if (!t) die('no page target' + (opt.target ? ` matching ${opt.target}` : '') + `; have: ` + pages.map((p) => p.url).join(' | '));
  return t.webSocketDebuggerUrl;
}

class Session {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.mid = 0;
    this.pending = new Map();
    this.events = [];
    this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = () => rej(new Error('ws error')); });
    this.ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && this.pending.has(m.id)) {
        const { res, rej } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? rej(new Error(m.method + ' ' + JSON.stringify(m.error))) : res(m.result);
      } else if (m.method) this.events.push(m);
    };
  }
  send(method, params) {
    const id = ++this.mid;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, includeCommandLineAPI: true });
    if (r.exceptionDetails) throw new Error('page exception: ' + ((r.exceptionDetails.exception || {}).description || JSON.stringify(r.exceptionDetails)).slice(0, 600));
    return r.result.value;
  }
  close() { this.ws.close(); }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(s, expression, timeoutMs, label) {
  const end = Date.now() + timeoutMs;
  for (;;) {
    let v = null;
    try { v = await s.evaluate(expression); } catch (e) { /* page may be mid-navigation */ }
    if (v) return v;
    if (Date.now() > end) throw new Error('timeout waiting for ' + (label || expression));
    await sleep(250);
  }
}

const SEM_DUMP = `(() => {
  const out = [];
  const vw = innerWidth, vh = innerHeight;
  for (const el of document.querySelectorAll('flt-semantics')) {
    const r = el.getBoundingClientRect();
    const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    const full = (el.textContent || '').trim();
    const role = el.getAttribute('role') || '';
    const label = el.getAttribute('aria-label') || '';
    let listeners = [];
    try { listeners = Object.keys(getEventListeners(el)); } catch (e) {}
    out.push({ id: el.getAttribute('id'), role, label, own, full: full.slice(0, 90),
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      flags: { disabled: el.getAttribute('aria-disabled'), hidden: el.getAttribute('aria-hidden'), expanded: el.getAttribute('aria-expanded') },
      listeners, offscreen: r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh });
  }
  return out;
})()`;

const INFO = `(async () => {
  let frames = 0; const stop = performance.now() + 1500;
  const tick = () => { frames++; if (performance.now() < stop) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  await new Promise((r) => setTimeout(r, 1700));
  const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height), cs.position, cs.pointerEvents, cs.visibility, cs.display]; };
  return { url: location.href, visibility: document.visibilityState, hidden: document.hidden, focus: document.hasFocus(),
    rafPer1500ms: frames, viewport: [innerWidth, innerHeight], dpr: devicePixelRatio,
    glass: rect(document.querySelector('flt-glass-pane')), view: rect(document.querySelector('flutter-view')),
    canvases: Array.from(document.querySelectorAll('canvas')).map((c) => [c.width, c.height, rect(c)]),
    semantics: { nodes: document.querySelectorAll('flt-semantics').length, placeholder: !!document.querySelector('flt-semantics-placeholder'), host: rect(document.querySelector('flt-semantics-host')) } };
})()`;

async function main() {
  const s = new Session(await pageWsUrl());
  await s.ready;
  await s.send('Page.enable'); await s.send('Runtime.enable');
  if (opt.watch) { await s.send('Network.enable'); s.events.length = 0; }
  let out;
  switch (cmd) {
    case 'targets': {
      out = await (await fetch(`http://127.0.0.1:${opt.port}/json/list`)).json();
      out = out.filter((t) => t.type === 'page').map((t) => ({ title: t.title, url: t.url }));
      break;
    }
    case 'nav': {
      if (!args[0]) die('nav <url>');
      await s.send('Page.navigate', { url: args[0] });
      await waitFor(s, `!!document.querySelector('flt-semantics-placeholder')`, 30000, 'flutter boot');
      // engine lazily builds the semantics tree only after the placeholder is clicked
      await s.evaluate(`document.querySelector('flt-semantics-placeholder').click()`);
      await waitFor(s, `document.querySelectorAll('flt-semantics').length > 0`, 15000, 'first semantics')
        .catch((e) => console.error('(warn) ' + e.message));
      await sleep(parseInt(args[1] || '2500', 10));
      out = await s.evaluate(INFO);
      break;
    }
    case 'info': out = await s.evaluate(INFO); break;
    case 'sem': {
      const all = args.includes('--all');
      let nodes = await s.evaluate(SEM_DUMP);
      if (!all) nodes = nodes.filter((n) => !n.offscreen);
      out = nodes;
      for (const n of nodes) {
        console.log(`#${n.id} [${n.role || '-'}] ${JSON.stringify(n.label)} rect=${n.rect} own=${JSON.stringify(n.own)} full=${JSON.stringify(n.full)} ${JSON.stringify(n.flags)} on=${n.listeners.join(',')}${n.offscreen ? ' OFFSCREEN' : ''}`);
      }
      out = null;
      break;
    }
    case 'eval': {
      const src = args[0] === '-f' ? fs.readFileSync(args[1], 'utf8') : args.join(' ');
      out = await s.evaluate(src);
      break;
    }
    case 'semclick': {
      const key = args[0];
      if (!key) die('semclick <text-or-label>');
      out = await s.evaluate(`(() => {
        const nodes = Array.from(document.querySelectorAll('flt-semantics'));
        const own = (el) => Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
        let hit = nodes.find((el) => (el.getAttribute('aria-label') || '') === ${JSON.stringify(key)} && (el.getAttribute('role') || '') !== 'label')
          || nodes.find((el) => own(el) === ${JSON.stringify(key)} || (el.textContent || '').trim() === ${JSON.stringify(key)});
        if (!hit) return 'NOTFOUND';
        const r = hit.getBoundingClientRect();
        hit.click();
        return 'clicked #' + hit.getAttribute('id') + ' role=' + hit.getAttribute('role') + ' label=' + hit.getAttribute('aria-label') + ' rect=' + [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
      })()`);
      break;
    }
    case 'semid': {
      // click the semantics node with id <n> (as printed by `sem`, with or without the prefix)
      const n = String(args[0] || '').replace(/^#?flt-semantic-node-/, '');
      if (!n) die('semid <id>');
      out = await s.evaluate(`(() => {
        const el = document.getElementById('flt-semantic-node-${n}');
        if (!el) return 'NOTFOUND';
        const r = el.getBoundingClientRect();
        let listeners = []; try { listeners = Object.keys(getEventListeners(el)); } catch (e) {}
        el.click();
        return 'clicked #${n} role=' + el.getAttribute('role') + ' label=' + JSON.stringify(el.getAttribute('aria-label')) + ' rect=' + [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] + ' on=' + listeners.join(',');
      })()`);
      break;
    }
    case 'move': {
      // real CDP mouse move (hover) to viewport coords
      const x = parseFloat(args[0]), y = parseFloat(args[1]);
      if (!(x >= 0) || !(y >= 0)) die('move <x> <y>');
      await s.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
      out = 'moved ' + x + ',' + y;
      break;
    }
    case 'xy': {
      const x = parseFloat(args[0]), y = parseFloat(args[1]);
      if (!(x >= 0) || !(y >= 0)) die('xy <x> <y>');
      for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
        await s.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
      }
      out = 'clicked ' + x + ',' + y;
      break;
    }
    case 'shot': {
      // shot <out.png> [x y w h scale] — clipped capture; scale 2+ keeps small
      // text legible for the Windows OCR engine
      if (!args[0]) die('shot <out.png> [x y w h scale]');
      const p = { format: 'png' };
      if (args.length >= 5) {
        p.clip = { x: parseFloat(args[1]), y: parseFloat(args[2]), width: parseFloat(args[3]), height: parseFloat(args[4]), scale: parseFloat(args[5] || '2') };
      }
      const r = await s.send('Page.captureScreenshot', p);
      fs.writeFileSync(args[0], Buffer.from(r.data, 'base64'));
      out = 'wrote ' + args[0];
      break;
    }
    default: die('unknown cmd: ' + cmd);
  }
  if (out !== null && out !== undefined) console.log(typeof out === 'string' ? out : JSON.stringify(out, null, 1));
  if (opt.watch) {
    await sleep(opt.post);
    const lines = s.events.map(describeEvent).filter(Boolean);
    console.log('--- events in ' + opt.post + 'ms: ' + (lines.length ? '\n' + lines.slice(0, 60).join('\n') : '(none)'));
  }
  // let the ws close handshake finish: process.exit on a closing handle trips a libuv assert
  await Promise.race([new Promise((r) => s.ws.addEventListener('close', r)), sleep(800)]);
  s.ws.close();
}

main().then(() => process.exit(0), (e) => die(String(e)));
