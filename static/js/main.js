// main.js - ações do frontend: submissão do formulário de crawl e checagem periódica

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('formBuscar');
  const loading = document.getElementById('loading');
  const btnBuscar = document.getElementById('btnBuscar');

  if (!form) return;

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (btnBuscar) btnBuscar.disabled = true;
    if (loading) loading.style.display = 'block';

    fetch(form.action, { method: 'POST', body: new FormData(form) })
      .then(() => {
        // inicia checagens periódicas
        pollForUpdates();
      })
      .catch(() => {
        if (btnBuscar) btnBuscar.disabled = false;
        if (loading) loading.style.display = 'none';
      });
  });

  function pollForUpdates() {
    let checks = 0;
    const maxChecks = 24; // 2 minutos (24 * 5s)

    const interval = setInterval(() => {
      checks++;
      if (checks >= maxChecks) {
        clearInterval(interval);
        window.location.href = window.location.pathname + '?page=1';
        return;
      }

      fetch(window.location.pathname + '/noticias?updating=1')
        .then(res => res.text())
        .then(html => {
          // busca sinal simples: presença de '.noticia' na listagem
          if (html && html.indexOf('class="noticia"') !== -1) {
            clearInterval(interval);
            window.location.href = window.location.pathname + '?page=1';
          }
        })
        .catch(() => {});
    }, 5000);
  }
});
