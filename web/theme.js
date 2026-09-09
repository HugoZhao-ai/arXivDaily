(() => {
  let theme = 'light';
  try { theme = localStorage.getItem('quant-theme') || 'light'; } catch {}
  document.documentElement.dataset.theme = theme;
})();
