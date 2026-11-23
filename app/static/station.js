const layout = document.querySelector('#selection');
const scene = layout.querySelector('#scenario');
const originalScene = scene.value;
const work = layout.querySelector('#work-lot');
const archived = layout.querySelector('#scope-run');
scene.addEventListener('change', () => {
  const changed = scene.value !== originalScene;
  work.disabled = changed;
  if (archived) archived.disabled = changed;
});
document.querySelector('#print').addEventListener('click', () => print());
const commit = document.querySelector('#commit');
commit?.addEventListener('click', async () => {
  const message = document.querySelector('#message');
  const { key, sample, view } = commit.dataset;
  commit.disabled = true;
  message.textContent = '核对秤单中…';
  try {
    const response = await (key
      ? fetch(`/api/runs/${key}/rerun`, { method:'POST' })
      : fetch('/api/runs', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({sample}) }));
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || '卷联保存失败');
    if (key) message.textContent = '复算一致，称签仍用原卷。';
    else {
      const query = new URLSearchParams({ run:result.id, sample, work:work.value });
      location.assign(`/ledger/${view}?${query}`);
    }
  } catch (error) {
    message.textContent = `${error.message}，请重试。`;
  } finally { commit.disabled = false; }
});
const recallCommit = document.querySelector('#recall-commit');
recallCommit?.addEventListener('click', async () => {
  const message = document.querySelector('#recall-message');
  const { key, sample, origin } = recallCommit.dataset;
  const reference = document.querySelector('#recall-ref')?.value ?? '';
  recallCommit.disabled = true;
  message.textContent = '召回登记中…';
  try {
    let run = key;
    if (!run) {
      const saved = await fetch('/api/runs', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({sample}) });
      const archive = await saved.json();
      if (!saved.ok) throw new Error(archive.message || '卷联保存失败');
      run = archive.id;
    }
    const response = await fetch('/api/recalls', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({run, origin, reference}) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || '召回登记失败');
    if (result.reused) message.textContent = '同一份召回记录已在柜，未重复扣留。';
    else {
      const query = new URLSearchParams({ run, sample, origin, recall:result.id, work:work.value });
      location.assign(`/ledger/recall?${query}`);
    }
  } catch (error) {
    message.textContent = `${error.message}，请重试。`;
  } finally { recallCommit.disabled = false; }
});
