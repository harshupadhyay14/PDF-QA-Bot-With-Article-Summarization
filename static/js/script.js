// script.js — DocMind

document.addEventListener('DOMContentLoaded', () => {

function showStatus(msg) {
  const statusBar = document.getElementById('status-bar');
  const statusMsg = document.getElementById('status-msg');
  if (!statusBar || !statusMsg) return;
  statusMsg.textContent = msg;
  statusBar.hidden = false;
}
function hideStatus() {
  const statusBar = document.getElementById('status-bar');
  if (!statusBar) return;
  statusBar.hidden = true;
}

// ─── Copy buttons ────────────────────────────────────────────
function setupCopy(btnId, textId) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById(textId).textContent);
      const orig = btn.innerHTML;
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
      setTimeout(() => { btn.innerHTML = orig; }, 2000);
    } catch(_) {}
  });
}
setupCopy('qa-copy', 'qa-answer');
setupCopy('sum-copy', 'sum-text');

// ─── Multi-file handling ─────────────────────────────────────
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList  = document.getElementById('file-list');
let selectedFiles = [];

function renderFiles() {
  if (!fileList) return;
  fileList.innerHTML = '';
  selectedFiles.forEach((f, idx) => {
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `
      <svg class="file-chip-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
      <span class="file-chip-name">${f.name}</span>
      <button class="file-chip-remove" data-idx="${idx}">✕</button>`;
    fileList.appendChild(chip);
  });
  if (dropZone) dropZone.hidden = selectedFiles.length > 0;
  fileList.querySelectorAll('.file-chip-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedFiles.splice(parseInt(btn.dataset.idx), 1);
      renderFiles();
    });
  });
}

function addFiles(newFiles) {
  for (const f of newFiles) {
    const ext = f.name.split('.').pop().toLowerCase();
    if (!['pdf','docx'].includes(ext)) { alert(`Skipped "${f.name}" — only PDF/DOCX supported.`); continue; }
    if (!selectedFiles.find(x => x.name === f.name)) selectedFiles.push(f);
  }
  renderFiles();
}

if (fileInput) {
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) addFiles(Array.from(fileInput.files));
  });
}

if (dropZone) {
  ['dragenter','dragover'].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add('dragover'); }));
  ['dragleave','drop'].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove('dragover'); }));
  dropZone.addEventListener('drop', e => { if (e.dataTransfer.files.length) addFiles(Array.from(e.dataTransfer.files)); });
}

const questionInput = document.getElementById('question-input');
const qaSubmit = document.getElementById('qa-submit');
if (questionInput && qaSubmit) {
  questionInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') qaSubmit.click();
  });
}

// ─── Q&A ─────────────────────────────────────────────────────
if (qaSubmit) {
  qaSubmit.addEventListener('click', async () => {
    const question = document.getElementById('question-input').value.trim();
    if (!selectedFiles.length) { alert('Please upload at least one PDF or DOCX file.'); return; }
    if (!question) { alert('Please type a question.'); return; }

    document.getElementById('qa-result').hidden = true;
    qaSubmit.disabled = true;
    showStatus('Extracting text and querying AI…');

    const form = new FormData();
    selectedFiles.forEach(f => form.append('files', f));
    form.append('question', question);

    try {
      const res  = await fetch('/qa', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      document.getElementById('qa-answer').textContent = data.answer || '(No answer)';
      document.getElementById('qa-result').hidden = false;
      if (data.history) renderHistory(data.history);
    } catch(err) { alert('Error: ' + err.message); }
    finally { qaSubmit.disabled = false; hideStatus(); }
  });
}

// ─── Summarizer ───────────────────────────────────────────────
const summarizeSubmit = document.getElementById('summarize-submit');
if (summarizeSubmit) {
  summarizeSubmit.addEventListener('click', async () => {
    const url = document.getElementById('url-input').value.trim();
    if (!url) { alert('Please paste an article URL.'); return; }
    try { new URL(url); } catch(_) { alert('Please enter a valid URL.'); return; }

    document.getElementById('sum-result').hidden = true;
    summarizeSubmit.disabled = true;
    showStatus('Fetching article and generating summary…');

    try {
      const res  = await fetch('/summarize', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ url }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      document.getElementById('sum-text').textContent = data.summary || '(No summary)';
      document.getElementById('sum-result').hidden = false;
      if (data.history) renderHistory(data.history);
    } catch(err) { alert('Error: ' + err.message); }
    finally { summarizeSubmit.disabled = false; hideStatus(); }
  });
}

// ─── History ──────────────────────────────────────────────────
function renderHistory(history) {
  const list  = document.getElementById('history-list');
  const empty = document.getElementById('history-empty');
  const count = document.getElementById('history-count');
  if (!list || !empty || !count) return;

  count.textContent = history.length;
  if (!history.length) { empty.hidden = false; list.innerHTML = ''; list.appendChild(empty); return; }
  empty.hidden = true;
  list.innerHTML = '';

  [...history].reverse().forEach(item => {
    const el = document.createElement('div');
    el.className = 'history-item';
    if (item.type === 'qa') {
      const files = (item.files || []).join(', ');
      el.innerHTML = `
        <div class="history-item-header">
          <span class="history-badge badge-qa">Q&A</span>
          <span class="history-time">${item.timestamp || ''}</span>
        </div>
        ${files ? `<div class="history-files">📄 ${files}</div>` : ''}
        <div class="history-q">Q: ${escHtml(item.question)}</div>
        <div class="history-a">${escHtml(item.answer)}</div>`;
    } else {
      el.innerHTML = `
        <div class="history-item-header">
          <span class="history-badge badge-sum">Summary</span>
          <span class="history-time">${item.timestamp || ''}</span>
        </div>
        <div class="history-files">🌐 ${escHtml(item.url)}</div>
        <div class="history-a">${escHtml(item.summary)}</div>`;
    }
    list.appendChild(el);
  });
}

function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

fetch('/history').then(r => r.json()).then(renderHistory).catch(() => {});

// ─── Clear history ────────────────────────────────────────────
const clearBtn = document.getElementById('clear-history-btn');
if (clearBtn) {
  clearBtn.addEventListener('click', async () => {
    if (!confirm('Clear all history?')) return;
    await fetch('/history/clear', { method: 'POST' });
    renderHistory([]);
  });
}

// ─── Export PDF ───────────────────────────────────────────────
const exportBtn = document.getElementById('export-pdf-btn');
if (exportBtn) {
  exportBtn.addEventListener('click', async () => {
    const histRes = await fetch('/history');
    const history = await histRes.json();
    if (!history.length) { alert('No history to export yet.'); return; }

    showStatus('Generating PDF export…');
    try {
      const res = await fetch('/export-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ history })
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error || res.statusText);
      }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = `docmind-export.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch(err) { alert('Export failed: ' + err.message); }
    finally { hideStatus(); }
  });
}

}); // end DOMContentLoaded