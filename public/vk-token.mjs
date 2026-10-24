const vkOrigins = new Set(['vk.com', 'www.vk.com', 'm.vk.com', 'vk.ru', 'www.vk.ru', 'm.vk.ru']
  .map(host => 'https://' + host));

export async function initializeTokenPage({ bridge, document, location, navigator,
  setTimeout = globalThis.setTimeout, clearTimeout = globalThis.clearTimeout }) {
  const ui = Object.fromEntries(['context', 'authorize', 'status', 'result', 'token', 'copy', 'toggle', 'clear']
    .map(id => [id, document.getElementById(id)]));
  let active = true;
  const clear = () => {
    ui.token.value = '';
    ui.token.type = 'password';
    ui.toggle.textContent = 'Показать';
    ui.toggle.setAttribute('aria-pressed', 'false');
    ui.result.hidden = true;
  };
  clear();
  const timed = async promise => {
    let timer;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('timeout')), 45000);
      })]);
    } finally { clearTimeout(timer); }
  };
  document.defaultView?.addEventListener('pagehide', () => { active = false; clear(); ui.authorize.disabled = true; });
  ui.clear.addEventListener('click', () => { clear(); ui.status.textContent = 'Ключ очищен.'; });
  ui.toggle.addEventListener('click', () => {
    const show = ui.token.type === 'password';
    ui.token.type = show ? 'text' : 'password';
    ui.toggle.textContent = show ? 'Скрыть' : 'Показать';
    ui.toggle.setAttribute('aria-pressed', String(show));
  });
  ui.copy.addEventListener('click', async () => {
    if (!ui.token.value) return;
    try {
      await navigator.clipboard.writeText(ui.token.value);
      ui.status.textContent = 'Ключ скопирован. Вставьте его в скрытый запрос терминала.';
    } catch {
      ui.token.type = 'text';
      ui.toggle.textContent = 'Скрыть';
      ui.toggle.setAttribute('aria-pressed', 'true');
      ui.token.focus();
      ui.token.select();
      ui.status.textContent = 'Браузер не разрешил копирование кнопкой. Ключ выделен: нажмите Ctrl+C.';
    }
  });
  const appId = Number(new URLSearchParams(location.search).get('vk_app_id'));
  let trustedFrame = false;
  try { trustedFrame = vkOrigins.has(new URL(document.referrer).origin); } catch {}
  if (!bridge || !Number.isSafeInteger(appId) || appId <= 0 ||
      !(bridge.isWebView() || (bridge.isIframe() && trustedFrame))) return;

  ui.context.textContent = `Мини-приложение VK № ${appId}. После нажатия VK покажет запрос разрешения wall.`;
  try {
    await timed(bridge.send('VKWebAppInit'));
    if (!active) return;
    ui.authorize.disabled = false;
  } catch {
    ui.status.textContent = 'VK не подтвердил запуск мини-приложения. Откройте его заново через VK.';
    return;
  }
  document.defaultView?.addEventListener('pageshow', event => {
    if (event.persisted) { active = true; clear(); ui.authorize.disabled = false; }
  });
  ui.authorize.addEventListener('click', async () => {
    clear();
    ui.authorize.disabled = true;
    ui.status.textContent = 'Ожидаю ответ окна авторизации VK…';
    try {
      const data = await timed(bridge.send('VKWebAppGetAuthToken', { app_id: appId, scope: 'wall' }));
      if (!active) return;
      const scopes = typeof data?.scope === 'string' ? data.scope.split(',').map(x => x.trim()) : [];
      if (!scopes.includes('wall')) {
        ui.status.textContent = 'VK не выдал право wall. Ключ не показан; проверьте разрешения приложения.';
        return;
      }
      if (typeof data?.access_token !== 'string' || !data.access_token.trim()) throw new Error('empty');
      ui.token.value = data.access_token;
      ui.result.hidden = false;
      ui.status.textContent = 'VK выдал ключ и право wall. Теперь проверьте доступ скриптом --check.';
    } catch (error) {
      clear();
      const code = error?.error_data?.error_code;
      // Raw VK errors can contain request parameters or credentials.
      ui.status.textContent = `Ключ не получен${Number.isInteger(code) ? ` (код VK ${code})` : ''}. Если окно было закрыто, повторите запрос.`;
    } finally { if (active) ui.authorize.disabled = false; }
  });
}

if (typeof document !== 'undefined') {
  initializeTokenPage({ bridge: window.vkBridge, document, location, navigator });
}
