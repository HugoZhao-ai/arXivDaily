(() => {
  const $ = (selector) => document.querySelector(selector);
  const scope = new URL(document.body.dataset.root || './', location.href).pathname;
  const storageKey = `quant-reader:${scope}`;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch {}
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
  const persist = () => {
    try { localStorage.setItem(storageKey, JSON.stringify(saved)); }
    catch { $('#toast').textContent = '浏览器无法保存阅读记录；本次操作仍然有效。'; }
  };
  const entry = (id) => saved[id] ||= {};
  function paintButtons() {
    document.querySelectorAll('[data-save]').forEach(button => {
      const active = !!saved[button.dataset.save]?.star;
      button.textContent = active ? '★ 已收藏' : '☆ 收藏';
      button.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('[data-read]').forEach(button => {
      const active = !!saved[button.dataset.read]?.read;
      button.textContent = active ? '✓ 已读' : '标为已读';
      button.setAttribute('aria-pressed', String(active));
    });
  }
  document.addEventListener('click', event => {
    const save = event.target.closest('[data-save]');
    const read = event.target.closest('[data-read]');
    if (save) { entry(save.dataset.save).star = !entry(save.dataset.save).star; persist(); }
    if (read) { entry(read.dataset.read).read = !entry(read.dataset.read).read; persist(); }
    if (save || read) { paintButtons(); if ($('#feed')) filter(false); }
  });
  $('#theme-toggle')?.addEventListener('click', () => {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('quant-theme', theme); } catch {}
    $('#theme-toggle').textContent = theme === 'dark' ? '☀ 浅色' : '☾ 深色';
  });
  if ($('#theme-toggle')) $('#theme-toggle').textContent = document.documentElement.dataset.theme === 'dark' ? '☀ 浅色' : '☾ 深色';
  paintButtons();

  const cards = [...document.querySelectorAll('.paper-card')];
  let page = 1;
  const pageSize = 12;
  const controls = ['q', 'topic', 'researcher', 'period', 'reading', 'sort'];
  function filter(reset = true) {
    if (reset) page = 1;
    const values = Object.fromEntries(controls.map(key => [key, $('#' + key)?.value || '']));
    const terms = values.q.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    // Rolling date filters are relative to today, never to an old sample's newest paper.
    const cutoff = values.period ? new Date(Date.now() - Number(values.period) * 86400000).toISOString().slice(0, 10) : '';
    const matches = cards.filter(card => {
      const state = saved[card.dataset.id] || {};
      return terms.every(term => card.dataset.search.includes(term)) &&
        (!values.topic || card.dataset.topics.split(' ').includes(values.topic)) &&
        (!values.researcher || card.dataset.researchers.split(' ').includes(values.researcher)) &&
        (!cutoff || card.dataset.date >= cutoff) &&
        (!values.reading || (values.reading === 'saved' ? state.star : values.reading === 'read' ? state.read : !state.read));
    });
    matches.sort((a, b) => values.sort === 'relevance' ? Number(b.dataset.score) - Number(a.dataset.score) || b.dataset.date.localeCompare(a.dataset.date) :
      values.sort === 'updated' ? b.dataset.updated.localeCompare(a.dataset.updated) : b.dataset.date.localeCompare(a.dataset.date));
    page = Math.max(1, Math.min(page, Math.ceil(matches.length / pageSize)));
    cards.forEach(card => card.hidden = true);
    matches.slice((page - 1) * pageSize, page * pageSize).forEach(card => { card.hidden = false; $('#feed').append(card); });
    $('#result-count').textContent = `${matches.length} 篇论文`;
    $('#empty').hidden = matches.length > 0;
    $('#pagination').hidden = matches.length <= pageSize;
    $('#page-label').textContent = `${page} / ${Math.max(1, Math.ceil(matches.length / pageSize))}`;
    $('#prev').disabled = page === 1;
    $('#next').disabled = page * pageSize >= matches.length;
    const params = new URLSearchParams();
    for (const key of controls) if (values[key]) params.set(key, values[key]);
    history.replaceState(null, '', location.pathname + (params.size ? '?' + params : ''));
    document.querySelectorAll('[data-topic-link]').forEach(link => link.classList.toggle('selected', link.dataset.topicLink === values.topic));
  }
  if ($('#feed')) {
    const params = new URLSearchParams(location.search);
    controls.forEach(key => {
      if (params.has(key)) $('#' + key).value = params.get(key);
      $('#' + key).addEventListener(key === 'q' ? 'input' : 'change', () => filter());
    });
    document.querySelectorAll('[data-topic-link]').forEach(link => link.addEventListener('click', event => {
      event.preventDefault(); $('#topic').value = link.dataset.topicLink; filter();
    }));
    $('#clear').addEventListener('click', () => { controls.forEach(key => $('#' + key).value = ''); filter(); });
    $('#prev').addEventListener('click', () => { page--; filter(false); $('#results').scrollIntoView({behavior: 'smooth'}); });
    $('#next').addEventListener('click', () => { page++; filter(false); $('#results').scrollIntoView({behavior: 'smooth'}); });
    filter();
    document.addEventListener('keydown', event => {
      if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
        event.preventDefault(); $('#q').focus();
      }
    });
  }

  const paperId = document.body.dataset.paperId;
  if (paperId) {
    const previous = Number(saved[paperId]?.progress || 0);
    if (previous > .02 && previous < .98) {
      $('#resume').hidden = false;
      $('#resume').textContent = `继续上次阅读 · ${Math.round(previous * 100)}% ↓`;
      $('#resume').addEventListener('click', () => {
        scrollTo({top: previous * (document.documentElement.scrollHeight - innerHeight), behavior: 'smooth'});
        $('#resume').hidden = true;
      });
    }
    let timer;
    const recordProgress = () => {
      const height = document.documentElement.scrollHeight - innerHeight;
      const progress = height > 0 ? Math.min(1, Math.max(0, scrollY / height)) : 0;
      $('#reading-progress').value = progress;
      $('#progress-label').textContent = `${Math.round(progress * 100)}%`;
      entry(paperId).progress = progress;
      clearTimeout(timer); timer = setTimeout(persist, 200);
    };
    addEventListener('scroll', recordProgress, {passive: true});
    addEventListener('pagehide', persist);
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => entries.forEach(item => {
        if (item.isIntersecting) document.querySelectorAll('.toc a').forEach(link => link.classList.toggle('active', link.hash === '#' + item.target.id));
      }), {rootMargin: '-10% 0px -65% 0px'});
      document.querySelectorAll('.reading-section').forEach(section => observer.observe(section));
    }
  }
  $('#export')?.addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({version: 1, papers: saved}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'quant-reading-list.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('#import')?.addEventListener('change', async event => {
    try {
      const file = event.target.files[0]; if (!file) return;
      if (file.size > 2_000_000) throw Error();
      const data = JSON.parse(await file.text());
      if (data.version !== 1 || !data.papers || typeof data.papers !== 'object' || Array.isArray(data.papers)) throw Error();
      for (const [id, value] of Object.entries(data.papers)) {
        if (!/^(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})$/.test(id) || !value || typeof value !== 'object') continue;
        saved[id] = {star: value.star === true, read: value.read === true, progress: Math.min(1, Math.max(0, Number(value.progress) || 0))};
      }
      persist(); paintButtons(); if ($('#feed')) filter(false); $('#toast').textContent = '阅读记录已导入。';
    } catch { $('#toast').textContent = '无法导入，请选择有效的阅读记录 JSON 文件。'; }
    event.target.value = '';
  });
})();
