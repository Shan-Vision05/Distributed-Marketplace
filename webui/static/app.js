const state = {
  role: 'buyer',
  authMode: 'login',
  sessionId: null,
  username: null,
  config: null,
};

const elements = {
  sessionStatus: document.getElementById('sessionStatus'),
  logoutButton: document.getElementById('logoutButton'),
  roleSelector: document.getElementById('roleSelector'),
  authModeSelector: document.getElementById('authModeSelector'),
  authForm: document.getElementById('authForm'),
  authSubmit: document.getElementById('authSubmit'),
  authUsername: document.getElementById('authUsername'),
  authPassword: document.getElementById('authPassword'),
  messageBanner: document.getElementById('messageBanner'),
  welcomePanel: document.getElementById('welcomePanel'),
  buyerDashboard: document.getElementById('buyerDashboard'),
  sellerDashboard: document.getElementById('sellerDashboard'),
  buyerTitle: document.getElementById('buyerTitle'),
  sellerTitle: document.getElementById('sellerTitle'),
  buyerRefresh: document.getElementById('buyerRefresh'),
  sellerRefresh: document.getElementById('sellerRefresh'),
  searchForm: document.getElementById('searchForm'),
  searchCategory: document.getElementById('searchCategory'),
  searchKeywords: document.getElementById('searchKeywords'),
  catalogCount: document.getElementById('catalogCount'),
  productGrid: document.getElementById('productGrid'),
  cartSummary: document.getElementById('cartSummary'),
  cartItems: document.getElementById('cartItems'),
  saveCartButton: document.getElementById('saveCartButton'),
  clearCartButton: document.getElementById('clearCartButton'),
  checkoutForm: document.getElementById('checkoutForm'),
  ordersCount: document.getElementById('ordersCount'),
  ordersList: document.getElementById('ordersList'),
  inventoryCount: document.getElementById('inventoryCount'),
  inventoryGrid: document.getElementById('inventoryGrid'),
  createProductForm: document.getElementById('createProductForm'),
  sellerRatingCard: document.getElementById('sellerRatingCard'),
};

const STORAGE_KEY = 'distributed-marketplace-webui-session';

async function init() {
  bindCoreEvents();
  bindTabRows();
  await loadConfig();
  restoreSession();
  syncAuthControls();
  syncDashboard();
  if (state.sessionId) {
    await refreshActiveWorkspace();
  }
}

function bindCoreEvents() {
  elements.roleSelector.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-role]');
    if (!button) return;
    state.role = button.dataset.role;
    syncAuthControls();
    syncDashboard();
  });

  elements.authModeSelector.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-mode]');
    if (!button) return;
    state.authMode = button.dataset.mode;
    syncAuthControls();
  });

  elements.authForm.addEventListener('submit', handleAuthSubmit);
  elements.logoutButton.addEventListener('click', handleLogout);
  elements.buyerRefresh.addEventListener('click', refreshBuyerWorkspace);
  elements.sellerRefresh.addEventListener('click', refreshSellerWorkspace);
  elements.searchForm.addEventListener('submit', handleSearchSubmit);
  elements.saveCartButton.addEventListener('click', handleSaveCart);
  elements.clearCartButton.addEventListener('click', handleClearCart);
  elements.checkoutForm.addEventListener('submit', handleCheckout);
  elements.createProductForm.addEventListener('submit', handleCreateProduct);
}

function bindTabRows() {
  document.querySelectorAll('.tab-row').forEach((tabRow) => {
    tabRow.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-target]');
      if (!button) return;
      const container = tabRow.parentElement;
      tabRow.querySelectorAll('button').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      container.querySelectorAll('.tab-panel').forEach((panel) => {
        const isTarget = panel.id === button.dataset.target;
        panel.hidden = !isTarget;
        panel.classList.toggle('active', isTarget);
      });
      if (state.role === 'buyer') {
        if (button.dataset.target === 'buyerCartPanel') await loadCart();
        if (button.dataset.target === 'buyerOrdersPanel') await loadOrders();
      }
      if (state.role === 'seller') {
        if (button.dataset.target === 'sellerInventoryPanel') await loadInventory();
        if (button.dataset.target === 'sellerRatingPanel') await loadSellerRating();
      }
    });
  });
}

