const API = 'http://localhost:3000';

// ── Nav ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById(`panel-${item.dataset.panel}`).classList.add('active');
    if (item.dataset.panel === 'sessions') loadSessions();
  });
});

// ── Health ────────────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    document.getElementById('api-status').textContent =
      d.status === 'ok' ? `online · ${d.model}` : 'degraded';
  } catch {
    document.getElementById('api-status').textContent = 'offline';
  }
}
checkHealth();
setInterval(checkHealth, 30000);

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderMd(text) {
  return typeof marked !== 'undefined' ? marked.parse(text) : esc(text).replace(/\n/g,'<br>');
}

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

// ── Thread management ─────────────────────────────────────────────────────────
let currentThreadId = localStorage.getItem('air_thread') || genId();
localStorage.setItem('air_thread', currentThreadId);

// ── Chat ──────────────────────────────────────────────────────────────────────
const chatBody  = document.getElementById('chat-body');
const chatInput = document.getElementById('chat-input');
const btnSend   = document.getElementById('btn-send');

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 130) + 'px';
});

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
btnSend.addEventListener('click', sendMessage);

function addMsg(role, content = '', sources = []) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;

  let bodyContent = '';
  if (role === 'assistant') {
    bodyContent = renderMd(content);
  } else if (role === 'system') {
    bodyContent = esc(content);
  } else {
    bodyContent = esc(content).replace(/\n/g, '<br>');
  }

  el.innerHTML = `<div class="msg-role">${role}</div><div class="msg-body">${bodyContent}</div>`;

  if (sources.length) {
    const wrap = document.createElement('div');
    wrap.className = 'sources-wrap';
    const items = sources.map(s => {
      let domain = s.url;
      try { domain = new URL(s.url).hostname.replace('www.',''); } catch(e) {}
      return `<div class="src-item">
        <div class="src-num">[${s.index}]</div>
        <div class="src-title">${esc(s.title || 'Untitled')}</div>
        <a class="src-url" href="${s.url}" target="_blank" rel="noreferrer">${domain}</a>
        <div class="src-snippet">${esc((s.snippet||'').slice(0,120))}</div>
      </div>`;
    }).join('');
    wrap.innerHTML = `
      <div class="sources-toggle" onclick="toggleSrc(this)">&#9658; ${sources.length} sources used</div>
      <div class="sources-list hidden"><div class="src-grid">${items}</div></div>`;
    el.querySelector('.msg-body').appendChild(wrap);
  }

  chatBody.appendChild(el);
  chatBody.scrollTop = chatBody.scrollHeight;
  return el;
}

window.toggleSrc = function(t) {
  const list = t.nextElementSibling;
  const hidden = list.classList.toggle('hidden');
  t.innerHTML = (hidden ? '&#9658;' : '&#9660;') + t.innerHTML.slice(t.innerHTML.indexOf(' '));
};

function addProgress() {
  const el = document.createElement('div');
  el.className = 'msg assistant';
  el.innerHTML = `<div class="msg-role">assistant</div>
    <div class="msg-body">
      <div class="node-row"><div class="spinner"></div><span id="node-label">thinking…</span></div>
    </div>`;
  chatBody.appendChild(el);
  chatBody.scrollTop = chatBody.scrollHeight;
  return el;
}

const NODE_LABELS = {
  route_query:       '🔀 routing query…',
  tavily_search:     '🔍 searching web…',
  fetch_and_extract: '📄 reading top results…',
  generate_answer:   '✍️ generating answer…',
};

