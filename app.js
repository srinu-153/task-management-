(() => {
  const today = new Date();
  const localDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };
  let csrfToken = null;
  async function apiRequest(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set('Content-Type', 'application/json');
    if (csrfToken && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(options.method)) {
      headers.set('X-CSRF-Token', csrfToken);
    }
    const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
    const body = response.status === 204 ? null : await response.json();
    if (!response.ok) throw new Error(body?.error || 'Something went wrong. Please try again.');
    return body;
  }

  const taskApi = {
    list() { return apiRequest('/api/tasks'); },
    async save(task) {
      const isUpdate = Boolean(task.id);
      const body = JSON.stringify({
        title: task.title, description: task.description, due: task.due,
        priority: task.priority, space: task.space, completed: task.completed
      });
      return apiRequest(isUpdate ? `/api/tasks/${encodeURIComponent(task.id)}` : '/api/tasks', {
        method: isUpdate ? 'PATCH' : 'POST', body
      });
    },
    remove(id) { return apiRequest(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
  };

  const $ = (selector) => document.querySelector(selector);
  const elements = {
    signIn: $('#sign-in'), workspace: $('#workspace'), signInForm: $('#sign-in-form'),
    taskDialog: $('#task-dialog'), taskForm: $('#task-form'), taskList: $('#task-list'),
    emptyState: $('#empty-state'), search: $('#search'), statusFilter: $('#status-filter'), toast: $('#toast')
  };
  let tasks = [];
  let activeView = 'all';
  let activeUser = null;
  let authMode = 'register';
  let toastTimer;

  const getInitials = (name) => name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || '').join('');
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const formatDate = (dateString) => {
    if (!dateString) return 'No date';
    const date = new Date(`${dateString}T12:00:00`);
    if (dateString === localDate(new Date())) return 'Today';
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
  };
  const formatLongDate = (date) => new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(date);

  function notify(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => elements.toast.classList.remove('is-visible'), 2400);
  }

  async function setUser(user, token = null) {
    activeUser = user;
    csrfToken = token;
    elements.signIn.hidden = Boolean(user);
    elements.workspace.hidden = !user;
    if (user) {
      const initials = getInitials(user.name) || 'FN';
      $('#profile-name').textContent = user.name;
      $('#avatar-initials').textContent = initials;
      $('#topbar-sign-out').textContent = initials;
      try {
        tasks = await taskApi.list();
        render();
      } catch (error) {
        notify(error.message);
        setUser(null);
      }
    }
  }

  function viewTasks() {
    const query = elements.search.value.trim().toLowerCase();
    const status = elements.statusFilter.value;
    return tasks.filter((task) => {
      if (activeView === 'today' && (task.completed || task.due !== localDate(new Date()))) return false;
      if (activeView === 'upcoming' && (task.completed || !task.due || task.due <= localDate(new Date()))) return false;
      if (activeView === 'completed' && !task.completed) return false;
      if (activeView !== 'completed' && status === 'open' && task.completed) return false;
      if (status === 'completed' && !task.completed) return false;
      return `${task.title} ${task.description} ${task.space}`.toLowerCase().includes(query);
    }).sort((a, b) => Number(a.completed) - Number(b.completed) || (a.due || '9999').localeCompare(b.due || '9999') || b.createdAt - a.createdAt);
  }

  function renderTask(task) {
    const overdue = !task.completed && task.due && task.due < localDate(new Date());
    const priorityLabel = task.priority === 'high' ? 'High' : task.priority === 'low' ? 'Low' : 'Normal';
    return `<article class="task-row${task.completed ? ' is-completed' : ''}" data-id="${escapeHtml(task.id)}">
      <input class="task-check" type="checkbox" aria-label="Mark ${escapeHtml(task.title)} ${task.completed ? 'open' : 'complete'}" ${task.completed ? 'checked' : ''} />
      <div class="task-main"><span class="task-title">${escapeHtml(task.title)}</span>${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ''}</div>
      <span class="task-space"><span class="space-dot ${task.space === 'Work' ? 'dot-coral' : 'dot-sage'}"></span>${escapeHtml(task.space)}</span>
      <span class="priority ${escapeHtml(task.priority)}">${priorityLabel}</span>
      <span class="task-due${overdue ? ' overdue' : ''}">${overdue ? 'Overdue' : formatDate(task.due)}</span>
      <div class="task-actions"><button class="task-action edit" type="button" aria-label="Edit ${escapeHtml(task.title)}">Edit</button><button class="task-action delete" type="button" aria-label="Delete ${escapeHtml(task.title)}">Delete</button></div>
    </article>`;
  }

  function updateSummary() {
    const open = tasks.filter((task) => !task.completed);
    const done = tasks.length - open.length;
    const dueToday = open.filter((task) => task.due === localDate(new Date())).length;
    $('#summary-open').textContent = open.length;
    $('#summary-done').textContent = done;
    $('#summary-today').textContent = dueToday;
    $('#nav-open-count').textContent = open.length;
    $('#task-footer-count').textContent = `${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'}`;
  }

  function render() {
    if (!activeUser) return;
    const titles = { all: ['My tasks', 'A clear view of what you\'re moving forward.'], today: ['Today', 'Just what needs your attention today.'], upcoming: ['Upcoming', 'A little look at what is coming next.'], completed: ['Completed', 'A record of the things you have moved forward.'] };
    const [title, subtitle] = titles[activeView];
    $('#breadcrumb-view').textContent = title;
    $('#view-title').innerHTML = `${title}<span class="title-period">.</span>`;
    $('#view-subtitle').textContent = subtitle;
    document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('is-active', item.dataset.view === activeView));
    const visible = viewTasks();
    elements.taskList.innerHTML = visible.map(renderTask).join('');
    elements.emptyState.hidden = visible.length > 0;
    $('#list-count').textContent = `${visible.length} ${visible.length === 1 ? 'task' : 'tasks'}`;
    $('#empty-title').textContent = activeView === 'completed' ? 'Nothing checked off yet.' : 'A fresh page.';
    $('#empty-copy').textContent = activeView === 'completed' ? 'Completed tasks will gather here.' : 'Add a task when something needs your attention.';
    $('#empty-add').hidden = activeView === 'completed';
    updateSummary();
  }

  function openTaskDialog(task = null) {
    elements.taskForm.reset();
    $('#task-id').value = task?.id || '';
    $('#task-title').value = task?.title || '';
    $('#task-description').value = task?.description || '';
    $('#task-due').value = task?.due || '';
    $('#task-priority').value = task?.priority || 'normal';
    $('#task-space').value = task?.space || 'Personal';
    $('#dialog-title').textContent = task ? 'Edit task' : 'New task';
    $('#save-task').textContent = task ? 'Save changes' : 'Save task';
    elements.taskDialog.showModal();
    $('#task-title').focus();
  }

  async function refresh() {
    tasks = await taskApi.list();
    render();
  }

  elements.signInForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(elements.signInForm);
    const credentials = { email: String(data.get('email')).trim().toLowerCase(), password: String(data.get('password')) };
    if (authMode === 'register') credentials.name = String(data.get('name')).trim();
    try {
      const result = await apiRequest(`/api/auth/${authMode}`, { method: 'POST', body: JSON.stringify(credentials) });
      await setUser(result.user, result.csrfToken);
    } catch (error) {
      notify(error.message);
    }
  });
  $('#auth-mode-toggle').addEventListener('click', () => {
    authMode = authMode === 'register' ? 'login' : 'register';
    const registering = authMode === 'register';
    $('#register-fields').hidden = !registering;
    $('#name').required = registering;
    $('#password').autocomplete = registering ? 'new-password' : 'current-password';
    $('#auth-submit').innerHTML = `${registering ? 'Create account' : 'Sign in'} <span aria-hidden="true">&#8594;</span>`;
    $('#auth-mode-toggle').textContent = registering ? 'Already have an account? Sign in' : 'New to Fieldnote? Create an account';
    $('#auth-note').textContent = registering ? 'Use at least 8 characters. Your tasks are private to your account.' : 'Sign in to return to your private task list.';
  });
  async function signOut() {
    try {
      await apiRequest('/api/auth/logout', { method: 'POST' });
      await setUser(null);
    } catch (error) {
      notify(error.message);
    }
  }
  $('#sign-out').addEventListener('click', signOut);
  $('#topbar-sign-out').addEventListener('click', signOut);
  $('#new-task').addEventListener('click', () => openTaskDialog());
  $('#empty-add').addEventListener('click', () => openTaskDialog());
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => elements.taskDialog.close()));
  elements.taskDialog.addEventListener('click', (event) => {
    if (event.target === elements.taskDialog) elements.taskDialog.close();
  });
  elements.taskForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = $('#task-id').value;
    const existing = tasks.find((task) => task.id === id);
    const task = {
      id: id || null,
      title: $('#task-title').value.trim(), description: $('#task-description').value.trim(),
      due: $('#task-due').value, priority: $('#task-priority').value, space: $('#task-space').value,
      completed: existing?.completed || false, createdAt: existing?.createdAt || Date.now()
    };
    if (!task.title) return;
    try {
      await taskApi.save(task);
      elements.taskDialog.close();
      await refresh();
      notify(existing ? 'Your changes are saved.' : 'Task added to your list.');
    } catch (error) {
      notify(error.message);
    }
  });
  elements.taskList.addEventListener('change', async (event) => {
    if (!event.target.matches('.task-check')) return;
    const row = event.target.closest('.task-row');
    const task = tasks.find((item) => item.id === row.dataset.id);
    if (!task) return;
    try {
      await taskApi.save({ ...task, completed: event.target.checked });
      await refresh();
      notify(event.target.checked ? 'One more thing moved forward.' : 'Task marked as open.');
    } catch (error) {
      notify(error.message);
      await refresh();
    }
  });
  elements.taskList.addEventListener('click', async (event) => {
    const row = event.target.closest('.task-row');
    if (!row) return;
    const task = tasks.find((item) => item.id === row.dataset.id);
    if (event.target.closest('.edit')) openTaskDialog(task);
    if (event.target.closest('.delete') && task && confirm(`Delete "${task.title}"?`)) {
      try {
        await taskApi.remove(task.id);
        await refresh();
        notify('Task deleted.');
      } catch (error) {
        notify(error.message);
      }
    }
  });
  document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => {
    activeView = button.dataset.view;
    elements.statusFilter.value = 'all';
    render();
  }));
  elements.search.addEventListener('input', render);
  elements.statusFilter.addEventListener('change', render);
  $('#today-date').textContent = formatLongDate(today);
  $('#welcome-date').textContent = formatLongDate(today).toUpperCase();

  apiRequest('/api/auth/session').then(async (result) => {
    if (result.user) await setUser(result.user, result.csrfToken);
    else elements.signIn.hidden = false;
  }).catch(() => {
    elements.signIn.hidden = false;
    notify('Cannot reach the task server. Start it and reload this page.');
  });
})();