async function loadConfig() {
  try {
    state.config = await api('/api/config');
    elements.searchCategory.value = state.config.defaults?.buyer_search_category ?? 0;
  } catch (error) {
    showMessage(error.message, true);
  }
}

function restoreSession() {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    state.role = saved.role ?? 'buyer';
    state.sessionId = saved.sessionId ?? null;
    state.username = saved.username ?? null;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

function persistSession() {
  if (!state.sessionId) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
    role: state.role,
    sessionId: state.sessionId,
    username: state.username,
  }));
}

function clearSession() {
  state.sessionId = null;
  state.username = null;
  persistSession();
}

function syncAuthControls() {
  elements.roleSelector.querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', button.dataset.role === state.role);
  });
  elements.authModeSelector.querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', button.dataset.mode === state.authMode);
  });
  elements.authSubmit.textContent = state.authMode === 'login' ? 'Login' : 'Create account';
}

function syncDashboard() {
  const signedIn = Boolean(state.sessionId);
  elements.logoutButton.hidden = !signedIn;
  elements.welcomePanel.hidden = signedIn;
  elements.buyerDashboard.hidden = !(signedIn && state.role === 'buyer');
  elements.sellerDashboard.hidden = !(signedIn && state.role === 'seller');
  elements.sessionStatus.textContent = signedIn
    ? `${state.role} · ${state.username ?? 'active session'}`
    : 'Signed out';
  if (state.username) {
    elements.buyerTitle.textContent = `Welcome back, ${state.username}`;
    elements.sellerTitle.textContent = `Welcome back, ${state.username}`;
  }
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const payload = {
    role: state.role,
    username: elements.authUsername.value.trim(),
    password: elements.authPassword.value,
  };
  if (!payload.username || !payload.password) {
    showMessage('Enter both username and password.', true);
    return;
  }

  const endpoint = state.authMode === 'login' ? '/api/auth/login' : '/api/auth/register';

  try {
    const result = await api(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (state.authMode === 'register') {
      showMessage(`Account created successfully for ${payload.username}. Please login next.`);
      state.authMode = 'login';
      syncAuthControls();
      elements.authPassword.value = '';
      return;
    }

    state.sessionId = result.session_id;
    state.username = result.username;
    persistSession();
    syncDashboard();
    showMessage(`Logged in as ${payload.username}.`);
    await refreshActiveWorkspace();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleLogout() {
  if (!state.sessionId) return;
  try {
    await api('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ role: state.role, session_id: state.sessionId }),
    });
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    clearSession();
    syncDashboard();
    resetWorkspaceViews();
    showMessage('Signed out.');
  }
}

async function refreshActiveWorkspace() {
  if (!state.sessionId) return;
  if (state.role === 'buyer') {
    await refreshBuyerWorkspace();
  } else {
    await refreshSellerWorkspace();
  }
}

async function refreshBuyerWorkspace() {
  await Promise.all([loadProducts(), loadCart(), loadOrders()]);
}

async function refreshSellerWorkspace() {
  await Promise.all([loadInventory(), loadSellerRating()]);
}

async function handleSearchSubmit(event) {
  event.preventDefault();
  await loadProducts();
}

async function loadProducts() {
  if (!state.sessionId) return;
  try {
    const category = Number(elements.searchCategory.value || 0);
    const keywords = elements.searchKeywords.value.trim();
    const result = await api(`/api/buyer/products?session_id=${encodeURIComponent(state.sessionId)}&category=${encodeURIComponent(category)}&keywords=${encodeURIComponent(keywords)}`);
    elements.catalogCount.textContent = `${result.count} result${result.count === 1 ? '' : 's'}`;
    renderProducts(result.items || []);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function loadCart() {
  if (!state.sessionId) return;
  try {
    const result = await api(`/api/buyer/cart?session_id=${encodeURIComponent(state.sessionId)}`);
    renderCart(result.items || [], result.summary || {});
  } catch (error) {
    if (isAuthError(error)) {
      await forceSessionReset(error.message);
      return;
    }
    showMessage(error.message, true);
  }
}

async function loadOrders() {
  if (!state.sessionId) return;
  try {
    const result = await api(`/api/buyer/orders?session_id=${encodeURIComponent(state.sessionId)}`);
    elements.ordersCount.textContent = `${result.count} order${result.count === 1 ? '' : 's'}`;
    renderOrders(result.purchase_history || []);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleAddToCart(itemId, quantity) {
  try {
    await api('/api/buyer/cart/add', {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId, item_id: itemId, quantity }),
    });
    showMessage('Item added to cart.');
    await loadCart();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleRemoveFromCart(itemId, quantity) {
  try {
    await api('/api/buyer/cart/remove', {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId, item_id: itemId, quantity }),
    });
    showMessage('Cart updated.');
    await loadCart();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleSaveCart() {
  if (!state.sessionId) return;
  try {
    await api('/api/buyer/cart/save', {
      method: 'POST',
      body: JSON.stringify({ role: state.role, session_id: state.sessionId }),
    });
    showMessage('Cart saved.');
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleClearCart() {
  if (!state.sessionId) return;
  try {
    await api('/api/buyer/cart/clear', {
      method: 'POST',
      body: JSON.stringify({ role: state.role, session_id: state.sessionId }),
    });
    showMessage('Cart cleared.');
    await loadCart();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function handleCheckout(event) {
  event.preventDefault();
  if (!state.sessionId) return;
  const payload = {
    session_id: state.sessionId,
    name: document.getElementById('checkoutName').value.trim(),
    card_number: document.getElementById('checkoutCardNumber').value.trim(),
    exp_month: document.getElementById('checkoutMonth').value.trim(),
    exp_year: document.getElementById('checkoutYear').value.trim(),
    cvv: document.getElementById('checkoutCvv').value.trim(),
  };

  try {
    const result = await api('/api/buyer/checkout', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showMessage(result.message || 'Purchase completed.');
    elements.checkoutForm.reset();
    await Promise.all([loadCart(), loadOrders(), loadProducts()]);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function submitFeedback(itemId, feedbackType) {
  try {
    await api('/api/buyer/feedback', {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        item_id: itemId,
        feedback_type: feedbackType,
      }),
    });
    showMessage(`Feedback recorded: ${feedbackType}.`);
    await Promise.all([loadOrders(), loadProducts()]);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function loadInventory() {
  if (!state.sessionId) return;
  try {
    const result = await api(`/api/seller/items?session_id=${encodeURIComponent(state.sessionId)}`);
    elements.inventoryCount.textContent = `${result.count} item${result.count === 1 ? '' : 's'}`;
    renderInventory(result.items || []);
  } catch (error) {
    if (isAuthError(error)) {
      await forceSessionReset(error.message);
      return;
    }
    showMessage(error.message, true);
  }
}

async function handleCreateProduct(event) {
  event.preventDefault();
  try {
    const result = await api('/api/seller/items', {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        name: document.getElementById('createName').value.trim(),
        category: Number(document.getElementById('createCategory').value),
        keywords: document.getElementById('createKeywords').value.trim(),
        condition: document.getElementById('createCondition').value,
        price: Number(document.getElementById('createPrice').value),
        quantity: Number(document.getElementById('createQuantity').value),
      }),
    });
    showMessage(`Product created with item ID ${result.item_id.join(',')}.`);
    elements.createProductForm.reset();
    document.getElementById('createCondition').value = 'new';
    await loadInventory();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function updateInventoryPrice(itemId, input) {
  try {
    await api('/api/seller/items/price', {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        item_id: itemId,
        price: Number(input.value),
      }),
    });
    showMessage('Price updated.');
    await loadInventory();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function updateInventoryQuantity(itemId, input) {
  try {
    await api('/api/seller/items/quantity', {
      method: 'POST',
      body: JSON.stringify({
        session_id: state.sessionId,
        item_id: itemId,
        quantity_delta: Number(input.value),
      }),
    });
    showMessage('Inventory updated.');
    input.value = '';
    await loadInventory();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function loadSellerRating() {
  if (!state.sessionId) return;
  try {
    const result = await api(`/api/seller/rating?session_id=${encodeURIComponent(state.sessionId)}`);
    renderSellerRating(result.feedback || { up: 0, down: 0 });
  } catch (error) {
    showMessage(error.message, true);
  }
}

function renderProducts(items) {
  elements.productGrid.innerHTML = '';
  if (!items.length) {
    elements.productGrid.appendChild(emptyState('No products found', 'Try a broader category or fewer keywords.'));
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'product-card';
    const stockBadge = item.is_in_stock
      ? '<span class="badge success">In stock</span>'
      : '<span class="badge warning">Out of stock</span>';
    card.innerHTML = `
      <div class="product-title-row">
        <div>
          <h4>${escapeHtml(item.name)}</h4>
          <span class="subtle">Item ${escapeHtml(item.item_key)}</span>
        </div>
        ${stockBadge}
      </div>
      <div class="item-meta">
        <div><span>Price</span><strong>$${formatMoney(item.price)}</strong></div>
        <div><span>Available</span><strong>${item.quantity}</strong></div>
        <div><span>Condition</span><strong>${escapeHtml(item.condition)}</strong></div>
        <div><span>Seller ID</span><strong>${item.seller_id}</strong></div>
      </div>
      <div class="meta-row">
        <div><span>Category</span><strong>${item.category}</strong></div>
        <div><span>Feedback score</span><strong>${item.feedback_score}</strong></div>
      </div>
      <div class="keyword-row">${renderKeywords(item.keywords)}</div>
      <div class="inline-action">
        <input type="number" min="1" max="${Math.max(item.quantity, 1)}" value="1" aria-label="Quantity to add">
        <button class="button primary small" ${item.is_in_stock ? '' : 'disabled'}>Add to cart</button>
      </div>
    `;
    const quantityInput = card.querySelector('input');
    card.querySelector('button').addEventListener('click', () => {
      handleAddToCart(item.item_key, Number(quantityInput.value || 1));
    });
    elements.productGrid.appendChild(card);
  });
}

function renderCart(items, summary) {
  elements.cartItems.innerHTML = '';
  elements.cartSummary.innerHTML = `
    <div class="summary-grid">
      <div><span>Line items</span><strong>${summary.line_items ?? 0}</strong></div>
      <div><span>Total quantity</span><strong>${summary.total_quantity ?? 0}</strong></div>
      <div><span>Total price</span><strong>$${formatMoney(summary.total_price ?? 0)}</strong></div>
    </div>
  `;

  if (!items.length) {
    elements.cartItems.appendChild(emptyState('Your cart is empty', 'Add a product from the catalog to begin checkout.'));
    return;
  }

  items.forEach((entry) => {
    const item = entry.item;
    const row = document.createElement('article');
    row.className = 'list-item';
    row.innerHTML = `
      <div class="list-head">
        <div>
          <h4>${escapeHtml(item.name)}</h4>
          <span class="subtle">Item ${escapeHtml(entry.item_id)}</span>
        </div>
        <span class="pill">$${formatMoney(entry.subtotal)}</span>
      </div>
      <div class="item-meta">
        <div><span>Unit price</span><strong>$${formatMoney(item.price)}</strong></div>
        <div><span>Quantity in cart</span><strong>${entry.quantity}</strong></div>
        <div><span>Available stock</span><strong>${item.quantity ?? 0}</strong></div>
        <div><span>Condition</span><strong>${escapeHtml(item.condition ?? 'unknown')}</strong></div>
      </div>
      <div class="inline-action">
        <input type="number" min="1" max="${entry.quantity}" value="1" aria-label="Quantity to remove">
        <button class="button danger small">Remove</button>
      </div>
    `;
    const removeInput = row.querySelector('input');
    row.querySelector('button').addEventListener('click', () => {
      handleRemoveFromCart(entry.item_id, Number(removeInput.value || 1));
    });
    elements.cartItems.appendChild(row);
  });
}

function renderOrders(orders) {
  elements.ordersList.innerHTML = '';
  if (!orders.length) {
    elements.ordersList.appendChild(emptyState('No purchases yet', 'Completed purchases will appear here.'));
    return;
  }

  orders.forEach((order) => {
    const row = document.createElement('article');
    row.className = 'list-item';
    row.innerHTML = `
      <div class="list-head">
        <div>
          <h4>${escapeHtml(order.item_name)}</h4>
          <span class="subtle">Purchased ${escapeHtml(order.purchased_at)} · Item ${escapeHtml(order.item_key)}</span>
        </div>
        <span class="pill">$${formatMoney(order.total)}</span>
      </div>
      <div class="item-meta">
        <div><span>Quantity</span><strong>${order.quantity}</strong></div>
        <div><span>Unit price</span><strong>$${formatMoney(order.price)}</strong></div>
      </div>
      <div class="order-actions">
        <button class="button secondary small" data-feedback="up">Thumbs up</button>
        <button class="button ghost small" data-feedback="down">Thumbs down</button>
      </div>
    `;
    row.querySelectorAll('button[data-feedback]').forEach((button) => {
      button.addEventListener('click', () => submitFeedback(order.item_key, button.dataset.feedback));
    });
    elements.ordersList.appendChild(row);
  });
}

function renderInventory(items) {
  elements.inventoryGrid.innerHTML = '';
  if (!items.length) {
    elements.inventoryGrid.appendChild(emptyState('No inventory yet', 'Create a product to start selling.'));
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'inventory-card';
    card.innerHTML = `
      <div class="inventory-title-row">
        <div>
          <h4>${escapeHtml(item.name)}</h4>
          <span class="subtle">Item ${escapeHtml(item.item_key)}</span>
        </div>
        <span class="badge muted">Category ${item.category}</span>
      </div>
      <div class="item-meta">
        <div><span>Current price</span><strong>$${formatMoney(item.price)}</strong></div>
        <div><span>Available units</span><strong>${item.quantity}</strong></div>
        <div><span>Condition</span><strong>${escapeHtml(item.condition)}</strong></div>
        <div><span>Feedback score</span><strong>${item.feedback_score}</strong></div>
      </div>
      <div class="keyword-row">${renderKeywords(item.keywords)}</div>
      <div class="inventory-controls">
        <input type="number" min="0.01" step="0.01" value="${item.price}" aria-label="New price">
        <button class="button secondary small">Update price</button>
      </div>
      <div class="inventory-controls">
        <input type="number" step="1" placeholder="Use positive or negative numbers" aria-label="Inventory change">
        <button class="button ghost small">Adjust stock</button>
      </div>
    `;

    const [priceInput, deltaInput] = card.querySelectorAll('input');
    const [priceButton, deltaButton] = card.querySelectorAll('button');
    priceButton.addEventListener('click', () => updateInventoryPrice(item.item_key, priceInput));
    deltaButton.addEventListener('click', () => updateInventoryQuantity(item.item_key, deltaInput));
    elements.inventoryGrid.appendChild(card);
  });
}

function renderSellerRating(feedback) {
  const score = Number(feedback.up || 0) - Number(feedback.down || 0);
  elements.sellerRatingCard.innerHTML = `
    <div class="rating-card">
      <span>Upvotes</span>
      <strong>${feedback.up || 0}</strong>
    </div>
    <div class="rating-card">
      <span>Downvotes</span>
      <strong>${feedback.down || 0}</strong>
    </div>
    <div class="rating-card">
      <span>Net score</span>
      <strong>${score}</strong>
    </div>
  `;
}

function emptyState(title, description) {
  const node = document.createElement('div');
  node.className = 'empty-state';
  node.innerHTML = `<h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>`;
  return node;
}

function renderKeywords(keywords = []) {
  if (!keywords.length) {
    return '<span class="keyword-chip">No keywords</span>';
  }
  return keywords
    .map((keyword) => `<span class="keyword-chip">${escapeHtml(keyword)}</span>`)
    .join('');
}

function resetWorkspaceViews() {
  elements.productGrid.innerHTML = '';
  elements.cartItems.innerHTML = '';
  elements.ordersList.innerHTML = '';
  elements.inventoryGrid.innerHTML = '';
  elements.sellerRatingCard.innerHTML = '';
  elements.catalogCount.textContent = '0 results';
  elements.ordersCount.textContent = '0 orders';
  elements.inventoryCount.textContent = '0 items';
  elements.cartSummary.innerHTML = '';
}

async function forceSessionReset(message) {
  clearSession();
  syncDashboard();
  resetWorkspaceViews();
  showMessage(message || 'Your session is no longer valid. Please sign in again.', true);
}

function showMessage(message, isError = false) {
  if (!message) {
    elements.messageBanner.hidden = true;
    elements.messageBanner.textContent = '';
    elements.messageBanner.classList.remove('error');
    return;
  }
  elements.messageBanner.hidden = false;
  elements.messageBanner.textContent = message;
  elements.messageBanner.classList.toggle('error', isError);
}

function isAuthError(error) {
  return typeof error?.status === 'number' && (error.status === 401 || error.status === 403);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const error = new Error(payload?.detail || payload?.message || 'Request failed');
    error.status = response.status;
    throw error;
  }

  return payload;
}

function formatMoney(value) {
  return Number(value || 0).toFixed(2);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

init();
