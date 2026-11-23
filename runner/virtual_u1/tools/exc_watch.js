// exc_watch.js — watch exceptions/console while a click happens.
// Usage: node exc_watch.js <page_ws_url> <x> <y> [watch_ms]
const url = process.argv[2];
const x = parseFloat(process.argv[3] || '131');
const y = parseFloat(process.argv[4] || '291');
const watchMs = parseInt(process.argv[5] || '15000', 10);

const ws = new WebSocket(url);
const idMap = new Map();
let msgId = 0;
function send(method, params = {}) {
  return new Promise((res) => {
    const id = ++msgId;
    idMap.set(id, res);
    ws.send(JSON.stringify({ id, method, params }));
  });
}
const events = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && idMap.has(m.id)) { idMap.get(m.id)(m.result); idMap.delete(m.id); return; }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails;
    events.push('EXC ' + ((d.exception && (d.exception.description || d.exception.value)) || d.text || '').toString().substring(0, 500));
  } else if (m.method === 'Runtime.consoleAPICalled') {
    if (['error', 'warning', 'assert'].includes(m.params.type)) {
      events.push('CON-' + m.params.type + ' ' + m.params.args.map(a => (a.value || a.description || '').toString()).join(' ').substring(0, 300));
    }
  } else if (m.method === 'Log.entryAdded') {
    const e = m.params.entry;
    if (['error', 'warning'].includes(e.level)) events.push(`LOG-${e.level} ${e.text} ${e.url || ''}`.substring(0, 300));
  }
};
ws.onopen = async () => {
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Page.enable');
  console.log('armed; dispatching click at', x, y);
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  setTimeout(() => {
    console.log(events.length ? events.join('\n') : '(no exceptions/console errors captured)');
    process.exit(0);
  }, watchMs);
};
ws.onerror = () => { console.error('WS error'); process.exit(1); };
