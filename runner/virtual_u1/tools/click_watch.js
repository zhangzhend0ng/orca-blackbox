// click_watch.js — watch WS frames / window.open / nav / exceptions while
// clicking a semantics node by its text. NO page reload.
// Usage: node click_watch.js <page_ws_url> <buttonText> [watch_ms]
const url = process.argv[2];
const text = process.argv[3] || 'Control';
const watchMs = parseInt(process.argv[4] || '9000', 10);

const ws = new WebSocket(url);
const evts = [];
let mid = 0;
const send = (m, p) => ws.send(JSON.stringify({ id: ++mid, method: m, params: p || {} }));

ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.method === 'Network.webSocketFrameSent') evts.push('SENT ' + m.params.response.payloadData.substring(0, 140));
  else if (m.method === 'Page.windowOpen') evts.push('WINDOW-OPEN ' + JSON.stringify(m.params).substring(0, 180));
  else if (m.method === 'Page.frameNavigated' && !m.params.frame.parentId) evts.push('NAV ' + (m.params.frame.url || '').substring(0, 120));
  else if (m.method === 'Runtime.exceptionThrown') evts.push('EXC ' + ((m.params.exceptionDetails.exception || {}).description || '').substring(0, 200));
  else if (m.method === 'Network.requestWillBeSent') {
    const u = m.params.request.url;
    if (!u.includes('flutter_web') && !u.includes('assets/')) evts.push('HTTP ' + m.params.request.method + ' ' + u.substring(0, 120));
  }
};

ws.onopen = () => {
  send('Network.enable');
  send('Runtime.enable');
  send('Page.enable');
  setTimeout(() => {
    send('Runtime.evaluate', {
      expression: `(() => { const n = document.querySelectorAll('flt-semantics'); for (const x of n) { if ((x.textContent||'').trim()==='${text}') { x.click(); return 'clicked'; } } return 'notfound'; })()`
    });
  }, 400);
};
setTimeout(() => {
  console.log(evts.length ? evts.slice(0, 40).join('\n') : '(no ws frames / window opens / http / exceptions)');
  process.exit(0);
}, watchMs);
