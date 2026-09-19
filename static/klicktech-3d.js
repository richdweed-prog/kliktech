(() => {
  document.documentElement.classList.add('js-menu');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  const nav = document.querySelector('.nav');
  const links = document.querySelector('.links');
  if (nav && links) {
    const existingToggle = nav.querySelector('.mobile-menu-toggle');
    const toggle = existingToggle || document.createElement('button');
    toggle.className = 'mobile-menu-toggle'; toggle.type = 'button';
    toggle.setAttribute('aria-label', 'Abrir menu'); toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<span aria-hidden="true">☰</span>';
    if (!existingToggle) nav.insertBefore(toggle, links);
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('menu-open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
      toggle.innerHTML = `<span aria-hidden="true">${open ? '×' : '☰'}</span>`;
    });
    links.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      nav.classList.remove('menu-open'); toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Abrir menu'); toggle.innerHTML = '<span aria-hidden="true">☰</span>';
    }));
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
    const hero = appHome.querySelector('.app-hero');
    if (hero) hero.classList.add('client-hero-layer');
  }

  const revealTargets = document.querySelectorAll('.plans, .compatibility-section, .info-card, .story, .step-item, .faq, .faq details, .app-stat, .app-order, .app-buy-card, .app-note, .app-profile-card, .client-stat, .client-purchase-card');
  revealTargets.forEach((element, index) => {
    element.dataset.reveal = '';
    if (element.classList.contains('info-card') || element.classList.contains('step-item') || element.matches('.faq details') || element.matches('.app-stat, .client-stat')) {
      element.style.transitionDelay = `${Math.min(index % 4, 3) * 55}ms`;
    }
  });
  if (!reduceMotion && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); instance.unobserve(entry.target); } });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    revealTargets.forEach((element) => observer.observe(element));
  } else revealTargets.forEach((element) => element.classList.add('is-visible'));

  if (reduceMotion || !finePointer) return;
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
