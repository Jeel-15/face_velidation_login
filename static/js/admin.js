/**
 * Admin Panel JavaScript
 * Matches admin.html element IDs exactly.
 */

let allUsers = [];
let allLogs  = [];

// -- Init
document.addEventListener('DOMContentLoaded', async () => {
    // Fetch username from profile API; fallback to localStorage
    try {
        const r = await fetch('/api/user/profile');
        const d = await r.json();
        if (d.success && d.user) {
            const adminUsernameEl = document.getElementById('adminUsername');
            if (adminUsernameEl) adminUsernameEl.textContent = d.user.user_id;
            localStorage.setItem('user_id', d.user.user_id);
        }
    } catch (e) {
        const adminUsernameEl = document.getElementById('adminUsername');
        if (adminUsernameEl) adminUsernameEl.textContent = localStorage.getItem('user_id') || 'Admin';
    }
    await loadStats();
    await loadUsers();
});

// -- Stats + Recent Activity
async function loadStats() {
    try {
        const res  = await fetch('/api/admin/stats');
        const data = await res.json();
        if (!data.success) return;
        const s = data.stats;

        const el = id => document.getElementById(id);
        if (el('statUsers'))    el('statUsers').textContent    = s.total_users             ?? '-';
        if (el('statEnrolled')) el('statEnrolled').textContent = s.enrolled_users           ?? '-';
        if (el('statActive'))   el('statActive').textContent   = s.active_users             ?? '-';
        if (el('statVerifs'))   el('statVerifs').textContent   = s.total_verifications ?? s.successful_logins_today ?? '-';

        // Load recent activity from logs endpoint
        const tbody = document.getElementById('recentActivity');
        if (tbody) {
            try {
                const logsRes  = await fetch('/api/admin/logs?limit=8');
                const logsData = await logsRes.json();
                const recent   = (logsData.success && logsData.logs) ? logsData.logs : [];
                if (recent.length > 0) {
                    tbody.innerHTML = recent.map(l => `
                        <tr>
                            <td style="color:#94a3b8;font-size:12px;white-space:nowrap;">${fmtDate(l.timestamp)}</td>
                            <td><strong>${escapeHtml(l.user_id || 'Unknown')}</strong></td>
                            <td style="color:#64748b;font-size:12px;">${escapeHtml(l.attempt_type || 'verification')}</td>
                            <td>${l.success
                                ? '<span class="badge badge-success">Success</span>'
                                : '<span class="badge badge-danger">Failed</span>'}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No recent activity.</td></tr>';
                }
            } catch (_) {
                tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No recent activity.</td></tr>';
            }
        }
    } catch (e) {
        console.error('Stats error:', e);
    }
}

// -- Users
async function loadUsers() {
    try {
        const res  = await fetch('/api/admin/users?include_inactive=true');
        const data = await res.json();
        if (data.success) { allUsers = data.users; renderUsers(allUsers); }
    } catch (e) {
        const tbody = document.getElementById('usersTableBody');
        if (tbody) tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Failed to load users.</td></tr>';
    }
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No users found.</td></tr>';
        return;
    }
    tbody.innerHTML = users.map(u => {
        const enrolledBadge = u.is_enrolled
            ? '<span class="badge badge-success">Enrolled</span>'
            : '<span class="badge badge-warning">Pending</span>';
        const statusBadge = u.is_active
            ? '<span class="badge badge-info">Active</span>'
            : '<span class="badge badge-danger">Inactive</span>';
        const faceModeBadge = Number(u.face_verification_enabled) === 0
            ? '<span class="badge badge-warning">Password Only</span>'
            : '<span class="badge badge-success">Biometric</span>';
        const adminBadge = u.is_admin
            ? '<span class="badge badge-warning">Admin</span>'
            : '<span style="color:#94a3b8;font-size:12px;">User</span>';
        return `
            <tr>
                <td><strong>${escapeHtml(u.user_id)}</strong></td>
                <td style="color:#64748b;font-size:12px;">${u.email || '-'}</td>
                <td>${enrolledBadge}</td>
                <td>${statusBadge}</td>
                <td>${faceModeBadge}</td>
                <td>${adminBadge}</td>
                <td>
                    <div class="row-actions">
                        <button class="btn btn-secondary" onclick="viewUser('${escapeHtml(u.user_id)}')">View</button>
                        <button class="btn btn-secondary" onclick="openEditUser('${escapeHtml(u.user_id)}')">Edit</button>
                        <button class="btn btn-secondary"
                            onclick="toggleFaceVerification('${escapeHtml(u.user_id)}', ${Number(u.face_verification_enabled) !== 0})">
                            ${Number(u.face_verification_enabled) === 0 ? 'Require Face' : 'Password Only'}
                        </button>
                        <button class="btn btn-secondary"
                            onclick="toggleUserStatus('${escapeHtml(u.user_id)}', ${!u.is_active})">
                            ${u.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button class="btn btn-secondary"
                            onclick="toggleAdminStatus('${escapeHtml(u.user_id)}', ${!u.is_admin})">
                            ${u.is_admin ? 'Revoke Admin' : 'Make Admin'}
                        </button>
                        <button class="btn btn-danger" onclick="deleteUser('${escapeHtml(u.user_id)}')">Delete</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// -- View user modal
async function viewUser(userId) {
    openModal('userModal');
    document.getElementById('userModalTitle').textContent = 'User: ' + userId;
    document.getElementById('userModalBody').innerHTML =
        '<div style="color:#475569;font-size:13px;padding:8px 0;">Loading...</div>';

    const delBtn = document.getElementById('userModalDeleteBtn');
    if (delBtn) delBtn.onclick = null;

    const resetBtn = document.getElementById('userModalResetEnrollBtn');
    if (resetBtn) { resetBtn.onclick = null; resetBtn.style.display = 'none'; }

    try {
        const res  = await fetch(`/api/admin/user/${encodeURIComponent(userId)}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        const u    = data.user;
        const logs = data.recent_logs || [];

        const logsHtml = logs.length === 0
            ? '<div style="color:#475569;font-size:12px;padding:8px 0;">No recent activity.</div>'
            : `<table style="width:100%;font-size:12px;border-collapse:collapse;margin-top:6px;">
                <thead><tr>
                  <th style="text-align:left;padding:6px 8px;color:#64748b;border-bottom:1px solid #e2e8f0;">Time</th>
                  <th style="text-align:left;padding:6px 8px;color:#64748b;border-bottom:1px solid #e2e8f0;">Type</th>
                  <th style="text-align:left;padding:6px 8px;color:#64748b;border-bottom:1px solid #e2e8f0;">Result</th>
                </tr></thead>
                <tbody>${logs.slice(0, 8).map(l => `
                <tr>
                  <td style="padding:6px 8px;color:#94a3b8;">${fmtDate(l.timestamp)}</td>
                  <td style="padding:6px 8px;">${escapeHtml(l.attempt_type || 'verification')}</td>
                  <td style="padding:6px 8px;">${l.success
                      ? '<span class="badge badge-success">OK</span>'
                      : '<span class="badge badge-danger">Fail</span>'}</td>
                </tr>`).join('')}
              </tbody></table>`;

        document.getElementById('userModalBody').innerHTML = `
            <div class="detail-row"><span class="d-key">User ID</span><span class="d-val">${escapeHtml(u.user_id)}</span></div>
            <div class="detail-row"><span class="d-key">Email</span><span class="d-val">${u.email || '-'}</span></div>
            <div class="detail-row"><span class="d-key">Status</span><span class="d-val">${u.is_active
                ? '<span class="badge badge-info">Active</span>'
                : '<span class="badge badge-danger">Inactive</span>'}</span></div>
            <div class="detail-row"><span class="d-key">Enrollment</span><span class="d-val">${u.is_enrolled
                ? '<span class="badge badge-success">Enrolled</span>'
                : '<span class="badge badge-warning">Pending</span>'}</span></div>
            <div class="detail-row"><span class="d-key">Face Login</span><span class="d-val">${Number(u.face_verification_enabled) === 0
                ? '<span class="badge badge-warning">Password Only</span>'
                : '<span class="badge badge-success">Biometric Required</span>'}</span></div>
            <div class="detail-row"><span class="d-key">Role</span><span class="d-val">${u.is_admin
                ? '<span class="badge badge-warning">Admin</span>' : 'User'}</span></div>
            <div class="detail-row"><span class="d-key">Face Samples</span><span class="d-val">${data.num_embeddings ?? 0}</span></div>
            <div class="detail-row"><span class="d-key">Created</span><span class="d-val" style="font-size:12px;">${fmtDate(u.created_at)}</span></div>
            <div class="detail-row"><span class="d-key">Last Login</span><span class="d-val" style="font-size:12px;">${u.last_login_at ? fmtDate(u.last_login_at) : 'Never'}</span></div>
            <div style="margin-top:14px;font-weight:600;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;">Recent Activity</div>
            ${logsHtml}
        `;

        if (delBtn) {
            delBtn.onclick = () => { closeModal('userModal'); deleteUser(userId); };
        }

        if (resetBtn && u.is_enrolled) {
            resetBtn.style.display = '';
            resetBtn.onclick = () => {
                closeModal('userModal');
                showConfirm(
                    'Reset Enrollment',
                    `This will delete all face data for <strong>${escapeHtml(userId)}</strong> so they can re-enroll.`,
                    async () => {
                        try {
                            const res  = await fetch(`/api/admin/user/${encodeURIComponent(userId)}/reset-enrollment`, { method: 'POST' });
                            const data = await res.json();
                            if (data.success) {
                                showToast(data.message || 'Enrollment reset.', 'success');
                                await loadUsers(); await loadStats();
                            } else {
                                showToast(data.error || 'Reset failed.', 'error');
                            }
                        } catch (e) { showToast('Request failed.', 'error'); }
                    }
                );
            };
        }
    } catch (e) {
        document.getElementById('userModalBody').innerHTML =
            '<div style="color:#f87171;font-size:13px;">Failed to load user details.</div>';
    }
}

// -- Create user
async function createUserFromPanel(event) {
    event.preventDefault();
    const userId   = document.getElementById('newUserId').value.trim();
    const password = document.getElementById('newUserPassword').value;
    const email    = document.getElementById('newUserEmail').value.trim();
    const msgEl    = document.getElementById('createUserMsg');

    const showMsg = (text, ok) => {
        msgEl.textContent = text;
        msgEl.style.cssText = ok
            ? 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;margin-bottom:14px;'
            : 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;margin-bottom:14px;';
    };

    if (!userId || !password) { showMsg('User ID and password are required.', false); return; }
    if (password.length < 6)  { showMsg('Password must be at least 6 characters.', false); return; }

    try {
        const res  = await fetch('/api/admin/create-user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, password, email })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showMsg(data.error || 'Failed to create user.', false);
            return;
        }
        showMsg(`User "${userId}" created! They can now enroll at /enroll.`, true);
        document.getElementById('createUserForm').reset();
        showToast(`User "${userId}" created.`, 'success');
        await loadStats();
    } catch (e) {
        showMsg('Request failed. Please try again.', false);
    }
}

// -- Toggle status
async function toggleUserStatus(userId, isActive) {
    const action = isActive ? 'Enable' : 'Disable';
    showConfirm(
        `${action} User`,
        `Are you sure you want to <strong>${action.toLowerCase()}</strong> user <strong>${escapeHtml(userId)}</strong>?`,
        async () => {
            try {
                const res  = await fetch(`/api/admin/user/${encodeURIComponent(userId)}/toggle-status`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: isActive })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message || 'Status updated.', 'success');
                    await loadUsers(); await loadStats();
                } else {
                    showToast(data.error || 'Failed to update.', 'error');
                }
            } catch (e) { showToast('Request failed.', 'error'); }
        }
    );
}

// -- Toggle admin
async function toggleAdminStatus(userId, isAdmin) {
    const action = isAdmin ? 'grant admin to' : 'revoke admin from';
    showConfirm(
        isAdmin ? 'Grant Admin' : 'Revoke Admin',
        `Are you sure you want to <strong>${action}</strong> <strong>${escapeHtml(userId)}</strong>?`,
        async () => {
            try {
                const res  = await fetch(`/api/admin/user/${encodeURIComponent(userId)}/toggle-admin`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_admin: isAdmin })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message || 'Admin status updated.', 'success');
                    await loadUsers(); await loadStats();
                } else {
                    showToast(data.error || 'Failed.', 'error');
                }
            } catch (e) { showToast('Request failed.', 'error'); }
        }
    );
}

async function toggleFaceVerification(userId, currentlyEnabled) {
    const newValue = !currentlyEnabled;
    const title = newValue ? 'Require Face Verification' : 'Allow Password-Only Login';
    const message = newValue
        ? `Enable biometric login requirement for <strong>${escapeHtml(userId)}</strong>?`
        : `Disable biometric login for <strong>${escapeHtml(userId)}</strong>?<br><span style="color:#64748b;font-size:12px;">This user will be able to login with only ID and password.</span>`;

    showConfirm(title, message, async () => {
        try {
            const res = await fetch(`/api/admin/user/${encodeURIComponent(userId)}/toggle-face-verification`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newValue })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message || 'Face verification mode updated.', 'success');
                await loadUsers();
            } else {
                showToast(data.error || 'Failed to update face verification mode.', 'error');
            }
        } catch (e) {
            showToast('Request failed.', 'error');
        }
    });
}

function openEditUser(userId) {
    const user = allUsers.find(u => u.user_id === userId);
    if (!user) {
        showToast('User data not loaded. Refresh and try again.', 'error');
        return;
    }

    const msgEl = document.getElementById('editUserMsg');
    const titleEl = document.getElementById('editUserModalTitle');
    document.getElementById('editOriginalUserId').value = user.user_id;
    document.getElementById('editUserId').value = user.user_id;
    document.getElementById('editUserPassword').value = '';
    document.getElementById('editUserEmail').value = user.email || '';
    msgEl.style.display = 'none';
    msgEl.textContent = '';
    titleEl.textContent = `Edit User: ${user.user_id}`;
    openModal('editUserModal');
}

async function submitEditUser(event) {
    event.preventDefault();

    const originalUserId = document.getElementById('editOriginalUserId').value;
    const newUserId = document.getElementById('editUserId').value.trim();
    const newPassword = document.getElementById('editUserPassword').value;
    const email = document.getElementById('editUserEmail').value.trim();
    const msgEl = document.getElementById('editUserMsg');
    const saveBtn = document.getElementById('editUserSaveBtn');

    if (!newUserId) {
        msgEl.textContent = 'User ID is required.';
        msgEl.style.cssText = 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;margin-bottom:14px;';
        return;
    }

    if (newPassword && newPassword.length < 6) {
        msgEl.textContent = 'Password must be at least 6 characters.';
        msgEl.style.cssText = 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;margin-bottom:14px;';
        return;
    }

    saveBtn.disabled = true;
    try {
        const res = await fetch(`/api/admin/user/${encodeURIComponent(originalUserId)}/edit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                new_user_id: newUserId,
                new_password: newPassword,
                email: email,
            })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            msgEl.textContent = data.error || 'Failed to update user.';
            msgEl.style.cssText = 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;margin-bottom:14px;';
            return;
        }

        msgEl.textContent = data.message || 'User updated successfully.';
        msgEl.style.cssText = 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;margin-bottom:14px;';
        showToast(data.message || 'User updated.', 'success');
        await loadUsers();
        await loadStats();
        setTimeout(() => closeModal('editUserModal'), 600);
    } catch (e) {
        msgEl.textContent = 'Request failed. Please try again.';
        msgEl.style.cssText = 'display:block;padding:10px 14px;border-radius:6px;font-size:13px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;margin-bottom:14px;';
    } finally {
        saveBtn.disabled = false;
    }
}

// -- Delete user
async function deleteUser(userId) {
    showConfirm(
        'Delete User',
        `This will <strong>permanently delete</strong> user <strong>${escapeHtml(userId)}</strong> and all their data.`,
        async () => {
            try {
                const res  = await fetch(`/api/admin/user/${encodeURIComponent(userId)}/delete`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    showToast(`User "${userId}" deleted.`, 'success');
                    await loadUsers(); await loadStats();
                } else {
                    showToast(data.error || 'Delete failed.', 'error');
                }
            } catch (e) { showToast('Request failed.', 'error'); }
        }
    );
}

// -- Logs
async function loadLogs() {
    const tbody = document.getElementById('logsTableBody');
    if (tbody) tbody.innerHTML = '<tr class="empty-row"><td colspan="5">Loading...</td></tr>';
    try {
        const res  = await fetch('/api/admin/logs?limit=100');
        const data = await res.json();
        if (data.success) { allLogs = data.logs; renderLogs(allLogs); }
    } catch (e) {
        if (tbody) tbody.innerHTML = '<tr class="empty-row"><td colspan="5">Failed to load logs.</td></tr>';
    }
}

function renderLogs(logs) {
    const tbody = document.getElementById('logsTableBody');
    if (!tbody) return;
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No logs found.</td></tr>';
        return;
    }
    tbody.innerHTML = logs.map(l => `
        <tr>
            <td style="color:#94a3b8;font-size:12px;white-space:nowrap;">${fmtDate(l.timestamp)}</td>
            <td><strong>${escapeHtml(l.user_id || 'Unknown')}</strong></td>
            <td style="color:#64748b;font-size:12px;">${escapeHtml(l.attempt_type || 'verification')}</td>
            <td>${l.success
                ? '<span class="badge badge-success">Success</span>'
                : '<span class="badge badge-danger">Failed</span>'}</td>
            <td style="color:#64748b;font-size:12px;">${l.match_distance != null ? Number(l.match_distance).toFixed(3) : '-'}</td>
        </tr>
    `).join('');
}

// -- Settings stubs
function toggleMaintenance() { showToast('Maintenance toggle not implemented yet.', 'info'); }
function cleanupDB()         { showToast('Database cleanup not implemented yet.', 'info'); }

// -- Modal helpers
function openModal(id)  { const el=document.getElementById(id); if(el) el.classList.add('open'); }
function closeModal(id) { const el=document.getElementById(id); if(el) el.classList.remove('open'); }

document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
        if (e.target === overlay) overlay.classList.remove('open');
    });
});

let _confirmCallback = null;
function showConfirm(title, message, onConfirm) {
    const titleEl = document.getElementById('confirmTitle');
    const msgEl   = document.getElementById('confirmMessage');
    if (titleEl) titleEl.textContent = title;
    if (msgEl)   msgEl.innerHTML     = message;
    _confirmCallback = onConfirm;
    openModal('confirmModal');
}

const confirmOkBtn = document.getElementById('confirmOkBtn');
if (confirmOkBtn) {
    confirmOkBtn.addEventListener('click', async () => {
        closeModal('confirmModal');
        if (_confirmCallback) { await _confirmCallback(); _confirmCallback = null; }
    });
}

// -- Toast
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const icons = { success: 'OK', error: 'ERR', info: 'i', warning: '!' };
    const toast  = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toast.onclick = () => toast.remove();
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// -- Utils
function fmtDate(ds) {
    if (!ds) return 'N/A';
    return new Date(ds).toLocaleString();
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
}
