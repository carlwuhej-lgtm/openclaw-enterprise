/**
 * OpenClaw Enterprise - 认证模块
 * Token 管理、请求拦截、登录检查
 */

const AUTH = {
    TOKEN_KEY: 'access_token',
    USER_KEY: 'user_info',

    getToken() {
        return localStorage.getItem(this.TOKEN_KEY);
    },

    getUser() {
        try {
            return JSON.parse(localStorage.getItem(this.USER_KEY));
        } catch {
            return null;
        }
    },

    setAuth(token, user) {
        localStorage.setItem(this.TOKEN_KEY, token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    },

    clear() {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.USER_KEY);
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    /** 检查登录状态，未登录跳转 login */
    requireAuth() {
        if (!this.isLoggedIn()) {
            window.location.href = '/pages/login';
            return false;
        }
        // 渲染用户信息
        this.renderUserInfo();
        return true;
    },

    /** 在顶栏显示用户名和登出按钮 */
    renderUserInfo() {
        const user = this.getUser();
        if (!user) return;

        // 找到 topbar 的右侧区域并注入用户信息
        const topbar = document.querySelector('.topbar-right') || document.querySelector('.topbar');
        if (!topbar) return;

        // 如果已经渲染过就跳过
        if (document.getElementById('user-bar')) return;

        const bar = document.createElement('div');
        bar.id = 'user-bar';
        bar.style.cssText = 'display:flex;align-items:center;gap:12px;margin-left:auto;';
        bar.innerHTML = `
            <span style="color:#94a3b8;font-size:13px;">
                👤 <strong style="color:#f1f5f9">${user.real_name || user.username}</strong>
                <span style="background:rgba(99,102,241,0.2);color:#818cf8;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:6px;">${user.role}</span>
            </span>
            <button onclick="AUTH.logout()" style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);color:#fca5a5;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px;transition:all 0.2s;">
                退出登录
            </button>
        `;
        topbar.appendChild(bar);
    },

    logout() {
        this.clear();
        window.location.href = '/pages/login';
    }
};

/**
 * 带认证的 fetch 封装，自动附加 Bearer token
 * 遇到 401 自动跳转登录
 */
async function authFetch(url, options = {}) {
    const token = AUTH.getToken();
    if (!options.headers) options.headers = {};
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    if (!options.headers['Content-Type'] && options.body && typeof options.body === 'string') {
        options.headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, options);

    if (response.status === 401) {
        AUTH.clear();
        window.location.href = '/pages/login';
        throw new Error('Unauthorized');
    }

    return response;
}
