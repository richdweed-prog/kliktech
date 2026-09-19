(() => {
  "use strict";

  const body = document.body;
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  let csrf = csrfMeta?.content || "";
  let currentUser = null;
  let pendingPlan = null;
  let activeDialog = null;
  let dialogOpener = null;
  let authMode = "login";
  let busy = false;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const money = (value) => `R$ ${Number(value || 0).toFixed(2).replace(".", ",")}`;
  const text = (value) => String(value ?? "");

  async function request(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (method !== "GET" && method !== "HEAD") {
      headers.set("X-CSRF-Token", csrf);
      headers.set("X-Requested-With", "XMLHttpRequest");
    }
    try {
      const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
      let data = {};
      try { data = await response.json(); } catch (_error) { data = {}; }
      if (data.csrf_token) csrf = data.csrf_token;
      return { response, data };
    } catch (_error) {
      return { response: null, data: { error: "Não foi possível conectar ao servidor. Tente novamente." } };
    }
  }

  function setBusy(button, value) {
    if (!button) return;
    button.disabled = value;
    if (value) button.dataset.originalLabel = button.textContent;
    button.textContent = value ? "Aguarde…" : (button.dataset.originalLabel || button.textContent);
  }

  function dialogElements() {
    return $$(".public-dialog-backdrop.is-open");
  }

  function openDialog(dialog, opener) {
    if (!dialog) return;
    dialogOpener = opener || document.activeElement;
    activeDialog = dialog;
    dialog.classList.add("is-open");
    dialog.removeAttribute("aria-hidden");
    body.classList.add("has-dialog");
    const focusTarget = $("input:not([type=hidden]), button, select, textarea", dialog);
    window.setTimeout(() => (focusTarget || dialog).focus(), 0);
  }

  function closeDialog(dialog = activeDialog) {
    if (!dialog) return;
    dialog.classList.remove("is-open");
    dialog.setAttribute("aria-hidden", "true");
    if (activeDialog === dialog) activeDialog = null;
    if (!dialogElements().length) body.classList.remove("has-dialog");
    if (dialogOpener && document.contains(dialogOpener)) dialogOpener.focus();
  }

  function trapFocus(event) {
    if (event.key === "Escape" && activeDialog) {
      closeDialog();
      return;
    }
    if (event.key !== "Tab" || !activeDialog) return;
    const focusable = $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', activeDialog);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function setMessage(element, message, type = "") {
    if (!element) return;
    element.textContent = message || "";
    element.className = element.dataset.baseClass || element.className.replace(/\s+is-(error|success|warning)/g, "");
    if (type) element.classList.add(`is-${type}`);
  }

  function applyTheme(mode) {
    const selected = ["dark", "light"].includes(mode) ? mode : "dark";
    body.classList.toggle("is-light", selected === "light");
    $("#client-page")?.classList.toggle("is-light", selected === "light");
    localStorage.setItem("kliktech-theme", selected);
    $$('[data-theme-toggle]').forEach((button) => { button.textContent = selected === "light" ? "Tema escuro" : "Tema claro"; });
  }

  function toggleTheme() {
    applyTheme(localStorage.getItem("kliktech-theme") === "light" ? "dark" : "light");
  }

  function openClientPage() {
    const page = $("#client-page");
    if (!page) return;
    page.classList.add("is-open");
    page.removeAttribute("aria-hidden");
    body.classList.add("has-client");
    closeDialog($("#auth-dialog"));
  }

  function closeClientPage() {
    const page = $("#client-page");
    page?.classList.remove("is-open");
    page?.setAttribute("aria-hidden", "true");
    body.classList.remove("has-client");
    closeClientDrawer();
  }

  function openClientDrawer() {
    $("#client-sidebar")?.classList.add("is-open");
    $("#client-scrim")?.classList.add("is-visible");
    $("#client-menu-button")?.setAttribute("aria-expanded", "true");
  }

  function closeClientDrawer() {
    $("#client-sidebar")?.classList.remove("is-open");
    $("#client-scrim")?.classList.remove("is-visible");
    $("#client-menu-button")?.setAttribute("aria-expanded", "false");
  }

  function switchPanel(panelId) {
    $$(".client-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === panelId));
    $$(".client-nav-button").forEach((button) => button.classList.toggle("is-active", button.dataset.panel === panelId));
    closeClientDrawer();
  }

  function openAuthDialog(mode = "login", opener) {
    authMode = mode;
    setAuthMode(mode);
    openDialog($("#auth-dialog"), opener);
  }

  function setAuthMode(mode) {
    authMode = mode;
    $$("[data-auth-tab]").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.authTab === mode));
    $$("[data-auth-form]").forEach((form) => { form.hidden = form.dataset.authForm !== mode; });
    const title = $("#auth-dialog-title");
    if (title) title.textContent = mode === "register" ? "Criar sua conta" : "Entrar na sua conta";
    setMessage($("#auth-message"), "");
  }

  function renderPlanCard(plan) {
    const article = document.createElement("article");
    article.className = `public-plan${plan.featured ? " public-plan--featured" : ""}`;
    const content = document.createElement("div");
    const small = document.createElement("small");
    small.textContent = plan.featured ? "RECOMENDADO" : "PLANO DIGITAL";
    const heading = document.createElement("h3");
    heading.textContent = plan.gigas;
    const description = document.createElement("p");
    description.textContent = `${plan.tempo} · ${money(plan.price)}`;
    content.append(small, heading, description);
    const button = document.createElement("button");
    button.className = "public-button";
    button.type = "button";
    button.textContent = "Escolher este plano";
    button.dataset.plan = plan.plan;
    button.addEventListener("click", () => selectPlan(plan.plan));
    article.append(content, button);
    return article;
  }

  async function loadCatalog() {
    const grid = $("#public-plans-grid");
    if (!grid) return;
    const result = await request("/api/plans");
    grid.replaceChildren();
    const clientGrid = $("#client-buy-grid");
    if (clientGrid) clientGrid.replaceChildren();
    if (!result.response || !result.response.ok || !Array.isArray(result.data.plans) || !result.data.plans.length) {
      const empty = document.createElement("p");
      empty.className = "public-empty";
      empty.textContent = "Nenhum plano está disponível neste momento.";
      grid.append(empty);
      if (clientGrid) clientGrid.append(empty.cloneNode(true));
      return;
    }
    result.data.plans.forEach((plan) => {
      grid.append(renderPlanCard(plan));
      if (clientGrid) {
        const card = document.createElement("article");
        card.className = "client-buy-card";
        const title = document.createElement("h2");
        title.textContent = plan.gigas;
        const description = document.createElement("p");
        description.textContent = `${plan.tempo} · ${money(plan.price)}`;
        const button = document.createElement("button");
        button.className = "public-button";
        button.type = "button";
        button.textContent = "Escolher plano";
        button.addEventListener("click", () => prepareCheckout(plan.plan));
        card.append(title, description, button);
        clientGrid.append(card);
      }
    });
  }

  function selectPlan(plan) {
    pendingPlan = plan;
    if (currentUser) {
      openClientPage();
      switchPanel("client-buy");
      prepareCheckout(plan);
    } else {
      openAuthDialog("login");
    }
  }

  function createPurchaseCard(purchase) {
    const article = document.createElement("article");
    article.className = "client-order";
    const header = document.createElement("header");
    const title = document.createElement("strong");
    title.textContent = purchase.plan;
    const status = document.createElement("span");
    status.className = "client-order-status";
    status.textContent = "COMPRA APROVADA";
    header.append(title, status);
    const meta = document.createElement("div");
    meta.className = "client-order-meta";
    const date = document.createElement("span");
    date.textContent = `Data: ${text(purchase.date)}`;
    const value = document.createElement("span");
    value.textContent = `Valor: ${money(purchase.price)}`;
    meta.append(date, value);
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Ver dados privados de instalação";
    const activation = document.createElement("div");
    activation.className = "client-activation";
    if (purchase.photo_url) {
      const photo = document.createElement("img");
      photo.className = "client-qr";
      photo.src = purchase.photo_url;
      photo.alt = "Foto do material do eSIM";
      activation.append(photo);
    }
    const code = document.createElement("div");
    code.className = "client-code";
    code.textContent = `SM-DP+: ${text(purchase.smdp)}\n\nCódigo de ativação: ${text(purchase.activation_code)}${purchase.line ? `\n\nLinha: ${text(purchase.line)}` : ""}`;
    const qr = document.createElement("img");
    qr.className = "client-qr";
    qr.src = purchase.qr_url;
    qr.alt = "QR Code privado para instalar o eSIM";
    activation.append(code, qr);
    details.append(summary, activation);
    article.append(header, meta, details);
    return article;
  }

  function renderPurchases(purchases) {
    const targets = ["#client-home-orders", "#client-history-orders", "#client-activation-orders"];
    targets.forEach((selector) => {
      const target = $(selector);
      if (!target) return;
      target.replaceChildren();
      if (!purchases.length) {
        const empty = document.createElement("p");
        empty.className = "public-empty";
        empty.textContent = "Você ainda não possui compras aprovadas.";
        target.append(empty);
        return;
      }
      purchases.forEach((purchase) => target.append(createPurchaseCard(purchase)));
    });
  }

  async function refreshClient() {
    const me = await request("/api/me");
    if (!me.response || !me.response.ok || !me.data.user) {
      currentUser = null;
      closeClientPage();
      return;
    }
    currentUser = me.data.user;
    if (me.data.csrf_token) csrf = me.data.csrf_token;
    openClientPage();
    $("#client-user-name").textContent = currentUser.name;
    $("#client-user-email").textContent = currentUser.email;
    $("#client-first-name").textContent = currentUser.name.split(/\s+/)[0];
    $("#client-balance").textContent = money(currentUser.balance);
    $("#client-balance-card").textContent = money(currentUser.balance);
    $("#client-profile-name").value = currentUser.name;
    $("#client-profile-email").value = currentUser.email;
    const purchases = await request("/api/account/purchases");
    const list = purchases.data.purchases || [];
    $("#client-order-count").textContent = String(list.length);
    renderPurchases(list);
    if (pendingPlan) {
      switchPanel("client-buy");
      prepareCheckout(pendingPlan);
    }
  }

  async function submitAuth(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    const data = Object.fromEntries(new FormData(form));
    if (authMode === "register" && data.password !== data.password_confirmation) {
      setMessage($("#auth-message"), "As senhas não conferem.", "error");
      return;
    }
    if (busy) return;
    busy = true;
    setBusy(button, true);
    const result = await request(`/api/auth/${authMode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    busy = false;
    setBusy(button, false);
    if (!result.response || !result.response.ok) {
      setMessage($("#auth-message"), result.data.error || "Não foi possível continuar.", "error");
      return;
    }
    if (result.data.is_admin) {
      window.location.href = "/admin";
      return;
    }
    await refreshClient();
  }

  async function prepareCheckout(plan) {
    pendingPlan = plan;
    const form = $("#checkout-form");
    const select = $("#checkout-ddd");
    const message = $("#checkout-message");
    const planName = $("#checkout-plan");
    if (!form || !select) return;
    planName.textContent = plan;
    select.replaceChildren();
    setMessage(message, "Consultando DDDs disponíveis…");
    const result = await request(`/api/availability?plan=${encodeURIComponent(plan)}`);
    if (!result.response || !result.response.ok || !result.data.ddds?.length) {
      setMessage(message, "Não há DDD disponível para este plano no momento.", "warning");
      $("#checkout-submit").disabled = true;
      return;
    }
    result.data.ddds.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.ddd;
      option.textContent = `DDD ${item.ddd} · ${item.quantity} disponível(is)`;
      select.append(option);
    });
    $("#checkout-submit").disabled = false;
    setMessage(message, "Selecione o DDD e confirme a compra. Saldo e estoque serão validados no servidor.");
  }

  async function submitCheckout(event) {
    event.preventDefault();
    const button = $("#checkout-submit");
    if (button.disabled || busy || !pendingPlan) return;
    $("#confirm-plan").textContent = pendingPlan;
    $("#confirm-ddd").textContent = $("#checkout-ddd").value;
    openDialog($("#confirm-dialog"), button);
  }

  async function confirmPurchase(event) {
    event.preventDefault();
    const button = $("#confirm-form button[type=submit]");
    if (button.disabled || busy || !pendingPlan) return;
    busy = true;
    setBusy(button, true);
    const result = await request("/api/purchase", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan: pendingPlan, ddd: $("#checkout-ddd").value }) });
    busy = false;
    setBusy(button, false);
    if (!result.response || !result.response.ok) {
      setMessage($("#checkout-message"), result.data.error || "Não foi possível concluir a compra.", "error");
      return;
    }
    setMessage($("#checkout-message"), "Compra aprovada. Os dados privados estão no histórico.", "success");
    pendingPlan = null;
    closeDialog($("#confirm-dialog"));
    await refreshClient();
    switchPanel("client-history");
  }

  async function saveProfile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    if (busy) return;
    busy = true;
    setBusy(button, true);
    const result = await request("/api/account/profile", { method: "POST", body: new FormData(form) });
    busy = false;
    setBusy(button, false);
    const message = $("#profile-message");
    if (!result.response || !result.response.ok) {
      setMessage(message, result.data.error || "Não foi possível salvar o perfil.", "error");
      return;
    }
    setMessage(message, "Perfil atualizado.", "success");
    await refreshClient();
  }

  async function submitWallet(event) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    const message = $("#wallet-message");
    busy = true;
    setBusy(button, true);
    const result = await request("/api/wallet/create-pix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount: Number($("#wallet-amount").value) }) });
    busy = false;
    setBusy(button, false);
    if (!result.response || !result.response.ok) {
      setMessage(message, result.data.error || "Não foi possível gerar o Pix.", "error");
      return;
    }
    $("#wallet-copy").textContent = result.data.charge.copy_paste;
    $("#wallet-output").hidden = false;
    setMessage(message, "Pix gerado. Pague o código e aguarde a confirmação do provedor.", "success");
  }

  async function copyWalletCode() {
    const value = $("#wallet-copy")?.textContent || "";
    try {
      await navigator.clipboard.writeText(value);
      setMessage($("#wallet-message"), "Código copiado.", "success");
    } catch (_error) {
      setMessage($("#wallet-message"), "Não foi possível copiar automaticamente. Selecione o código manualmente.", "warning");
    }
  }

  async function checkCompatibility(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    const resultBox = $("#compatibility-result");
    setMessage(resultBox, "Consultando compatibilidade…");
    resultBox.className = "public-result is-visible";
    setBusy(button, true);
    const model = $("#compatibility-model").value.trim();
    const result = await request(`/api/esim/compatibility?model=${encodeURIComponent(model)}`);
    setBusy(button, false);
    if (!result.response || !result.response.ok) {
      setMessage(resultBox, result.data.error || "Não foi possível consultar agora.", "warning");
      return;
    }
    if (result.data.esim_supported === true) {
      setMessage(resultBox, `Possível compatibilidade encontrada: ${result.data.family}. Confirme a variante e a opção “Adicionar eSIM” no aparelho.`, "success");
    } else {
      setMessage(resultBox, result.data.message || "Confirme se há EID e a opção “Adicionar eSIM” no aparelho.", "warning");
    }
  }

  function bindEvents() {
    $$("[data-open-auth]").forEach((element) => element.addEventListener("click", (event) => { event.preventDefault(); openAuthDialog(element.dataset.openAuth, element); }));
    $$("[data-close-dialog]").forEach((element) => element.addEventListener("click", () => closeDialog($(element.closest(".public-dialog-backdrop")))));
    $$(".public-dialog-backdrop").forEach((backdrop) => backdrop.addEventListener("click", (event) => { if (event.target === backdrop) closeDialog(backdrop); }));
    $$("[data-auth-tab]").forEach((tab) => tab.addEventListener("click", () => setAuthMode(tab.dataset.authTab)));
    $("#login-form")?.addEventListener("submit", (event) => { authMode = "login"; submitAuth(event); });
    $("#register-form")?.addEventListener("submit", (event) => { authMode = "register"; submitAuth(event); });
    $("#compatibility-form")?.addEventListener("submit", checkCompatibility);
    $("#checkout-form")?.addEventListener("submit", submitCheckout);
    $("#confirm-form")?.addEventListener("submit", confirmPurchase);
    $("#profile-form")?.addEventListener("submit", saveProfile);
    $("#wallet-form")?.addEventListener("submit", submitWallet);
    $("#wallet-copy-button")?.addEventListener("click", copyWalletCode);
    $("#client-wallet-button")?.addEventListener("click", (event) => openDialog($("#wallet-dialog"), event.currentTarget));
    $("#client-menu-button")?.addEventListener("click", openClientDrawer);
    $("#client-scrim")?.addEventListener("click", closeClientDrawer);
    $$(".client-nav-button").forEach((button) => button.addEventListener("click", () => switchPanel(button.dataset.panel)));
    $("#client-logout")?.addEventListener("click", async () => { await request("/api/auth/logout", { method: "POST" }); currentUser = null; pendingPlan = null; closeClientPage(); });
    $$("[data-theme-toggle]").forEach((button) => button.addEventListener("click", toggleTheme));
    $("#public-menu-toggle")?.addEventListener("click", () => {
      const menu = $("#public-menu");
      const open = menu.classList.toggle("is-open");
      $("#public-menu-toggle").setAttribute("aria-expanded", String(open));
    });
    $$("#public-menu a").forEach((link) => link.addEventListener("click", () => $("#public-menu")?.classList.remove("is-open")));
    document.addEventListener("keydown", trapFocus);
  }

  async function init() {
    applyTheme(localStorage.getItem("kliktech-theme") || "dark");
    bindEvents();
    await loadCatalog();
    await refreshClient();
  }

  window.KlikTech = { selectPlan, openAuthDialog, closeDialog, toggleTheme, switchPanel };
  init();
})();