async function sendMessage() {
  const q = chatInput.value.trim();
  if (!q || btnSend.disabled) return;

  addMsg('user', q);
  chatInput.value = '';
  chatInput.style.height = 'auto';
  btnSend.disabled = true;

  const progressEl = addProgress();
  const nodeLabel  = progressEl.querySelector('#node-label');
  let   answerEl   = null;
  let   answerBody = null;
  let   answerText = '';

  try {
    const res = await fetch(`${API}/api/query/stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question: q, thread_id: currentThreadId }),
    });

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.event === 'node') {
            if (nodeLabel) nodeLabel.textContent = NODE_LABELS[data.node] || data.node;
          }

          if (data.event === 'answer') {
            if (!answerEl) {
              progressEl.remove();
              answerEl   = addMsg('assistant', '');
              answerBody = answerEl.querySelector('.msg-body');
              answerBody.innerHTML = '<span class="cursor"></span>';
            }
            answerText += data.token;
            answerBody.innerHTML = renderMd(answerText) + '<span class="cursor"></span>';
            chatBody.scrollTop = chatBody.scrollHeight;
          }

          if (data.event === 'sources' && answerEl) {
            answerBody.innerHTML = renderMd(answerText);
            if (data.sources?.length) {
              const wrap = document.createElement('div');
              wrap.className = 'sources-wrap';
              const items = data.sources.map(s => {
                let domain = s.url;
                try { domain = new URL(s.url).hostname.replace('www.',''); } catch(e) {}
                return `<div class="src-item">
                  <div class="src-num">[${s.index}]</div>
                  <div class="src-title">${esc(s.title||'Untitled')}</div>
                  <a class="src-url" href="${s.url}" target="_blank" rel="noreferrer">${domain}</a>
                  <div class="src-snippet">${esc((s.snippet||'').slice(0,120))}</div>
                </div>`;
              }).join('');
              wrap.innerHTML = `
                <div class="sources-toggle" onclick="toggleSrc(this)">&#9658; ${data.sources.length} sources used</div>
                <div class="sources-list hidden"><div class="src-grid">${items}</div></div>`;
              answerBody.appendChild(wrap);
            }
          }

          if (data.event === 'error') {
            progressEl.remove();
            addMsg('system', `Error: ${data.detail}`);
          }

        } catch {}
      }
    }
  } catch (err) {
    progressEl.remove();
    addMsg('system', `Connection error: ${err.message}`);
  }

  btnSend.disabled = false;
  chatInput.focus();
}

// ── Search panel ──────────────────────────────────────────────────────────────
const dropZone    = document.getElementById('image-drop-zone');
const fileInput   = document.getElementById('search-image-file');
const previewWrap = document.getElementById('preview-wrap');
const previewImg  = document.getElementById('preview-img');
const btnRemove   = document.getElementById('btn-remove-img');
let   imageB64    = null;

// Drag and drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) loadImage(file);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) loadImage(fileInput.files[0]);
});

function loadImage(file) {
  const reader = new FileReader();
  reader.onload = e => {
    const dataUrl = e.target.result;
    imageB64 = dataUrl.split(',')[1];
    previewImg.src = dataUrl;
    previewWrap.style.display = 'block';
    dropZone.querySelector('.upload-hint').textContent = 'Click to change image';
  };
  reader.readAsDataURL(file);
}

btnRemove.addEventListener('click', e => {
  e.stopPropagation();
  imageB64 = null;
  fileInput.value = '';
  previewWrap.style.display = 'none';
  previewImg.src = '';
  dropZone.querySelector('.upload-hint').textContent = 'Drop image here or click to upload';
});

document.getElementById('btn-search').addEventListener('click', async () => {
  const url    = document.getElementById('search-url').value.trim();
  const query  = document.getElementById('search-query').value.trim();
  const status = document.getElementById('search-status');
  const result = document.getElementById('search-result');

  if (!url || !query) {
    status.className = 'status-box error';
    status.textContent = 'URL and query are both required.';
    return;
  }

  document.getElementById('btn-search').disabled = true;
  status.className = 'status-box loading';

  let statusText = `Fetching ${new URL(url).hostname}…`;
  if (imageB64) statusText += ' · Analysing image…';
  status.textContent = statusText;

  result.classList.remove('visible');

  try {
    const payload = { url, query };
    if (imageB64) payload.image_b64 = imageB64;

    const res  = await fetch(`${API}/api/search`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Search failed');

    status.className = 'status-box';

    let domain = url;
    try { domain = new URL(url).hostname.replace('www.',''); } catch(e) {}

    document.getElementById('result-title').textContent = data.title || domain;
    const linkEl = document.getElementById('result-link');
    linkEl.href        = url;
    linkEl.textContent = `${domain} ↗`;

    document.getElementById('result-answer').innerHTML = renderMd(data.answer);
    result.classList.add('visible');

  } catch (err) {
    status.className = 'status-box error';
    status.textContent = `Error: ${err.message}`;
  }

  document.getElementById('btn-search').disabled = false;
});

// ── Sessions ──────────────────────────────────────────────────────────────────
let activeSessionId = null;

async function loadSessions() {
  try {
    const res  = await fetch(`${API}/api/session`);
    const data = await res.json();
    const container = document.getElementById('sessions-items');

    if (!Array.isArray(data) || !data.length) {
      container.innerHTML = '<div class="no-sessions">No sessions yet</div>';
      return;
    }

    container.innerHTML = data.map(s => `
      <div class="session-item ${s.thread_id === activeSessionId ? 'active' : ''}"
           data-id="${s.thread_id}"
           onclick="loadSessionDetail('${s.thread_id}', this)">
        <div class="session-name">${esc(s.session_name)}</div>
        <div class="session-date">${s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}</div>
      </div>`).join('');
  } catch {
    document.getElementById('sessions-items').innerHTML =
      '<div class="no-sessions">Failed to load</div>';
  }
}

window.loadSessionDetail = async function(threadId, el) {
  activeSessionId = threadId;
  document.querySelectorAll('.session-item').forEach(i => i.classList.remove('active'));
  if (el) el.classList.add('active');

  const detail = document.getElementById('sessions-detail');
  detail.innerHTML = '<div class="empty-state"><div class="spinner"></div>Loading…</div>';

  try {
    const res  = await fetch(`${API}/api/session/${encodeURIComponent(threadId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);

    const msgs = (data.messages || []).map(m => `
      <div class="session-msg">
        <div class="session-msg-role ${m.role}">${m.role}</div>
        <div class="session-msg-content">${esc(m.content).replace(/\n/g,'<br>')}</div>
      </div>`).join('');

    detail.innerHTML = `
      <div class="session-actions">
        <button class="btn-sm" onclick="continueSession('${threadId}')">Continue in Chat</button>
        <button class="btn-sm danger" onclick="deleteSession('${threadId}')">Clear</button>
      </div>
      <div style="font-family:var(--font-mono);font-size:11px;color:var(--muted2)">${esc(data.session_name)}</div>
      ${msgs || '<div class="empty-state"><div class="empty-icon">💬</div>No messages</div>'}`;
  } catch (e) {
    detail.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div>${e.message}</div>`;
  }
};

window.continueSession = function(threadId) {
  currentThreadId = threadId;
  localStorage.setItem('air_thread', threadId);
  document.querySelector('[data-panel="chat"]').click();
};

window.deleteSession = async function(threadId) {
  if (!confirm('Clear this session history?')) return;
  await fetch(`${API}/api/session/${encodeURIComponent(threadId)}`, { method: 'DELETE' });
  activeSessionId = null;
  document.getElementById('sessions-detail').innerHTML =
    '<div class="empty-state"><div class="empty-icon">🗑️</div>Cleared</div>';
  loadSessions();
};