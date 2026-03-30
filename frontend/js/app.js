/**
 * OpenClaw Enterprise - 前端 JavaScript
 * 处理 API 调用和页面交互
 */

const API_BASE = window.location.origin + '/api';

// ==================== 认证工具 ====================
function getToken() {
  return localStorage.getItem('access_token');
}

function checkAuth() {
  const token = getToken();
  if (!token) {
    // 如果当前不在登录页，跳转到登录页
    if (!window.location.pathname.includes('login.html')) {
      window.location.href = '/pages/login.html';
    }
    return false;
  }
  return true;
}

function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('user_info');
  window.location.href = '/pages/login.html';
}

function getUserInfo() {
  const userInfo = localStorage.getItem('user_info');
  return userInfo ? JSON.parse(userInfo) : null;
}

// ==================== 工具函数 ====================
function formatTime(dateString) {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now - date;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (hours < 24) return `${hours} 小时前`;
  if (days < 7) return `${days} 天前`;
  return date.toLocaleDateString('zh-CN');
}

function getRiskLabel(score) {
  if (score < 30) return { label: '低', class: 'low' };
  if (score < 70) return { label: '中', class: 'medium' };
  return { label: '高', class: 'high' };
}

function getStatusBadge(status) {
  const badges = {
    'online': '<span class="badge badge-green">● 在线</span>',
    'offline': '<span class="badge badge-gray">● 离线</span>',
    'warning': '<span class="badge badge-yellow">● 需升级</span>',
    'violation': '<span class="badge badge-red">● 违规</span>'
  };
  return badges[status] || '<span class="badge badge-gray">● 未知</span>';
}

function getAuditStatusBadge(status) {
  const badges = {
    'allowed': '<span class="badge badge-green">✅ 允许</span>',
    'blocked': '<span class="badge badge-red">🚫 阻断</span>',
    'pending': '<span class="badge badge-yellow">⏳ 待审批</span>'
  };
  return badges[status] || '<span class="badge badge-gray">? 未知</span>';
}

function getOperationIcon(type) {
  const icons = {
    'file_read': '📁 文件读取',
    'command_exec': '⚡ 命令执行',
    'api_call': '🔑 API 调用',
    'message_send': '💬 消息发送',
    'web_crawl': '🌐 网页爬取'
  };
  return icons[type] || type;
}

function showAlertLevel(level) {
  const levels = {
    'critical': { icon: '🔴', class: 'critical', color: 'var(--danger)' },
    'high': { icon: '🟠', class: 'high', color: 'var(--warning)' },
    'medium': { icon: '🔵', class: 'medium', color: 'var(--primary)' },
    'low': { icon: '🟢', class: 'low', color: 'var(--success)' }
  };
  return levels[level] || { icon: '⚪', class: 'low', color: 'var(--text-muted)' };
}

