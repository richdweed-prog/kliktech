(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  const nav = document.querySelector('.nav');
  const links = document.querySelector('.links');
  if (nav && links) {
    const toggle = document.createElement('button');
    toggle.className = 'mobile-menu-toggle'; toggle.type = 'button';
    toggle.setAttribute('aria-label', 'Abrir menu'); toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<span aria-hidden="true">☰</span>';
    nav.insertBefore(toggle, links);
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

  // Build a lightweight 3D telemetry layer around the existing eSIM artwork.
  const stage = document.querySelector('.stage');
  if (stage) {
    const extras = document.createElement('div');
    extras.className = 'stage-3d-extras';
    extras.setAttribute('aria-hidden', 'true');
    extras.innerHTML = `
      <div class="scene-grid"></div>
      <div class="energy-ring ring-a"></div><div class="energy-ring ring-b"></div>
      <div class="satellite satellite-a"><i></i><b>01</b></div>
      <div class="satellite satellite-b"><i></i><b>02</b></div>
      <div class="signal-beam"></div>
      <div class="hud-label hud-top"><span class="hud-dot"></span>NETWORK / ONLINE</div>
      <div class="hud-label hud-bottom">LAT 23.55° S&nbsp;&nbsp; LONG 46.63° W</div>
      <div class="hud-metric metric-a"><small>LATÊNCIA</small><strong>18<em>ms</em></strong></div>
      <div class="hud-metric metric-b"><small>COBERTURA</small><strong>99.8<em>%</em></strong></div>`;
    stage.appendChild(extras);
  }

  const revealTargets = document.querySelectorAll('.plans, .compatibility-section, .info-card, .story, .step-item, .faq, .faq details');
  revealTargets.forEach((element, index) => {
    element.dataset.reveal = '';
    if (element.classList.contains('info-card') || element.classList.contains('step-item') || element.matches('.faq details')) {
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

  if (stage) {
    stage.addEventListener('pointermove', (event) => {
      const rect = stage.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      stage.style.setProperty('--scene-x', `${x * 18}px`);
      stage.style.setProperty('--scene-y', `${y * 14}px`);
      stage.style.setProperty('--scene-rotate', `${x * 4}deg`);
    });
    stage.addEventListener('pointerleave', () => {
      stage.style.setProperty('--scene-x', '0px'); stage.style.setProperty('--scene-y', '0px'); stage.style.setProperty('--scene-rotate', '0deg');
    });
  }

  document.querySelectorAll('.info-card, .app-stat, .app-order, .app-buy-card, .kpi').forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      card.style.setProperty('--mx', `${(x + .5) * 100}%`); card.style.setProperty('--my', `${(y + .5) * 100}%`);
      card.style.transform = `perspective(900px) rotateY(${x * 4}deg) rotateX(${-y * 3}deg) translateY(-5px) translateZ(4px)`;
    });
    card.addEventListener('pointerleave', () => { card.style.transform = ''; });
  });
})();
