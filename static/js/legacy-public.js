const nativeFetch = window.fetch.bind(window);
let legacyCsrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
async function safeFetch(url, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers || {});
  if (method !== 'GET' && method !== 'HEAD') {
    headers.set('X-CSRF-Token', legacyCsrf);
    headers.set('X-Requested-With', 'XMLHttpRequest');
  }
  try {
    const response = await nativeFetch(url, { ...options, headers, credentials: 'same-origin' });
    response.clone().json().then((data) => { if (data.csrf_token) legacyCsrf = data.csrf_token; }).catch(() => {});
    return response;
  } catch (_error) {
    return new Response(JSON.stringify({ error: 'Não foi possível conectar ao servidor. Tente novamente.' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
  }
}

let authMode='login',selectedPlan=null;const byId=id=>document.getElementById(id);
function openClientModal(mode='login'){authMode=mode;selectedPlan=sessionStorage.getItem('selectedPlan');byId('client-modal').classList.add('open');setAuthMode(mode);loadClientMe()}
function closeClientModal(){byId('client-modal').classList.remove('open')}
function setAuthMode(mode){authMode=mode;byId('login-tab').classList.toggle('active',mode==='login');byId('register-tab').classList.toggle('active',mode==='register');byId('name-wrap').style.display=mode==='register'?'block':'none';byId('confirm-wrap').style.display=mode==='register'?'block':'none';byId('client-submit').textContent=mode==='register'?'Criar minha conta →':'Entrar na conta →';byId('client-modal-title').textContent=mode==='register'?'Criar sua conta':'Entrar na sua conta';byId('client-error').style.display='none'}
function clientError(text){byId('client-error').textContent=text;byId('client-error').style.display='block'}
async function submitClientAuth(){const body={email:byId('client-email').value.trim(),password:byId('client-password').value};if(authMode==='register'){body.name=byId('client-name').value.trim();body.password_confirmation=byId('client-password-confirmation').value;if(!body.name){clientError('Informe seu nome completo.');return}if(body.password.length<6){clientError('A senha precisa ter pelo menos 6 caracteres.');return}if(body.password!==body.password_confirmation){clientError('As senhas não conferem.');return}}const r=await safeFetch('/api/auth/'+authMode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok){clientError(d.error||'Não foi possível continuar.');return}if(d.is_admin){location.href='/ademiroputo/dashboard';return}if(selectedPlan){const plan=selectedPlan;sessionStorage.removeItem('selectedPlan');await loadClientMe();const catalog=await (await safeFetch('/api/plans')).json();const chosen=(catalog.plans||[]).find(x=>x.plan===plan);if(chosen)await showDddSlots(chosen.plan,chosen.price);else clientError('Este plano não está mais disponível.')}else await loadClientMe()}
async function loadClientMe(){const d=await(await safeFetch('/api/me')).json();const modal=document.querySelector('.modal');if(d.user){closeClientModal();byId('client-app').classList.add('open');const money='R$ '+d.user.balance.toFixed(2).replace('.',',');byId('app-first-name').textContent=d.user.name.split(' ')[0];byId('app-avatar').textContent=d.user.name.trim().charAt(0).toUpperCase();byId('app-name').value=d.user.name;byId('app-email').value=d.user.email;byId('app-public-id').textContent=d.user.id?'ID '+d.user.id:'ID não disponível';if(d.user.profile_photo_url)byId('app-profile-avatar').style.backgroundImage=`url(${d.user.profile_photo_url})`;byId('app-balance').textContent=money;byId('app-balance-card').textContent=money;loadFullClientPurchases()}else{byId('client-app').classList.remove('open');modal.classList.remove('client-logged');byId('client-auth').style.display='block';byId('client-dashboard').style.display='none'}}
async function loadClientPurchases(){return loadFullClientPurchases()}
async function applyTheme(mode){document.body.classList.remove('light-mode','medium-mode');if(mode==='light')document.body.classList.add('light-mode');if(mode==='medium')document.body.classList.add('medium-mode');localStorage.setItem('kliktech-theme',mode);const labels={dark:'☾ Noite',medium:'◐ Médio',light:'☼ Dia'};['theme-toggle','public-theme-toggle'].forEach(id=>{const b=byId(id);if(b)b.textContent=labels[mode]})}function toggleTheme(){const current=localStorage.getItem('kliktech-theme')||'medium';const next={dark:'light',light:'medium',medium:'dark'}[current]||'medium';applyTheme(next)}function restoreTheme(){applyTheme(localStorage.getItem('kliktech-theme')||'medium')}restoreTheme();async function logoutClient(){await safeFetch('/api/auth/logout',{method:'POST'});byId('client-app').classList.remove('open');setAuthMode('login');loadClientMe()}function openWallet(){byId('wallet-modal').classList.add('open');byId('wallet-error').textContent='';byId('pix-result').style.display='none'}function closeWallet(){byId('wallet-modal').classList.remove('open')}async function createWalletPix(){const amount=Number(byId('wallet-amount').value);byId('wallet-error').textContent='';byId('pix-result').style.display='none';if(!Number.isFinite(amount)||amount<5){byId('wallet-error').textContent='Digite um valor de recarga de pelo menos R$ 5,00.';return}const r=await safeFetch('/api/wallet/create-pix',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount})});let d={};try{d=await r.json()}catch(e){}if(!r.ok){byId('wallet-error').textContent=r.status===503?'Recarga temporariamente indisponível: o servidor ainda não está conectado à BravoPay. Configure BRAVOPAY_API_KEY no .env e reinicie o sistema.':(d.error||'Não foi possível gerar o Pix.');return}byId('pix-result').style.display='block';byId('pix-copy').textContent=d.charge.copy_paste;byId('pix-status').textContent='Pix criado. Pague este código e aguarde a confirmação; o saldo aparecerá automaticamente nesta conta.'}function copyWalletPix(){navigator.clipboard?.writeText(byId('pix-copy').textContent);byId('pix-status').textContent='Código Pix copiado.'}function logoutFullClient(){logoutClient();location.hash='planos'}async function showDddSlots(plan,price){window.selectedBuyPlan=plan;const msg=byId('app-buy-message');msg.textContent='Consultando DDDs disponíveis...';const r=await safeFetch('/api/availability?plan='+encodeURIComponent(plan));const d=await r.json();if(!r.ok||!d.ddds?.length){msg.textContent='Sem DDD eSIM disponível para este plano no momento.';msg.style.color='var(--red)';return}msg.style.color='var(--acid)';msg.innerHTML='Escolha um DDD disponível: '+d.ddds.map(x=>`<button class="ddd-slot" onclick="confirmBuy('${plan}',${price},'${x.ddd}')">DDD ${x.ddd} · ${x.quantity} disponível</button>`).join(' ')}async function buyInsideClient(plan,price){return showDddSlots(plan,price)}async function confirmBuy(plan,price,ddd){const msg=byId('app-buy-message');msg.textContent='Processando sua compra...';const r=await safeFetch('/api/purchase',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan,ddd})});const d=await r.json();if(!r.ok){if(r.status===402){msg.textContent='Saldo insuficiente. Abra Adicionar saldo via Pix, conclua o pagamento e aguarde a confirmação antes de comprar.'}else if(r.status===409){msg.textContent='Este plano está sem eSIM disponível no estoque. Escolha outro plano ou aguarde reposição.'}else{msg.textContent=d.error||'Não foi possível concluir a compra.'}msg.style.color='var(--red)';return}msg.textContent='Compra aprovada. Os dados foram liberados no seu histórico de compras.';msg.style.color='var(--acid)';await loadFullClientPurchases();switchAppPanel('app-history',document.querySelector('.client-app-nav button:nth-child(2)'))}function switchAppPanel(id,button){document.querySelectorAll('.app-panel').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.client-app-nav button').forEach(x=>x.classList.remove('active'));byId(id).classList.add('active');if(button)button.classList.add('active')}function renderGuide(x){const g=x.setup_guide;return `<div class="app-guide"><h4>${g.title}</h4><div class="app-guide-grid">${g.steps.map((z,i)=>`<div class="app-guide-step"><b>${i+1}. ${z.title}</b><small><strong>iPhone · iOS</strong><br>${z.iphone}</small><small><strong>Android</strong><br>${z.android}</small></div>`).join('')}</div><div class="app-install-note"><b>Instalar o eSIM</b><br><br><strong>iPhone:</strong> ${g.install.iphone}<br><br><strong>Android:</strong> ${g.install.android}<br><br>${g.install.note}</div></div>`}async function loadFullClientPurchases(){const r=await safeFetch('/api/account/purchases');if(!r.ok)return;const d=await r.json();byId('app-order-count').textContent=d.purchases.length;byId('app-history-label').textContent=d.purchases.length+' pedido(s)';const cards=d.purchases.length?d.purchases.map(x=>`<article class="app-order"><div class="app-order-head"><b>${x.plan}</b><span class="app-approved">COMPRA APROVADA · ENTREGA IMEDIATA</span></div><div class="app-order-meta"><span>Data<b>${x.date}</b></span><span>Valor<b>R$ ${Number(x.price).toFixed(2).replace('.',',')}</b></span></div><details open><summary>Ver eSIM, configuração e instruções</summary><div class="app-codes">${x.photo_url?`<img src="${x.photo_url}" alt="Foto do eSIM" style="max-width:100%;max-height:180px;object-fit:contain;display:block;margin-bottom:12px">`:''}<img src="${x.qr_url}" alt="QR Code de instalação do eSIM" style="display:block;width:190px;height:190px;background:white;padding:8px;border-radius:6px;margin-bottom:12px"><b>SM-DP+</b><br>${x.smdp}<br><br><b>Código de ativação</b><br>${x.activation_code}${x.line?`<br><br><b>ICCID / linha</b><br>${x.line}`:''}</div>${renderGuide(x)}</details></article>`).join(''):'<div class="app-empty">Você ainda não possui compras aprovadas.<br>Escolha um plano para começar.</div>';['app-home-list','app-history-list','app-activation-list'].forEach(id=>byId(id).innerHTML=cards)}
function switchClientPanel(panel,button){document.querySelectorAll('.client-panel').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.client-nav button').forEach(x=>x.classList.remove('active'));byId('panel-'+panel).classList.add('active');if(button)button.classList.add('active');if(panel==='history')renderClientList('client-history-list');if(panel==='activations')renderClientList('client-activation-list')}function renderClientList(id){const source=byId('client-purchase-list').innerHTML;byId(id).innerHTML=source||'<div class="client-empty">Nenhuma compra aprovada ainda.</div>'}async function buy(plan){await safeFetch('/api/cart',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan})});sessionStorage.setItem('selectedPlan',plan);openClientModal('login')}
async function checkEsimCompatibility(){const form=byId('compatibility-form'),input=byId('compatibility-model'),out=byId('compatibility-result');const model=input.value.trim();if(!model)return;out.className='compatibility-result open';out.textContent='Consultando compatibilidade...';try{const r=await safeFetch('/api/esim/compatibility?model='+encodeURIComponent(model));const d=await r.json();if(d.esim_supported===true){out.className='compatibility-result open success';out.innerHTML='<b>Possível compatibilidade encontrada.</b><br>'+d.family+'. Confirme a variante do aparelho e a opção “Adicionar eSIM” antes da compra.'}else{out.className='compatibility-result open review';out.innerHTML='<b>Precisamos confirmar este modelo.</b><br>'+(d.message||'Verifique se o aparelho possui EID e a opção “Adicionar eSIM”.')} }catch(e){out.className='compatibility-result open error';out.textContent='Não foi possível consultar agora. Tente novamente em instantes.'}}
byId('compatibility-form').addEventListener('submit',e=>{e.preventDefault();checkEsimCompatibility()});
loadCatalogSafe();
byId('profile-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,r=await safeFetch('/api/account/profile',{method:'POST',body:new FormData(form)}),d=await r.json();byId('profile-message').textContent=r.ok?'Perfil atualizado.':(d.error||'Não foi possível salvar.');if(r.ok){byId('app-public-id').textContent='ID '+d.user.id;if(d.user.profile_photo_url)byId('app-profile-avatar').style.backgroundImage=`url(${d.user.profile_photo_url})`}};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeClientModal()});


function appendText(parent, value) { parent.appendChild(document.createTextNode(String(value ?? ''))); }
function legacyPlanCard(plan, index, inside = false) {
  const card = document.createElement('article');
  card.className = inside ? `app-buy-card${plan.featured ? ' featured' : ''}` : `plan${plan.featured ? ' featured' : ''}`;
  const small = document.createElement('small');
  if (inside) small.textContent = `${String(index + 1).padStart(2, '0')} / ${plan.gigas}`;
  const heading = document.createElement('h3'); heading.textContent = plan.gigas;
  const description = document.createElement('p'); description.textContent = inside ? `${plan.tempo} de internet móvel` : `${plan.tempo} · R$ ${Number(plan.price).toFixed(2).replace('.', ',')}`;
  const info = document.createElement('div');
  if (inside) { info.append(small, heading, description); const price = document.createElement('strong'); price.textContent = `R$ ${Number(plan.price).toFixed(2).replace('.', ',')}`; info.append(price); } else { info.append(heading, description); }
  const button = document.createElement('button'); button.type = 'button'; button.className = inside ? '' : 'buy'; button.textContent = 'Comprar com saldo →';
  button.addEventListener('click', () => inside ? buyInsideClient(plan.plan, plan.price) : buy(plan.plan));
  card.append(info, button);
  if (!inside) { const external = document.createElement('button'); external.type = 'button'; external.className = 'external-buy'; external.textContent = 'Criar conta e comprar com saldo →'; external.addEventListener('click', () => buy(plan.plan)); card.append(external); }
  return card;
}
async function loadCatalogSafe() {
  try {
    const response = await safeFetch('/api/plans');
    const data = await response.json();
    const plans = Array.isArray(data.plans) ? data.plans : [];
    const grid = byId('public-plans-grid');
    if (grid) { grid.replaceChildren(); plans.forEach((plan, index) => grid.appendChild(legacyPlanCard(plan, index, false))); }
    const buyGrid = byId('app-buy-grid');
    if (buyGrid) { buyGrid.replaceChildren(); plans.forEach((plan, index) => buyGrid.appendChild(legacyPlanCard(plan, index, true))); }
  } catch (_error) { /* empty state remains visible */ }
}
async function showDddSlots(plan, price) {
  window.selectedBuyPlan = plan;
  const message = byId('app-buy-message');
  message.replaceChildren(document.createTextNode('Consultando DDDs disponíveis...'));
  try {
    const response = await safeFetch('/api/availability?plan=' + encodeURIComponent(plan));
    const data = await response.json();
    if (!response.ok || !Array.isArray(data.ddds) || !data.ddds.length) { message.textContent = 'Sem DDD eSIM disponível para este plano no momento.'; return; }
    message.replaceChildren(document.createTextNode('Escolha um DDD disponível: '));
    data.ddds.forEach((item) => { const button = document.createElement('button'); button.type = 'button'; button.className = 'ddd-slot'; button.textContent = `DDD ${item.ddd} · ${item.quantity} disponível`; button.addEventListener('click', () => confirmBuy(plan, price, item.ddd)); message.appendChild(button); });
  } catch (_error) { message.textContent = 'Não foi possível consultar os DDDs agora.'; }
}
async function loadFullClientPurchases() {
  try {
    const response = await safeFetch('/api/account/purchases');
    if (!response.ok) return;
    const data = await response.json();
    const purchases = Array.isArray(data.purchases) ? data.purchases : [];
    byId('app-order-count').textContent = String(purchases.length);
    byId('app-history-label').textContent = `${purchases.length} pedido(s)`;
    const render = (purchase) => {
      const article = document.createElement('article'); article.className = 'app-order';
      const head = document.createElement('div'); head.className = 'app-order-head'; const plan = document.createElement('b'); plan.textContent = purchase.plan; const status = document.createElement('span'); status.className = 'app-approved'; status.textContent = 'COMPRA APROVADA · ENTREGA IMEDIATA'; head.append(plan, status);
      const meta = document.createElement('div'); meta.className = 'app-order-meta'; const date = document.createElement('span'); date.textContent = 'Data'; const dateValue = document.createElement('b'); dateValue.textContent = purchase.date; date.appendChild(dateValue); const value = document.createElement('span'); value.textContent = 'Valor'; const valueText = document.createElement('b'); valueText.textContent = `R$ ${Number(purchase.price).toFixed(2).replace('.', ',')}`; value.appendChild(valueText); meta.append(date, value);
      const details = document.createElement('details'); details.open = true; const summary = document.createElement('summary'); summary.textContent = 'Ver eSIM, configuração e instruções'; const codes = document.createElement('div'); codes.className = 'app-codes';
      if (purchase.photo_url) { const photo = document.createElement('img'); photo.className = 'legacy-photo'; photo.src = purchase.photo_url; photo.alt = 'Foto do eSIM'; codes.appendChild(photo); }
      const qr = document.createElement('img'); qr.className = 'legacy-qr'; qr.src = purchase.qr_url; qr.alt = 'QR Code de instalação do eSIM'; codes.appendChild(qr); appendText(codes, 'SM-DP+\n'); const smdp = document.createElement('b'); smdp.textContent = purchase.smdp; codes.appendChild(smdp); appendText(codes, '\n\nCódigo de ativação\n'); const activation = document.createElement('b'); activation.textContent = purchase.activation_code; codes.appendChild(activation); if (purchase.line) { appendText(codes, '\n\nICCID / linha\n'); const line = document.createElement('b'); line.textContent = purchase.line; codes.appendChild(line); }
      details.append(summary, codes); article.append(head, meta, details); return article;
    };
    ['app-home-list', 'app-history-list', 'app-activation-list'].forEach((id) => { const target = byId(id); target.replaceChildren(); if (!purchases.length) { const empty = document.createElement('div'); empty.className = 'app-empty'; empty.textContent = 'Você ainda não possui compras aprovadas. Escolha um plano para começar.'; target.appendChild(empty); } else purchases.forEach((purchase) => target.appendChild(render(purchase))); });
  } catch (_error) { /* keep the dashboard usable */ }
}
function legacyNavigate(action, source) {
  const appMap = { 'app-home': 'app-home', 'app-history': 'app-history', 'app-activations': 'app-activations', 'app-buy': 'app-buy', 'app-settings': 'app-settings', 'app-help': 'app-help' };
  if (appMap[action]) return switchAppPanel(appMap[action], source);
  const clientMap = { 'client-home': 'home', 'client-history': 'history', 'client-activations': 'activations', 'client-buy': 'buy', 'client-settings': 'settings', 'client-help': 'help' };
  if (clientMap[action]) return switchClientPanel(clientMap[action], source);
  if (action === 'open-login') return openClientModal('login');
  if (action === 'toggle-theme') return toggleTheme();
  if (action === 'auth-login') return setAuthMode('login');
  if (action === 'auth-register') return setAuthMode('register');
  if (action === 'submit-auth') return submitClientAuth();
  if (action === 'close-client' || action === 'close-client-backdrop') return closeClientModal();
  if (action === 'open-wallet') return openWallet();
  if (action === 'close-wallet' || action === 'close-wallet-backdrop') return closeWallet();
  if (action === 'create-wallet') return createWalletPix();
  if (action === 'copy-wallet') return copyWalletPix();
  if (action === 'logout-client') return logoutClient();
  if (action === 'logout-full-client') return logoutFullClient();
  if (action === 'toggle-client-navigation') return toggleClientNavigation();
  if (action === 'close-client-navigation') return closeClientNavigation();
  if (action === 'toggle-public-menu') return window.togglePublicMenu?.();
  const quickBuy = { 'buy-30-1': ['30GB · 1 mês', 20], 'buy-45-1': ['45GB · 1 mês', 30], 'buy-30-2': ['30GB · 2 meses', 40], 'buy-45-2': ['45GB · 2 meses', 50] };
  if (quickBuy[action]) return buyInsideClient(...quickBuy[action]);
}
document.addEventListener('click', (event) => {
  const action = event.target.closest('[data-legacy-action]')?.dataset.legacyAction;
  if (action) { if (action.endsWith('-backdrop') && event.target !== event.currentTarget) return; event.preventDefault(); legacyNavigate(action, event.target.closest('button')); }
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { closeClientModal(); closeWallet(); } });
(() => {
  document.documentElement.classList.add('js-menu');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  const nav = document.querySelector('.kt-public-nav');
  const links = document.querySelector('.kt-public-links');
  const publicToggle = document.querySelector('#public-menu-toggle');
  window.togglePublicMenu = () => {
    const open = !nav?.classList.contains('kt-menu-open');
    nav?.classList.toggle('kt-menu-open', open);
    publicToggle?.setAttribute('aria-expanded', String(open));
    publicToggle?.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    if (publicToggle) publicToggle.querySelector('span[aria-hidden="true"]').textContent = open ? '×' : '☰';
    document.body.classList.toggle('public-menu-lock', open && window.matchMedia('(max-width: 900px)').matches);
    if (open) links?.querySelector('a, button')?.focus();
  };
  if (nav && links && publicToggle) {
    links.querySelectorAll('a, button').forEach((link) => link.addEventListener('click', () => {
      nav.classList.remove('kt-menu-open');
      publicToggle.setAttribute('aria-expanded', 'false');
      publicToggle.setAttribute('aria-label', 'Abrir menu');
      publicToggle.querySelector('span[aria-hidden="true"]').textContent = '☰';
      document.body.classList.remove('public-menu-lock');
    }));
    document.addEventListener('click', (event) => {
      if (!nav.contains(event.target) && nav.classList.contains('kt-menu-open')) {
        nav.classList.remove('kt-menu-open');
        publicToggle.setAttribute('aria-expanded', 'false');
        publicToggle.setAttribute('aria-label', 'Abrir menu');
        publicToggle.querySelector('span[aria-hidden="true"]').textContent = '☰';
        document.body.classList.remove('public-menu-lock');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && nav.classList.contains('kt-menu-open')) {
        nav.classList.remove('kt-menu-open');
        publicToggle.setAttribute('aria-expanded', 'false');
        publicToggle.setAttribute('aria-label', 'Abrir menu');
        publicToggle.querySelector('span[aria-hidden="true"]').textContent = '☰';
        document.body.classList.remove('public-menu-lock');
        publicToggle.focus();
      }
    });
  }

  const stage = document.querySelector('.stage');
  if (stage) {
    const extras = document.createElement('div');
    extras.className = 'stage-3d-extras'; extras.setAttribute('aria-hidden', 'true');
    extras.innerHTML = '<div class="scene-grid"></div><div class="energy-ring ring-a"></div><div class="energy-ring ring-b"></div><div class="satellite satellite-a"><i></i><b>01</b></div><div class="satellite satellite-b"><i></i><b>02</b></div><div class="signal-beam"></div><div class="hud-label hud-top"><span class="hud-dot"></span>NETWORK / ONLINE</div><div class="hud-label hud-bottom">LAT 23.55° S&nbsp;&nbsp; LONG 46.63° W</div><div class="hud-metric metric-a"><small>LATÊNCIA</small><strong>18<em>ms</em></strong></div><div class="hud-metric metric-b"><small>COBERTURA</small><strong>99.8<em>%</em></strong></div>';
    stage.appendChild(extras);
  }

  // A living dashboard layer is created only once the customer area exists.
  const appHome = document.querySelector('#app-home');
  if (appHome) {
    const ambient = document.createElement('div');
    ambient.className = 'client-ambient'; ambient.setAttribute('aria-hidden', 'true');
    ambient.innerHTML = '<div class="ambient-glow"></div><div class="ambient-orbit ambient-orbit-a"></div><div class="ambient-orbit ambient-orbit-b"></div><div class="ambient-core"><span></span></div><div class="ambient-particle p1"></div><div class="ambient-particle p2"></div><div class="ambient-particle p3"></div><div class="live-chip"><i></i> CONEXÃO ATIVA</div>';
    appHome.prepend(ambient);
    const depth = document.createElement('div');
    depth.className = 'client-depth-scene'; depth.setAttribute('aria-hidden', 'true');
    depth.innerHTML = '<span class="depth-ring"></span><span class="depth-ring"></span><span class="depth-node"></span>';
    appHome.prepend(depth);
    const hero = appHome.querySelector('.app-hero');
    if (hero) hero.classList.add('client-hero-layer');
  }

  const revealTargets = document.querySelectorAll('.plans, .compatibility-section, .info-card, .story, .step-item, .faq, .faq details, .app-stat, .app-order, .app-buy-card, .app-note, .app-profile-card, .client-stat, .client-purchase-card');
  revealTargets.forEach((element, index) => {
    element.dataset.reveal = '';
    if (element.classList.contains('info-card') || element.classList.contains('step-item') || element.matches('.faq details') || element.matches('.app-stat, .client-stat')) {
      element.dataset.revealOrder = String(Math.min(index % 4, 3));
    }
  });
  if (!reduceMotion && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); instance.unobserve(entry.target); } });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    revealTargets.forEach((element) => observer.observe(element));
  } else revealTargets.forEach((element) => element.classList.add('is-visible'));

  if (reduceMotion || window.matchMedia('(max-width: 900px)').matches) return;
  if (!reduceMotion) {
    let ticking = false;
    const updateScrollScene = () => {
      const y = window.scrollY || 0;
      const viewport = Math.max(window.innerHeight, 1);
      const progress = Math.min(1, Math.max(0, y / (document.documentElement.scrollHeight - viewport || 1)));
      document.documentElement.style.setProperty('--page-progress', progress.toFixed(3));
      if (stage) {
        stage.style.setProperty('--scroll-tilt', `${(progress * 16 - 8).toFixed(2)}deg`);
        stage.style.setProperty('--scroll-depth', `${(progress * 18).toFixed(2)}px`);
      }
      const clientApp = document.querySelector('.client-app');
      if (clientApp) clientApp.style.setProperty('--client-scroll', `${(progress * 22).toFixed(2)}px`);
      ticking = false;
    };
    window.addEventListener('scroll', () => { if (!ticking) { window.requestAnimationFrame(updateScrollScene); ticking = true; } }, { passive: true });
    updateScrollScene();
  }

  if (!finePointer) return;
  if (stage) {
    stage.addEventListener('pointermove', (event) => {
      const rect = stage.getBoundingClientRect(); const x = (event.clientX - rect.left) / rect.width - .5; const y = (event.clientY - rect.top) / rect.height - .5;
      stage.style.setProperty('--scene-x', `${x * 18}px`); stage.style.setProperty('--scene-y', `${y * 14}px`); stage.style.setProperty('--scene-rotate', `${x * 4}deg`);
    });
    stage.addEventListener('pointerleave', () => { stage.style.setProperty('--scene-x', '0px'); stage.style.setProperty('--scene-y', '0px'); stage.style.setProperty('--scene-rotate', '0deg'); });
  }
  const clientArea = document.querySelector('.client-app');
  if (clientArea) {
    clientArea.addEventListener('pointermove', (event) => {
      const rect = clientArea.getBoundingClientRect();
      clientArea.style.setProperty('--client-x', `${((event.clientX - rect.left) / rect.width - .5) * 16}px`);
      clientArea.style.setProperty('--client-y', `${((event.clientY - rect.top) / rect.height - .5) * 12}px`);
    });
  }
  document.querySelectorAll('.info-card, .app-stat, .app-order, .app-buy-card, .app-note, .app-profile-card, .client-stat, .client-purchase-card, .kpi').forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect(); const x = (event.clientX - rect.left) / rect.width - .5; const y = (event.clientY - rect.top) / rect.height - .5;
      card.style.setProperty('--mx', `${(x + .5) * 100}%`); card.style.setProperty('--my', `${(y + .5) * 100}%`);
      card.style.transform = `perspective(900px) rotateY(${x * 4}deg) rotateX(${-y * 3}deg) translateY(-5px) translateZ(4px)`;
    });
    card.addEventListener('pointerleave', () => { card.style.transform = ''; });
  });
})();

/* Fallback do menu original: o checkbox continua sendo a fonte visual, e este
   handler garante toque, teclado, fechamento externo e estado ARIA. */
(() => {
  const nav = document.querySelector('.kt-public-nav');
  const toggle = document.querySelector('#public-menu-toggle');
  const menu = document.querySelector('#site-menu');
  if (!nav || !toggle || !menu) return;
  const setMenu = (open) => {
    nav.classList.toggle('kt-menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    const icon = toggle.querySelector('[aria-hidden="true"]');
    if (icon) icon.textContent = open ? '×' : '☰';
  };
  toggle.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    setMenu(!nav.classList.contains('kt-menu-open'));
  }, { passive: false });
  menu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('click', (event) => { if (!nav.contains(event.target)) setMenu(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setMenu(false); });
  setMenu(false);
})();

document.addEventListener('DOMContentLoaded', () => {
  if (typeof loadClientMe === 'function') loadClientMe().catch(() => {});
});