// ==================== API 调用（带认证） ====================
// 带认证的 fetch，自动添加 Bearer token，处理 401
async function authFetch(url, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers
  });

  // 401 未授权，跳转登录页
  if (response.status === 401) {
    logout();
    throw new Error('Unauthorized');
  }

  return response;
}
async function fetchAPI(endpoint) {
  try {
    const response = await authFetch(`${API_BASE}${endpoint}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (error.message === 'Unauthorized') return null;
    console.error(`API Error (${endpoint}):`, error);
    return null;
  }
}

async function updateAPI(endpoint, data, method = 'PUT') {
  try {
    const response = await authFetch(`${API_BASE}${endpoint}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (error.message === 'Unauthorized') return null;
    console.error(`API Update Error (${endpoint}):`, error);
    return null;
  }
}

// ==================== 数据加载 ====================
async function loadStats() {
  const stats = await fetchAPI('/stats');
  if (!stats) return;
  
  document.getElementById('stat-total-devices').textContent = stats.total_devices;
  document.getElementById('stat-weekly-trend').textContent = `↑ ${stats.weekly_new_devices} 本周新增`;
  document.getElementById('stat-pending').textContent = stats.pending_approvals;
  document.getElementById('stat-critical-alerts').textContent = stats.critical_alerts;
  document.getElementById('stat-audit-logs').textContent = stats.today_audit_logs.toLocaleString();
  document.getElementById('stat-audit-trend').textContent = '↑ 实时更新';
}

async function loadDevices() {
  const devicesData = await fetchAPI('/devices');
  if (!devicesData) return;
  const devices = devicesData.items || devicesData;
  
  const tbody = document.getElementById('devices-table');
  if (!tbody) return;
  
  if (!devices || devices.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text-muted);">暂无设备</td></tr>';
    return;
  }
  
  // 获取用户和租户信息
  const usersData = await fetchAPI('/users') || {};
  const tenantsData = await fetchAPI('/tenants') || {};
  const users = usersData.items || usersData || [];
  const tenants = tenantsData.items || tenantsData || [];
  
  tbody.innerHTML = devices.map(device => {
    const user = users.find(u => u.id === device.user_id);
    const tenant = tenants.find(t => t.id === device.tenant_id);
    const risk = getRiskLabel(device.risk_score);
    
    return `
      <tr>
        <td>
          <div class="device-cell">
            <span class="device-name">${device.status === 'violation' ? '⚠️' : '💻'} ${device.name}</span>
            <span class="device-meta">${tenant ? tenant.name : '未授权'} · ${device.version}</span>
          </div>
        </td>
        <td>${user ? user.real_name : '<span style="color:var(--danger)">未识别</span>'}</td>
        <td>${getStatusBadge(device.status)}</td>
        <td>
          <div class="risk-indicator">
            <div class="risk-track"><div class="risk-fill ${risk.class}" style="width:${device.risk_score}%"></div></div>
            <span class="risk-label ${risk.class}">${risk.label}</span>
          </div>
        </td>
        <td style="color:var(--text-muted)">${formatTime(device.last_active)}</td>
        <td>
          ${device.status === 'violation' 
            ? '<button class="btn btn-danger btn-sm" onclick="blockDevice(' + device.id + ')">🚫 阻断</button>'
            : '<button class="btn btn-secondary btn-sm" onclick="viewDevice(' + device.id + ')">详情</button>'
          }
        </td>
      </tr>
    `;
  }).join('');
}

async function loadAuditLogs() {
  const logsData = await fetchAPI('/audit-logs?page_size=5');
  if (!logsData) return;
  const logs = logsData.items || logsData;
  
  const tbody = document.getElementById('audit-table');
  if (!tbody) return;
  
  if (logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted);">暂无审计日志</td></tr>';
    return;
  }
  
  tbody.innerHTML = logs.map(log => `
    <tr>
      <td style="color:var(--text-muted);font-family:monospace">${new Date(log.timestamp).toLocaleTimeString('zh-CN')}</td>
      <td>${log.device_id ? 'Device-' + log.device_id : '未知'}</td>
      <td>${getOperationIcon(log.operation_type)}</td>
      <td style="font-family:monospace;font-size:0.8rem;color:var(--text-muted)">${log.operation_detail}</td>
      <td>${getAuditStatusBadge(log.status)}</td>
    </tr>
  `).join('');
}

async function loadAlerts() {
  const alertsData = await fetchAPI('/alerts');
  if (!alertsData) return;
  const alerts = alertsData.items || alertsData;
  
  // 更新告警徽章
  const badge = document.getElementById('alert-badge');
  if (badge) {
    const criticalCount = alerts.filter(a => a.level === 'critical').length;
    badge.textContent = criticalCount || '';
    badge.style.display = criticalCount ? 'inline-block' : 'none';
  }
  
  const container = document.getElementById('alerts-list');
  if (!container) return;
  
  if (alerts.length === 0) {
    container.innerHTML = '<div style="text-align:center;padding:1rem;color:var(--text-muted);">暂无告警</div>';
    return;
  }
  
  container.innerHTML = alerts.slice(0, 4).map(alert => {
    const level = showAlertLevel(alert.level);
    return `
      <div class="alert-item ${level.class}">
        <div class="alert-header">
          <span class="alert-title" style="color:${level.color}">${level.icon} ${alert.title}</span>
          <span class="alert-time">${formatTime(alert.created_at)}</span>
        </div>
        <div class="alert-desc">${alert.description}</div>
      </div>
    `;
  }).join('');
}

