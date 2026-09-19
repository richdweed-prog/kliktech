(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const adminPath = document.body.dataset.adminPath || "/admin";
  let csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  let busy = false;
  let dashboardData = null;

  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if ((options.method || "GET").toUpperCase() !== "GET") headers.set("X-CSRF-Token", csrf);
    try {
      const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
      let data = {};
      try { data = await response.json(); } catch (_error) { data = {}; }
      if (data.csrf_token) csrf = data.csrf_token;
      if (response.status === 403 && url.startsWith("/api/admin")) window.location.href = adminPath;
      return { response, data };
    } catch (_error) {
      return { response: null, data: { error: "Não foi possível conectar ao servidor." } };
    }
  }

  function setMessage(selector, value, type = "") {
    const box = $(selector);
    if (!box) return;
    box.textContent = value || "";
    box.className = `admin-form-message${type ? ` is-${type}` : ""}`;
  }

  function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); }

  function table(headers, rows) {
    const tableElement = document.createElement("table");
    tableElement.className = "admin-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    headers.forEach((header) => { const th = document.createElement("th"); th.textContent = header; headRow.append(th); });
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    rows.forEach((cells) => { const row = document.createElement("tr"); cells.forEach((cell) => { const td = document.createElement("td"); if (cell instanceof Node) td.append(cell); else td.textContent = String(cell ?? "—"); row.append(td); }); tbody.append(row); });
    tableElement.append(thead, tbody);
    return tableElement;
  }

  function badge(value, warning = false) {
    const span = document.createElement("span");
    span.className = `admin-badge${warning ? " admin-badge--warning" : ""}`;
    span.textContent = value;
    return span;
  }

  function renderChart(months) {
    const chart = $("#admin-chart");
    clear(chart);
    const max = Math.max(...months.map((month) => Number(month.revenue || 0)), 1);
    months.forEach((month) => {
      const column = document.createElement("div");
      column.className = "admin-chart-column";
      const barWrap = document.createElement("div");
      barWrap.className = "admin-chart-bar-wrap";
      const bar = document.createElement("div");
      bar.className = "admin-chart-bar";
      bar.title = `${month.label}: ${Number(month.revenue || 0).toFixed(2)} reais`;
      bar.style.height = `${Math.max(3, Number(month.revenue || 0) / max * 100)}%`;
      barWrap.append(bar);
      const label = document.createElement("span");
      label.textContent = month.label;
      column.append(barWrap, label);
      chart.append(column);
    });
  }

  function renderRecent(targetSelector, recent) {
    const target = $(targetSelector);
    clear(target);
    if (!recent.length) { target.textContent = "Nenhum pedido registrado."; return; }
    const rows = recent.map((item) => [item.customer, item.email, item.plan, `R$ ${Number(item.price).toFixed(2).replace(".", ",")}`, item.date, badge("Aprovada")]);
    target.append(table(["Cliente", "E-mail", "Plano", "Valor", "Data", "Status"], rows));
  }

  async function loadDashboard() {
    const result = await request("/api/admin/dashboard");
    if (!result.response || !result.response.ok) { setMessage("#admin-updated", result.data.error || "Falha ao carregar resumo.", "error"); return; }
    dashboardData = result.data;
    const metrics = result.data.metrics;
    $("#metric-sales-value").textContent = `R$ ${Number(metrics.sales_value).toFixed(2).replace(".", ",")}`;
    $("#metric-sales-count").textContent = String(metrics.sales_count);
    $("#metric-pix-count").textContent = String(metrics.pending_pix_count);
    $("#metric-stock").textContent = String(metrics.available_stock);
    $("#admin-updated").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
    renderChart(result.data.monthly || []);
    renderRecent("#admin-recent", result.data.recent || []);
    renderRecent("#admin-sales-table", result.data.recent || []);
  }

  async function loadPlans() {
    const result = await request("/api/admin/plans");
    if (!result.response || !result.response.ok) return;
    const select = $("#inventory-plan");
    clear(select);
    result.data.plans.filter((plan) => plan.active).forEach((plan) => { const option = document.createElement("option"); option.value = plan.plan; option.textContent = `${plan.plan} · R$ ${Number(plan.price).toFixed(2).replace(".", ",")}`; select.append(option); });
    const target = $("#admin-plans-table");
    clear(target);
    const rows = result.data.plans.map((plan) => [plan.plan, plan.gigas, plan.tempo, `R$ ${Number(plan.price).toFixed(2).replace(".", ",")}`, badge(plan.active ? "Ativo" : "Inativo", !plan.active)]);
    target.append(table(["Plano", "Franquia", "Ciclo", "Preço", "Status"], rows));
  }

  async function loadPix() {
    const result = await request("/api/admin/pix?limit=200");
    const target = $("#admin-pix-table");
    clear(target);
    if (!result.response || !result.response.ok) { target.textContent = result.data.error || "Falha ao carregar Pix."; return; }
    const rows = result.data.items.map((item) => [item.account_id, item.customer, item.email, `R$ ${Number(item.amount).toFixed(2).replace(".", ",")}`, badge(item.status, item.status !== "PAID"), item.created_at, item.paid_at || "—"]);
    target.append(table(["Conta", "Cliente", "E-mail", "Valor", "Status", "Criado", "Pago"], rows));
  }

  async function loadAbandoned() {
    const result = await request("/api/admin/abandoned?limit=200");
    const target = $("#admin-abandoned-table");
    clear(target);
    if (!result.response || !result.response.ok) { target.textContent = result.data.error || "Falha ao carregar carrinhos."; return; }
    const rows = result.data.items.map((item) => [item.account_id || "Visitante", item.customer, item.email, item.plan, item.updated_at, badge("Abandonado", true)]);
    target.append(table(["Conta", "Cliente", "E-mail", "Plano", "Última atividade", "Status"], rows));
  }

  async function loadUsers() {
    const result = await request("/api/admin/users");
    const target = $("#admin-users-table");
    clear(target);
    if (!result.response || !result.response.ok) { target.textContent = result.data.error || "Falha ao carregar usuários."; return; }
    const rows = result.data.users.map((user) => {
      const action = document.createElement("button");
      action.className = "admin-button admin-button--ghost";
      action.type = "button";
      action.textContent = user.blocked ? "Desbloquear" : "Bloquear";
      action.disabled = user.is_admin;
      action.addEventListener("click", () => changeAccess(user.id, !user.blocked));
      return [user.id, user.name, user.email, user.last_ip, user.blocked ? badge("Bloqueado", true) : badge("Liberado"), action];
    });
    target.append(table(["ID", "Nome", "E-mail", "Último IP", "Acesso", "Ação"], rows));
  }

  async function loadStock() {
    const result = await request("/api/admin/inventory");
    const target = $("#admin-stock-table");
    clear(target);
    if (!result.response || !result.response.ok) { target.textContent = result.data.error || "Falha ao carregar estoque."; return; }
    const rows = result.data.items.map((item) => {
      const action = document.createElement("button");
      action.className = "admin-button admin-button--danger";
      action.type = "button";
      action.textContent = "Excluir";
      action.disabled = item.sold;
      action.addEventListener("click", () => deleteStock(item.id));
      return [item.plan, item.model, item.ddd || "—", item.sold ? badge("Vendido", true) : badge("Disponível"), item.created_at, action];
    });
    target.append(table(["Plano", "Modelo", "DDD", "Status", "Entrada", "Ação"], rows));
  }

  async function changeAccess(id, blocked) {
    if (!window.confirm(`${blocked ? "Bloquear" : "Desbloquear"} esta conta?`)) return;
    const result = await request(`/api/admin/users/${encodeURIComponent(id)}/access`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ blocked }) });
    if (!result.response || !result.response.ok) window.alert(result.data.error || "Não foi possível alterar o acesso.");
    await loadUsers();
  }

  async function deleteStock(id) {
    if (!window.confirm("Excluir este eSIM não vendido do estoque?")) return;
    const result = await request(`/api/admin/inventory/${id}`, { method: "DELETE" });
    if (!result.response || !result.response.ok) window.alert(result.data.error || "Não foi possível excluir o eSIM.");
    await loadStock();
    await loadPlans();
  }

  async function createPlan(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = $("#plan-form button[type=submit]"); button.disabled = true;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    data.featured = event.currentTarget.elements.featured.checked;
    const result = await request("/api/admin/plans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    busy = false; button.disabled = false;
    if (!result.response || !result.response.ok) { setMessage("#plan-message", result.data.error || "Não foi possível criar o slot.", "error"); return; }
    event.currentTarget.reset(); setMessage("#plan-message", "Slot criado.", "success"); await loadPlans();
  }

  async function addInventory(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = $("#inventory-form button[type=submit]"); button.disabled = true;
    const result = await request("/api/admin/inventory", { method: "POST", body: new FormData(event.currentTarget) });
    busy = false; button.disabled = false;
    if (!result.response || !result.response.ok) { setMessage("#inventory-message", result.data.error || "Não foi possível adicionar o eSIM.", "error"); return; }
    event.currentTarget.reset(); setMessage("#inventory-message", "eSIM adicionado ao estoque.", "success"); await loadStock();
  }

  async function addBatch(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = $("#batch-form button[type=submit]"); button.disabled = true;
    const result = await request("/api/admin/inventory/batch", { method: "POST", body: new FormData(event.currentTarget) });
    busy = false; button.disabled = false;
    if (!result.response || !result.response.ok) { setMessage("#batch-message", result.data.errors?.join(" ") || result.data.error || "Lote inválido.", "error"); return; }
    event.currentTarget.reset(); setMessage("#batch-message", `${result.data.added} eSIM(s) adicionados.`, "success"); await loadStock();
  }

  function openSidebar() { $("#admin-sidebar").classList.add("is-open"); $("#admin-scrim").classList.add("is-visible"); $("#admin-menu-button").setAttribute("aria-expanded", "true"); }
  function closeSidebar() { $("#admin-sidebar").classList.remove("is-open"); $("#admin-scrim").classList.remove("is-visible"); $("#admin-menu-button").setAttribute("aria-expanded", "false"); }

  async function switchPanel(panelId) {
    $$(".admin-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === panelId));
    $$(".admin-nav button").forEach((button) => button.classList.toggle("is-active", button.dataset.panel === panelId));
    closeSidebar();
    if (panelId === "admin-overview" || panelId === "admin-sales") await loadDashboard();
    if (panelId === "admin-pix") await loadPix();
    if (panelId === "admin-abandoned") await loadAbandoned();
    if (panelId === "admin-stock") await loadStock();
    if (panelId === "admin-users") await loadUsers();
    if (panelId === "admin-add") { await loadPlans(); await loadStock(); }
  }

  async function init() {
    $$(".admin-nav button").forEach((button) => button.addEventListener("click", () => switchPanel(button.dataset.panel)));
    $("#admin-menu-button")?.addEventListener("click", openSidebar);
    $("#admin-sidebar-close")?.addEventListener("click", closeSidebar);
    $("#admin-scrim")?.addEventListener("click", closeSidebar);
    $("#admin-logout")?.addEventListener("click", async () => { await request("/api/auth/logout", { method: "POST" }); window.location.href = "/"; });
    $("#plan-form")?.addEventListener("submit", createPlan);
    $("#inventory-form")?.addEventListener("submit", addInventory);
    $("#batch-form")?.addEventListener("submit", addBatch);
    await loadDashboard();
    await loadPlans();
    await loadStock();
  }
  init();
})();
