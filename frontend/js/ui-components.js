/**
 * OpenClaw Enterprise - 通用表单和分页组件
 */

/**
 * 创建分页组件
 */
function createPagination(containerId, total, page, pageSize, onPageChange) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  const totalPages = Math.ceil(total / pageSize);
  
  let html = `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:1rem;background:var(--dark-card);border-radius:8px;">
      <div style="color:var(--text-secondary);font-size:0.85rem;">
        共 ${total} 条记录，第 ${page}/${totalPages} 页
      </div>
      <div style="display:flex;gap:0.5rem;align-items:center;">
        <button class="btn btn-secondary btn-sm" onclick="${onPageChange.name}(${page - 1})" ${page <= 1 ? 'disabled style="opacity:0.5"' : ''}>
          ⏮️ 上一页
        </button>
        <span style="color:var(--text-secondary);font-size:0.85rem;">
          ${page} / ${totalPages}
        </span>
        <button class="btn btn-secondary btn-sm" onclick="${onPageChange.name}(${page + 1})" ${page >= totalPages ? 'disabled style="opacity:0.5"' : ''}>
          下一页 ⏭️
        </button>
      </div>
    </div>
  `;
  
  container.innerHTML = html;
}

/**
 * 创建搜索筛选表单
 */
function createSearchForm(containerId, options, onSearch) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  let html = `
    <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem;">
      <input type="text" id="search-input" placeholder="搜索..." 
             style="flex:1;min-width:200px;padding:0.75rem;background:var(--dark-bg);border:1px solid var(--dark-border);border-radius:8px;color:var(--text-primary);">
  `;
  
  if (options.filters) {
    options.filters.forEach(filter => {
      html += `
        <select id="filter-${filter.key}" class="tenant-select" style="padding:0.75rem;min-width:150px;">
          <option value="">全部${filter.label}</option>
          ${filter.options.map(opt => `<option value="${opt.value}">${opt.label}</option>`).join('')}
        </select>
      `;
    });
  }
  
  html += `
      <button class="btn btn-primary" onclick="${onSearch.name}()">🔍 搜索</button>
      <button class="btn btn-secondary" onclick="${onSearch.name}('', true)">🔄 重置</button>
    </div>
  `;
  
  container.innerHTML = html;
}

/**
 * 创建表单弹窗
 */
function createModal(modalId, title, fields, onSubmit) {
  // 检查是否已存在
  if (document.getElementById(modalId)) {
    document.getElementById(modalId).remove();
  }
  
  let fieldsHtml = '';
  fields.forEach(field => {
    if (field.type === 'select') {
      fieldsHtml += `
        <div>
          <label style="display:block;margin-bottom:0.5rem;font-weight:600;">${field.label}</label>
          <select id="${field.id}" class="tenant-select" style="width:100%;padding:0.75rem;">
            ${field.options.map(opt => `<option value="${opt.value}">${opt.label}</option>`).join('')}
          </select>
        </div>
      `;
    } else if (field.type === 'textarea') {
      fieldsHtml += `
        <div>
          <label style="display:block;margin-bottom:0.5rem;font-weight:600;">${field.label}</label>
          <textarea id="${field.id}" rows="4" style="width:100%;padding:0.75rem;background:var(--dark-bg);border:1px solid var(--dark-border);border-radius:8px;color:var(--text-primary);"></textarea>
        </div>
      `;
    } else {
      fieldsHtml += `
        <div>
          <label style="display:block;margin-bottom:0.5rem;font-weight:600;">${field.label}</label>
          <input type="${field.type || 'text'}" id="${field.id}" 
                 style="width:100%;padding:0.75rem;background:var(--dark-bg);border:1px solid var(--dark-border);border-radius:8px;color:var(--text-primary);">
        </div>
      `;
    }
  });
  
  const modalHtml = `
    <div id="${modalId}" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:9999;">
      <div style="background:var(--dark-card);border-radius:12px;padding:2rem;max-width:600px;width:90%;max-height:90vh;overflow-y:auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;">
          <h3 style="font-size:1.25rem;font-weight:600;">${title}</h3>
          <button onclick="document.getElementById('${modalId}').remove()" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:1.5rem;">&times;</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:1rem;">
          ${fieldsHtml}
        </div>
        <div style="display:flex;gap:1rem;margin-top:1.5rem;">
          <button class="btn btn-primary" onclick="${onSubmit.name}()" style="flex:1;justify-content:center;">💾 保存</button>
          <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove()" style="flex:1;justify-content:center;">取消</button>
        </div>
      </div>
    </div>
  `;
  
  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

/**
 * 创建确认弹窗
 */
function createConfirmModal(modalId, title, message, onConfirm) {
  if (document.getElementById(modalId)) {
    document.getElementById(modalId).remove();
  }
  
  const modalHtml = `
    <div id="${modalId}" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:9999;">
      <div style="background:var(--dark-card);border-radius:12px;padding:2rem;max-width:400px;width:90%;">
        <div style="text-align:center;margin-bottom:1.5rem;">
          <div style="font-size:3rem;margin-bottom:1rem;">⚠️</div>
          <h3 style="font-size:1.25rem;font-weight:600;margin-bottom:0.5rem;">${title}</h3>
          <p style="color:var(--text-secondary);">${message}</p>
        </div>
        <div style="display:flex;gap:1rem;">
          <button class="btn btn-danger" onclick="${onConfirm.name}()" style="flex:1;justify-content:center;">确认</button>
          <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove()" style="flex:1;justify-content:center;">取消</button>
        </div>
      </div>
    </div>
  `;
  
  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

/**
 * 显示提示消息
 */
function showToast(message, type = 'info') {
  const colors = {
    info: 'var(--primary)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    error: 'var(--danger)'
  };
  
  const icons = {
    info: 'ℹ️',
    success: '✅',
    warning: '⚠️',
    error: '❌'
  };
  
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed;top:20px;right:20px;background:${colors[type]};color:#fff;
    padding:1rem 1.5rem;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.3);
    z-index:10000;animation:slideIn 0.3s ease;
  `;
  toast.textContent = `${icons[type]} ${message}`;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from { transform: translateX(400px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  @keyframes slideOut {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(400px); opacity: 0; }
  }
`;
document.head.appendChild(style);

// 导出函数
window.OpenClawUI = {
  createPagination,
  createSearchForm,
  createModal,
  createConfirmModal,
  showToast
};