async function loadPolicies() {
  const policiesData = await fetchAPI('/policies');
  if (!policiesData) return;
  const policies = policiesData.items || policiesData;
  
  const container = document.getElementById('policies-list');
  if (!container) return;
  
  container.innerHTML = policies.map(policy => `
    <div class="switch-item">
      <span class="switch-label">${policy.name.includes('禁止') ? '🚫' : policy.name.includes('密钥') ? '🔑' : policy.name.includes('外部') ? '🌐' : policy.name.includes('沙箱') ? '📦' : policy.name.includes('审批') ? '⚠️' : policy.name.includes('日志') ? '📊' : '🔄'} ${policy.name}</span>
      <div class="switch ${policy.is_enabled ? 'on' : ''}" data-id="${policy.id}" onclick="togglePolicy(this)"></div>
    </div>
  `).join('');
}

async function loadTenants() {
  const tenantsData = await fetchAPI('/tenants');
  const devicesData = await fetchAPI('/devices');
  if (!tenantsData) return;
  const tenants = tenantsData.items || tenantsData;
  const devices = (devicesData && (devicesData.items || devicesData)) || [];
  
  const container = document.getElementById('tenants-list');
  if (!container) return;
  
  const total = devices.length;
  
  container.innerHTML = tenants.map(tenant => {
    const count = devices.filter(d => d.tenant_id === tenant.id).length;
    const percent = total > 0 ? Math.round((count / total) * 100) : 0;
    const colorClass = tenant.code === 'RD' ? 'blue' : tenant.code === 'OPS' ? 'green' : 'orange';
    const icon = tenant.code === 'RD' ? '🏢' : tenant.code === 'OPS' ? '🔧' : '📊';
    
    return `
      <div class="tenant-item">
        <div class="tenant-header">
          <span class="tenant-name">${icon} ${tenant.name}</span>
          <span class="tenant-count" style="color:var(--${colorClass === 'blue' ? 'primary' : colorClass === 'green' ? 'success' : 'warning'})">${count} 实例</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${colorClass}" style="width:${percent}%"></div>
        </div>
      </div>
    `;
  }).join('');
}

// ==================== 操作函数 ====================
async function togglePolicy(element) {
  const policyId = element.dataset.id;
  const isEnabled = element.classList.contains('on');
  
  const result = await updateAPI(`/policies/${policyId}`, { is_enabled: !isEnabled });
  if (result) {
    element.classList.toggle('on');
  }
}

async function savePolicies() {
  alert('✅ 配置已保存！');
}

async function scanDevices() {
  alert('🔍 正在扫描网络中的 OpenClaw 实例...\n\n（演示功能：实际实现需要网络扫描模块）');
}

async function viewDevice(deviceId) {
  window.location.href = `/pages/devices?id=${deviceId}`;
}

async function blockDevice(deviceId) {
  if (confirm('⚠️ 确定要阻断此设备吗？\n\n阻断后该设备将无法连接企业内网资源。')) {
    // 实际实现需要调用 API
    alert('✅ 设备已阻断！');
  }
}

// ==================== 页面导航 ====================
function navigateTo(page) {
  window.location.href = `/pages/${page}`;
}

// ==================== 自动刷新 ====================
// 每 30 秒刷新一次数据
setInterval(() => {
  loadStats();
  loadAlerts();
}, 30000);

// ==================== 自动初始化 ====================
// 页面加载时检查认证状态（排除登录页和急救室）
if (!window.location.pathname.includes('login.html') && !window.location.pathname.includes('clinic.html')) {
  checkAuth();
}
