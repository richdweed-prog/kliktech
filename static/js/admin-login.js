(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  let csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  let busy = false;

  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if ((options.method || "GET").toUpperCase() !== "GET") headers.set("X-CSRF-Token", csrf);
    try {
      const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
      let data = {};
      try { data = await response.json(); } catch (_error) { data = {}; }
      if (data.csrf_token) csrf = data.csrf_token;
      return { response, data };
    } catch (_error) {
      return { response: null, data: { error: "Não foi possível conectar ao servidor." } };
    }
  }

  function message(value, type = "") {
    const box = $("#admin-login-message");
    box.textContent = value;
    box.className = `admin-form-message${type ? ` is-${type}` : ""}`;
  }

  async function submitLogin(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = $("#admin-login-form button[type=submit]");
    button.disabled = true;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await request("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    busy = false;
    button.disabled = false;
    if (!result.response || !result.response.ok || !result.data.is_admin) {
      message(result.data.error || "Acesso administrativo não autorizado.", "error");
      return;
    }
    const me = await request("/api/me");
    if (me.data.csrf_token) csrf = me.data.csrf_token;
    $("#admin-login-form").hidden = true;
    $("#admin-2fa-form").hidden = false;
    $("#admin-2fa-code").focus();
    message("Senha validada. Informe o código de seis dígitos do autenticador.");
  }

  async function submitTwoFactor(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = $("#admin-2fa-form button[type=submit]");
    button.disabled = true;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await request("/api/auth/admin-2fa", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    busy = false;
    button.disabled = false;
    if (!result.response || !result.response.ok) {
      message(result.data.error || "Código 2FA inválido.", "error");
      return;
    }
    window.location.href = "/admin/dashboard";
  }

  $("#admin-login-form")?.addEventListener("submit", submitLogin);
  $("#admin-2fa-form")?.addEventListener("submit", submitTwoFactor);
})();
