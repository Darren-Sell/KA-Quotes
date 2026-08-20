(function () {
  "use strict";

  /* ---------- API helper ---------- */
  async function api(method, path, body) {
    const res = await fetch("/api" + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) {
      const err = new Error((data && (data.message || data.error)) || ("Request failed (" + res.status + ")"));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  /* ---------- State ---------- */
  const state = {
    me: null,
    settings: null,
    products: [],
    customers: [],
    quotes: [],
    users: [],
    editingQuoteId: null,
    skipNextAutoReset: false,
  };

  const fmt = (n) => (state.settings ? state.settings.currency : "£") + (Number(n) || 0).toFixed(2);
  const todayISO = () => new Date().toISOString().slice(0, 10);
  const $ = (id) => document.getElementById(id);

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
  }

  /* ---------- Boot / auth flow ---------- */
  async function boot() {
    let status;
    try {
      status = await api("GET", "/setup/status");
    } catch (e) {
      document.body.innerHTML = "<p style='padding:40px;font-family:sans-serif;'>Couldn't reach the server. Please refresh.</p>";
      return;
    }
    if (status.needsSetup) {
      showScreen("setupScreen");
      return;
    }
    const meRes = await api("GET", "/auth/me");
    if (!meRes.user) {
      showScreen("loginScreen");
      return;
    }
    state.me = meRes.user;
    await loadApp();
  }

  function showScreen(id) {
    ["setupScreen", "loginScreen", "appShell"].forEach(s => $(s).hidden = (s !== id));
  }

  $("setupSubmit").addEventListener("click", async () => {
    const name = $("setupName").value.trim();
    const email = $("setupEmail").value.trim();
    const password = $("setupPassword").value;
    $("setupError").textContent = "";
    try {
      const r = await api("POST", "/setup", { name, email, password });
      state.me = r.user;
      await loadApp();
    } catch (e) {
      $("setupError").textContent = e.message === "weak_password" ? "Password must be at least 8 characters." : friendlyError(e);
    }
  });

  $("loginSubmit").addEventListener("click", doLogin);
  $("loginPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
  async function doLogin() {
    const email = $("loginEmail").value.trim();
    const password = $("loginPassword").value;
    $("loginError").textContent = "";
    try {
      const r = await api("POST", "/auth/login", { email, password });
      state.me = r.user;
      await loadApp();
    } catch (e) {
      $("loginError").textContent = e.data && e.data.error === "invalid_credentials"
        ? "Incorrect email or password." : friendlyError(e);
    }
  }

  $("logoutBtn").addEventListener("click", async () => {
    await api("POST", "/auth/logout");
    state.me = null;
    $("loginEmail").value = ""; $("loginPassword").value = "";
    showScreen("loginScreen");
  });

  function friendlyError(e) {
    return (e && e.message) ? e.message : "Something went wrong — please try again.";
  }

  async function loadApp() {
    const [settings, products, customers, quotes] = await Promise.all([
      api("GET", "/settings"),
      api("GET", "/products"),
      api("GET", "/customers"),
      api("GET", "/quotes"),
    ]);
    state.settings = settings;
    state.products = products.products;
    state.customers = customers.customers;
    state.quotes = quotes.quotes;

    if (state.me.role === "admin") {
      const u = await api("GET", "/users");
      state.users = u.users;
      $("usersTabBtn").hidden = false;
      $("exportBtn").hidden = false;
    } else {
      $("usersTabBtn").hidden = true;
      $("exportBtn").hidden = true;
    }

    $("currentUserName").textContent = state.me.name;
    $("currentUserRole").textContent = state.me.role === "admin" ? "Admin" : "Member";
    $("brandName").textContent = state.settings.companyName;
    $("brandMark").textContent = initials(state.settings.companyName);
    $("settingsAdminHint").textContent = state.me.role === "admin"
      ? "These details appear on every printed quote."
      : "Only admins can change company details — ask one of your admins if something needs updating.";
    $("saveSettingsBtn").hidden = state.me.role !== "admin";
    $("sCompanyName").disabled = $("sCompanyAddress").disabled = $("sCompanyEmail").disabled =
      $("sCompanyPhone").disabled = $("sCurrency").disabled = $("sDefaultTax").disabled =
      $("sPrefix").disabled = $("sDefaultNotes").disabled = state.me.role !== "admin";

    loadSettingsForm();
    populateCustomerSelect();
    renderCatalogQuickAdd();
    renderProducts();
    renderCustomers();
    if (state.me.role === "admin") renderUsers();
    renderDashboard();
    showScreen("appShell");
    showView("dashboard");
  }

  /* ---------- Tabs ---------- */
  function showView(name) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.querySelectorAll("nav.tabs button[data-view]").forEach(b => b.classList.remove("active"));
    $("view-" + name).classList.add("active");
    const tabBtn = document.querySelector(`nav.tabs button[data-view="${name}"]`);
    if (tabBtn) tabBtn.classList.add("active");
    if (name === "dashboard") renderDashboard();
    if (name === "quotes") renderQuotesList();
    if (name === "products") renderProducts();
    if (name === "customers") renderCustomers();
    if (name === "users") renderUsers();
    if (name === "newquote" && !state.editingQuoteId && !state.skipNextAutoReset) resetQuoteForm();
    if (name === "newquote") {
      // The description textareas may have been measured for auto-grow while
      // this view was still hidden (display:none gives scrollHeight 0), e.g.
      // when editing/duplicating a quote — re-measure now that it's visible.
      document.querySelectorAll("#qItemsBody .it-desc").forEach(autoGrow);
    }
    state.skipNextAutoReset = false;
  }
  document.querySelectorAll("nav.tabs button[data-view]").forEach(b => {
    b.addEventListener("click", () => showView(b.dataset.view));
  });
  document.querySelectorAll("[data-goto]").forEach(b => {
    b.addEventListener("click", () => { state.editingQuoteId = null; showView(b.dataset.goto); });
  });

  /* ---------- Theme ---------- */
  const themeBtn = $("themeToggleBtn");
  themeBtn.addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.getAttribute("data-theme") === "dark";
    root.setAttribute("data-theme", isDark ? "light" : "dark");
    themeBtn.textContent = isDark ? "🌙" : "☀️";
  });

  function initials(name) {
    return (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("") || "Q";
  }

  /* ---------- Dashboard ---------- */
  function renderDashboard() {
    const total = state.quotes.length;
    const accepted = state.quotes.filter(q => q.status === "accepted");
    const pipelineValue = state.quotes
      .filter(q => q.status === "sent" || q.status === "draft")
      .reduce((s, q) => s + quoteTotal(q), 0);
    const acceptedValue = accepted.reduce((s, q) => s + quoteTotal(q), 0);
    const thisMonth = state.quotes.filter(q => (q.date || "").slice(0, 7) === todayISO().slice(0, 7)).length;

    $("statRow").innerHTML = `
      <div class="stat-tile"><div class="label">Total quotes</div><div class="value">${total}</div></div>
      <div class="stat-tile"><div class="label">Open pipeline value</div><div class="value">${fmt(pipelineValue)}</div></div>
      <div class="stat-tile"><div class="label">Accepted value</div><div class="value accent-good">${fmt(acceptedValue)}</div></div>
      <div class="stat-tile"><div class="label">Created this month</div><div class="value">${thisMonth}</div></div>
    `;

    const recent = [...state.quotes].sort((a, b) => (b.date || "").localeCompare(a.date || "")).slice(0, 6);
    const body = $("recentQuotesBody");
    body.innerHTML = recent.length ? recent.map(rowHtml).join("") : emptyRow(6, "No quotes yet — create your first one.");
    wireRowButtons(body);
  }

  function renderQuotesList() {
    const body = $("allQuotesBody");
    const rows = [...state.quotes].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    body.innerHTML = rows.length ? rows.map(q => rowHtml(q, true)).join("") : emptyRow(7, "No quotes yet.");
    wireRowButtons(body);
  }

  function rowHtml(q, withValidUntil) {
    const cust = customerName(q.customerId);
    return `
      <tr data-id="${q.id}">
        <td>${escapeHtml(q.number)}</td>
        <td>${escapeHtml(cust)}</td>
        <td>${q.date || ""}</td>
        ${withValidUntil ? `<td>${q.validUntil || ""}</td>` : ""}
        <td>${statusBadge(q.status)}</td>
        <td class="num">${fmt(quoteTotal(q))}</td>
        <td class="row-actions">
          <button class="ghost icon-btn edit-quote" title="Edit">✏️</button>
          <button class="ghost icon-btn duplicate-quote" title="Duplicate as a new quote">⧉</button>
          <button class="ghost icon-btn view-quote" title="Preview / print">👁</button>
          <button class="ghost icon-btn danger delete-quote" title="Delete">🗑</button>
        </td>
      </tr>`;
  }

  function wireRowButtons(body) {
    body.querySelectorAll(".edit-quote").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const id = e.target.closest("tr").dataset.id;
        loadQuoteIntoForm(id);
        showView("newquote");
      });
    });
    body.querySelectorAll(".duplicate-quote").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const id = e.target.closest("tr").dataset.id;
        duplicateQuoteIntoForm(id);
        showView("newquote");
      });
    });
    body.querySelectorAll(".view-quote").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const id = e.target.closest("tr").dataset.id;
        const q = state.quotes.find(q => q.id === id);
        if (q) openPreview(q);
      });
    });
    body.querySelectorAll(".delete-quote").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        if (!confirm("Delete this quote? This can't be undone.")) return;
        await api("DELETE", "/quotes/" + id);
        state.quotes = state.quotes.filter(q => q.id !== id);
        renderDashboard(); renderQuotesList();
      });
    });
  }

  function statusBadge(status) {
    const labels = { draft: "Draft", sent: "Sent", accepted: "Accepted", rejected: "Rejected", expired: "Expired" };
    return `<span class="badge ${status}"><span class="dot"></span>${labels[status] || status}</span>`;
  }
  function emptyRow(colspan, text) { return `<tr class="empty-row"><td colspan="${colspan}">${text}</td></tr>`; }
  function customerName(id) {
    const c = state.customers.find(c => c.id === id);
    return c ? c.company : "—";
  }
  function quoteTotal(q) {
    const subtotal = (q.items || []).reduce((s, it) => s + it.qty * it.unitPrice, 0);
    const afterDiscount = subtotal * (1 - (q.discount || 0) / 100);
    return afterDiscount * (1 + (q.tax || 0) / 100);
  }

  /* ---------- Products ---------- */
  function renderProducts() {
    const body = $("productsBody");
    body.innerHTML = state.products.length ? state.products.map(p => `
      <tr data-id="${p.id}">
        <td class="pn-cell">${escapeHtml(p.sku || "")}</td>
        <td class="desc-cell">${escapeHtml(p.name)}</td>
        <td class="num">${fmt(p.price)}</td>
        <td class="row-actions"><button class="ghost icon-btn danger del-product" title="Delete">🗑</button></td>
      </tr>`).join("") : emptyRow(4, "No products yet — add your parts and services above.");
    body.querySelectorAll(".del-product").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        await api("DELETE", "/products/" + id);
        state.products = state.products.filter(p => p.id !== id);
        renderProducts(); renderCatalogQuickAdd();
      });
    });
  }

  $("addProductBtn").addEventListener("click", async () => {
    const name = $("pName").value.trim();
    const sku = $("pSku").value.trim();
    const price = parseFloat($("pPrice").value) || 0;
    if (!name) { alert("Enter a description."); return; }
    const product = await api("POST", "/products", { name, sku, price });
    state.products.push(product);
    state.products.sort((a, b) => a.name.localeCompare(b.name));
    $("pName").value = ""; $("pSku").value = ""; $("pPrice").value = "";
    autoGrow($("pName"));
    renderProducts(); renderCatalogQuickAdd();
  });
  $("pName").addEventListener("input", (e) => autoGrow(e.target));
  autoGrow($("pName"));

  /* ---------- Customers ---------- */
  function renderCustomers() {
    const body = $("customersBody");
    body.innerHTML = state.customers.length ? state.customers.map(c => `
      <tr data-id="${c.id}">
        <td>${escapeHtml(c.company)}</td>
        <td>${escapeHtml(c.contact || "")}</td>
        <td>${escapeHtml(c.email || "")}</td>
        <td class="row-actions"><button class="ghost icon-btn danger del-customer" title="Delete">🗑</button></td>
      </tr>`).join("") : emptyRow(4, "No customers yet — add one above.");
    body.querySelectorAll(".del-customer").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        await api("DELETE", "/customers/" + id);
        state.customers = state.customers.filter(c => c.id !== id);
        renderCustomers(); populateCustomerSelect();
      });
    });
  }

  $("addCustomerBtn").addEventListener("click", async () => {
    const company = $("cCompany").value.trim();
    const contact = $("cContact").value.trim();
    const email = $("cEmail").value.trim();
    const phone = $("cPhone").value.trim();
    const address = $("cAddress").value.trim();
    if (!company) { alert("Enter a company name."); return; }
    const customer = await api("POST", "/customers", { company, contact, email, phone, address });
    state.customers.push(customer);
    state.customers.sort((a, b) => a.company.localeCompare(b.company));
    ["cCompany", "cContact", "cEmail", "cPhone", "cAddress"].forEach(id => $(id).value = "");
    renderCustomers(); populateCustomerSelect();
  });

  /* ---------- Team / users (admin) ---------- */
  function renderUsers() {
    const body = $("usersBody");
    body.innerHTML = state.users.length ? state.users.map(u => `
      <tr data-id="${u.id}">
        <td>${escapeHtml(u.name)}</td>
        <td>${escapeHtml(u.email)}</td>
        <td><span class="badge role-${u.role}"><span class="dot"></span>${u.role === "admin" ? "Admin" : "Member"}</span></td>
        <td class="row-actions">
          ${u.id === state.me.id ? "" : `<button class="ghost icon-btn danger del-user" title="Remove">🗑</button>`}
        </td>
      </tr>`).join("") : emptyRow(4, "No team members yet.");
    body.querySelectorAll(".del-user").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        const u = state.users.find(u => u.id === id);
        if (!confirm(`Remove ${u ? u.name : "this user"}? They will no longer be able to log in.`)) return;
        try {
          await api("DELETE", "/users/" + id);
          state.users = state.users.filter(u => u.id !== id);
          renderUsers();
        } catch (err) {
          alert(err.data && err.data.error === "cannot_delete_last_admin"
            ? "You can't remove the last remaining admin." : friendlyError(err));
        }
      });
    });
  }

  $("addUserBtn").addEventListener("click", async () => {
    const name = $("uName").value.trim();
    const email = $("uEmail").value.trim();
    const password = $("uPassword").value;
    const role = $("uRole").value;
    $("userFormError").textContent = "";
    if (!name || !email) { $("userFormError").textContent = "Enter a name and email."; return; }
    try {
      const user = await api("POST", "/users", { name, email, password, role });
      state.users.push(user);
      $("uName").value = ""; $("uEmail").value = ""; $("uPassword").value = ""; $("uRole").value = "member";
      renderUsers();
    } catch (err) {
      const map = {
        weak_password: "Password must be at least 8 characters.",
        email_taken: "That email is already in use.",
        invalid_email: "Enter a valid email address.",
      };
      $("userFormError").textContent = (err.data && map[err.data.error]) || friendlyError(err);
    }
  });

  /* ---------- Settings ---------- */
  function loadSettingsForm() {
    $("sCompanyName").value = state.settings.companyName;
    $("sCompanyAddress").value = state.settings.companyAddress;
    $("sCompanyEmail").value = state.settings.companyEmail;
    $("sCompanyPhone").value = state.settings.companyPhone;
    $("sCurrency").value = state.settings.currency;
    $("sDefaultTax").value = state.settings.defaultTax;
    $("sPrefix").value = state.settings.prefix;
    $("sDefaultNotes").value = state.settings.defaultNotes || "";
  }

  $("saveSettingsBtn").addEventListener("click", async () => {
    const payload = {
      companyName: $("sCompanyName").value.trim() || "Your company",
      companyAddress: $("sCompanyAddress").value.trim(),
      companyEmail: $("sCompanyEmail").value.trim(),
      companyPhone: $("sCompanyPhone").value.trim(),
      currency: $("sCurrency").value.trim() || "£",
      defaultTax: parseFloat($("sDefaultTax").value) || 0,
      prefix: $("sPrefix").value.trim() || "Q-",
      defaultNotes: $("sDefaultNotes").value,
    };
    state.settings = await api("PUT", "/settings", payload);
    $("brandName").textContent = state.settings.companyName;
    $("brandMark").textContent = initials(state.settings.companyName);
    renderDashboard();
    alert("Settings saved.");
  });

  $("changePasswordBtn").addEventListener("click", async () => {
    const currentPassword = $("pwCurrent").value;
    const newPassword = $("pwNew").value;
    $("pwError").textContent = "";
    try {
      await api("PATCH", "/auth/password", { currentPassword, newPassword });
      $("pwCurrent").value = ""; $("pwNew").value = "";
      alert("Password updated.");
    } catch (err) {
      const map = { wrong_current_password: "Current password is incorrect.", weak_password: "New password must be at least 8 characters." };
      $("pwError").textContent = (err.data && map[err.data.error]) || friendlyError(err);
    }
  });

  /* ---------- Export (admin backup) ---------- */
  $("exportBtn").addEventListener("click", async () => {
    const data = await api("GET", "/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `kelston-quotes-backup-${todayISO()}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  });

  /* ---------- Quote builder ---------- */
  function populateCustomerSelect() {
    const sel = $("qCustomer");
    const current = sel.value;
    sel.innerHTML = `<option value="">— Select customer —</option>` +
      state.customers.map(c => `<option value="${c.id}">${escapeHtml(c.company)}</option>`).join("");
    if (current) sel.value = current;
  }

  let quoteItems = [];

  async function resetQuoteForm() {
    state.editingQuoteId = null;
    $("quoteFormHeading").textContent = "New quote";
    $("qNumber").value = "(assigned automatically when saved)";
    try {
      const r = await api("GET", "/quotes/next-number");
      $("qNumber").value = r.number + " (next available — confirmed on save)";
    } catch (e) { /* non-fatal */ }
    $("qDate").value = todayISO();
    $("qValidUntil").value = "";
    $("qDiscount").value = 0;
    $("qTax").value = state.settings ? state.settings.defaultTax : 20;
    $("qNotes").value = state.settings ? (state.settings.defaultNotes || "") : "";
    $("qStatus").value = "draft";
    $("qCustomer").value = "";
    $("quoteFormError").textContent = "";
    quoteItems = [];
    renderQuoteItems();
  }

  function loadQuoteIntoForm(id) {
    const q = state.quotes.find(q => q.id === id);
    if (!q) return;
    state.editingQuoteId = id;
    $("quoteFormHeading").textContent = "Edit quote";
    $("qNumber").value = q.number;
    $("qDate").value = q.date;
    $("qValidUntil").value = q.validUntil || "";
    $("qDiscount").value = q.discount || 0;
    $("qTax").value = q.tax != null ? q.tax : (state.settings ? state.settings.defaultTax : 20);
    $("qNotes").value = q.notes || "";
    $("qStatus").value = q.status || "draft";
    $("quoteFormError").textContent = "";
    populateCustomerSelect();
    $("qCustomer").value = q.customerId || "";
    quoteItems = (q.items || []).map(it => ({ ...it }));
    renderQuoteItems();
  }

  async function duplicateQuoteIntoForm(id) {
    const q = state.quotes.find(q => q.id === id);
    if (!q) return;
    // Set synchronously (before any await) so showView()'s auto-reset check,
    // which runs right after this function is called, sees it in time.
    state.skipNextAutoReset = true;
    state.editingQuoteId = null; // saving creates a brand new quote, never overwrites the original
    $("quoteFormHeading").textContent = `New quote (copied from ${q.number})`;
    $("qNumber").value = "(assigned automatically when saved)";
    try {
      const r = await api("GET", "/quotes/next-number");
      $("qNumber").value = r.number + " (next available — confirmed on save)";
    } catch (e) { /* non-fatal */ }
    $("qDate").value = todayISO();
    $("qValidUntil").value = "";
    $("qDiscount").value = q.discount || 0;
    $("qTax").value = q.tax != null ? q.tax : (state.settings ? state.settings.defaultTax : 20);
    $("qNotes").value = q.notes || "";
    $("qStatus").value = "draft"; // a copy always starts fresh, regardless of the original's status
    $("quoteFormError").textContent = "";
    populateCustomerSelect();
    $("qCustomer").value = q.customerId || "";
    quoteItems = (q.items || []).map(it => ({ ...it, id: "tmp" + Math.random().toString(36).slice(2) }));
    renderQuoteItems();
  }

  function addQuoteItem(prefill) {
    quoteItems.push(Object.assign({ id: "tmp" + Math.random().toString(36).slice(2), partNumber: "", description: "", qty: 1, unitPrice: 0 }, prefill || {}));
    renderQuoteItems();
  }

  function autoGrow(el) {
    if (!el.value) { el.style.height = ""; return; } // let CSS min-height govern; scrollHeight would include wrapped placeholder text
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  function renderQuoteItems() {
    const body = $("qItemsBody");
    body.innerHTML = quoteItems.length ? quoteItems.map(it => `
      <tr data-id="${it.id}">
        <td>
          <input type="text" class="it-partnum" placeholder="Part number" value="${escapeHtml(it.partNumber || "")}">
          <textarea class="it-desc" rows="1" placeholder="Description — add specs, part notes, etc.">${escapeHtml(it.description)}</textarea>
        </td>
        <td><input type="number" class="it-qty" min="0" step="1" value="${it.qty}"></td>
        <td><input type="number" class="it-price" min="0" step="0.01" value="${it.unitPrice}"></td>
        <td class="num it-total">${fmt(it.qty * it.unitPrice)}</td>
        <td><button class="ghost icon-btn danger it-remove" title="Remove">🗑</button></td>
      </tr>`).join("") : emptyRow(5, "No line items yet — add one or use quick-add from the catalog.");

    body.querySelectorAll("tr").forEach(tr => {
      const id = tr.dataset.id;
      const item = quoteItems.find(i => i.id === id);
      if (!item) return;
      const partEl = tr.querySelector(".it-partnum");
      if (partEl) {
        partEl.addEventListener("input", (e) => { item.partNumber = e.target.value; });
      }
      const descEl = tr.querySelector(".it-desc");
      if (descEl) {
        autoGrow(descEl);
        descEl.addEventListener("input", (e) => { item.description = e.target.value; autoGrow(e.target); });
      }
      tr.querySelector(".it-qty")?.addEventListener("input", (e) => { item.qty = parseFloat(e.target.value) || 0; updateQuoteTotals(); tr.querySelector(".it-total").textContent = fmt(item.qty * item.unitPrice); });
      tr.querySelector(".it-price")?.addEventListener("input", (e) => { item.unitPrice = parseFloat(e.target.value) || 0; updateQuoteTotals(); tr.querySelector(".it-total").textContent = fmt(item.qty * item.unitPrice); });
      tr.querySelector(".it-remove")?.addEventListener("click", () => { quoteItems = quoteItems.filter(i => i.id !== id); renderQuoteItems(); });
    });
    updateQuoteTotals();
  }

  function updateQuoteTotals() {
    const subtotal = quoteItems.reduce((s, it) => s + it.qty * it.unitPrice, 0);
    const discount = parseFloat($("qDiscount").value) || 0;
    const tax = parseFloat($("qTax").value) || 0;
    const afterDiscount = subtotal * (1 - discount / 100);
    const total = afterDiscount * (1 + tax / 100);
    $("qSubtotal").textContent = fmt(subtotal);
    $("qGrandTotal").textContent = fmt(total);
  }
  $("qDiscount").addEventListener("input", updateQuoteTotals);
  $("qTax").addEventListener("input", updateQuoteTotals);
  $("addItemBtn").addEventListener("click", () => addQuoteItem());

  function renderCatalogQuickAdd() {
    const wrap = $("catalogQuickAdd");
    wrap.innerHTML = state.products.length ? state.products.map(p => {
      const lines = (p.name || "").split("\n");
      const firstLine = lines[0] || "";
      const more = lines.length > 1 ? " …" : "";
      return `
      <button class="ghost quick-add-btn" data-id="${p.id}" style="width:100%; justify-content:space-between; margin-bottom:6px;">
        <span>${p.sku ? `<strong>${escapeHtml(p.sku)}</strong> — ` : ""}${escapeHtml(firstLine)}${more}</span><span>${fmt(p.price)}</span>
      </button>`;
    }).join("") : `<p class="hint">Add products in the Products tab to quick-add them here.</p>`;
    wrap.querySelectorAll(".quick-add-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = state.products.find(p => p.id === btn.dataset.id);
        if (p) addQuoteItem({ partNumber: p.sku || "", description: p.name, qty: 1, unitPrice: p.price });
      });
    });
  }

  $("saveQuoteBtn").addEventListener("click", async () => {
    const customerId = $("qCustomer").value;
    $("quoteFormError").textContent = "";
    if (!customerId) { $("quoteFormError").textContent = "Select a customer."; return; }
    if (!quoteItems.length) { $("quoteFormError").textContent = "Add at least one line item."; return; }

    const payload = {
      customerId,
      date: $("qDate").value || todayISO(),
      validUntil: $("qValidUntil").value,
      items: quoteItems.map(it => ({ partNumber: it.partNumber || "", description: it.description, qty: it.qty, unitPrice: it.unitPrice })),
      discount: parseFloat($("qDiscount").value) || 0,
      tax: parseFloat($("qTax").value) || 0,
      notes: $("qNotes").value,
      status: $("qStatus").value,
    };

    try {
      let saved;
      if (state.editingQuoteId) {
        saved = await api("PUT", "/quotes/" + state.editingQuoteId, payload);
        const idx = state.quotes.findIndex(q => q.id === saved.id);
        if (idx >= 0) state.quotes[idx] = saved; else state.quotes.push(saved);
      } else {
        saved = await api("POST", "/quotes", payload);
        state.quotes.push(saved);
      }
      state.editingQuoteId = null;
      renderDashboard();
      showView("quotes");
    } catch (e) {
      $("quoteFormError").textContent = friendlyError(e);
    }
  });

  $("clearQuoteBtn").addEventListener("click", () => resetQuoteForm());
  $("previewQuoteBtn").addEventListener("click", () => {
    const customerId = $("qCustomer").value;
    const draft = {
      number: state.editingQuoteId ? $("qNumber").value : $("qNumber").value.replace(/\s*\(.*\)$/, ""),
      customerId,
      date: $("qDate").value || todayISO(),
      validUntil: $("qValidUntil").value,
      items: quoteItems,
      discount: parseFloat($("qDiscount").value) || 0,
      tax: parseFloat($("qTax").value) || 0,
      notes: $("qNotes").value,
      status: $("qStatus").value,
    };
    openPreview(draft);
  });

  /* ---------- Preview / print ---------- */
  function openPreview(q) {
    const cust = state.customers.find(c => c.id === q.customerId);
    const subtotal = (q.items || []).reduce((s, it) => s + it.qty * it.unitPrice, 0);
    const discountAmt = subtotal * ((q.discount || 0) / 100);
    const afterDiscount = subtotal - discountAmt;
    const taxAmt = afterDiscount * ((q.tax || 0) / 100);
    const total = afterDiscount + taxAmt;

    const sheet = $("previewSheet");
    sheet.innerHTML = `
      <div class="p-head">
        <div>
          <div class="p-brand">${escapeHtml(state.settings.companyName)}</div>
          <div class="p-brand-sub">${escapeHtml(state.settings.companyAddress || "")}${state.settings.companyEmail ? "\n" + state.settings.companyEmail : ""}${state.settings.companyPhone ? "\n" + state.settings.companyPhone : ""}</div>
        </div>
        <div class="p-title">
          <div class="q">QUOTE</div>
          <div class="meta">${escapeHtml(q.number || "")}<br>Date: ${q.date || ""}${q.validUntil ? "<br>Valid until: " + q.validUntil : ""}</div>
        </div>
      </div>
      <div class="p-parties">
        <div>
          <div class="label">Prepared for</div>
          <div>${cust ? escapeHtml(cust.company) : "—"}</div>
          ${cust && cust.contact ? `<div>${escapeHtml(cust.contact)}</div>` : ""}
          ${cust && cust.email ? `<div>${escapeHtml(cust.email)}</div>` : ""}
          ${cust && cust.address ? `<div>${escapeHtml(cust.address)}</div>` : ""}
        </div>
      </div>
      <table>
        <thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit price</th><th class="num">Total</th></tr></thead>
        <tbody>
          ${(q.items || []).map(it => `
            <tr><td class="desc-cell">${it.partNumber ? `<strong>${escapeHtml(it.partNumber)}</strong><br>` : ""}${escapeHtml(it.description || "")}</td><td class="num">${it.qty}</td><td class="num">${fmt(it.unitPrice)}</td><td class="num">${fmt(it.qty * it.unitPrice)}</td></tr>
          `).join("")}
        </tbody>
      </table>
      <div class="p-totals">
        <div class="row"><span>Subtotal</span><span>${fmt(subtotal)}</span></div>
        ${q.discount ? `<div class="row"><span>Discount (${q.discount}%)</span><span>-${fmt(discountAmt)}</span></div>` : ""}
        ${q.tax ? `<div class="row"><span>Tax / VAT (${q.tax}%)</span><span>${fmt(taxAmt)}</span></div>` : ""}
        <div class="row grand"><span>Total</span><span>${fmt(total)}</span></div>
      </div>
      ${q.notes ? `<div class="p-notes">${escapeHtml(q.notes)}</div>` : ""}
    `;
    $("previewBackdrop").classList.add("open");
  }
  $("closePreviewBtn").addEventListener("click", () => $("previewBackdrop").classList.remove("open"));
  $("printPreviewBtn").addEventListener("click", () => window.print());

  boot();
})();
