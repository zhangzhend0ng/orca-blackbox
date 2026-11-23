// Watch WebSocket + request activity of the CLI web app via CDP.
// Usage: node ws_watch.js <page_ws_url> [watch_ms]
const url = process.argv[2];
const watchMs = parseInt(process.argv[3] || '20000', 10);

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
  if (m.method === 'Network.webSocketCreated') {
    events.push(`WS-CREATE ${m.params.url}`);
  } else if (m.method === 'Network.webSocketClosed') {
    events.push(`WS-CLOSE id=${m.params.identifier}`);
  } else if (m.method === 'Network.webSocketFrameSent') {
    const d = m.params.response.payloadData;
    events.push(`WS-SENT ${d.substring(0, 160)}`);
  } else if (m.method === 'Network.webSocketFrameReceived') {
    const d = m.params.response.payloadData;
    if (d.includes('notify') || d.includes('error') || events.filter(e => e.startsWith('WS-RECV')).length < 8) {
      events.push(`WS-RECV ${d.substring(0, 160)}`);
    }
  } else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    events.push('CONSOLE-ERR ' + m.params.args.map(a => a.value || a.description || '').join(' ').substring(0, 200));
  } else if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails;
    events.push('EXC ' + ((d.exception && d.exception.description) || d.text || '').substring(0, 200));
  } else if (m.method === 'Log.entryAdded' && (m.params.entry.level === 'error' || m.params.entry.level === 'warning')) {
    events.push(`LOG-${m.params.entry.level} ` + m.params.entry.text.substring(0, 200));
  }
};

ws.onopen = async () => {
  await send('Network.enable');
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Page.enable');
  await send('Page.reload', { ignoreCache: false });
  console.log('reloaded, watching for ' + watchMs + 'ms');
  setTimeout(async () => {
    console.log(events.slice(0, 80).join('\n'));
    console.log('--- total events:', events.length);
    process.exit(0);
  }, watchMs);
};
ws.onerror = (e) => { console.error('WS error', e.message || e); process.exit(1); };
