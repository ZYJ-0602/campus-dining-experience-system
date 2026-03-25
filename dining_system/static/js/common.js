/**
 * common.js - 校园食堂点评系统通用脚本库
 * 包含：页面跳转、数据存储、表单校验、UI交互等通用方法
 */

const detectedApiBaseUrl = (() => {
    const fromStorage = localStorage.getItem('apiBaseUrl');
    if (fromStorage) return fromStorage;

    if (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') {
        if (window.location.port === '8000' || window.location.port === '5500') {
            return 'http://127.0.0.1:5000/api';
        }
    }
    return '/api';
})();

const Common = {
    // ========================
    // 1. 基础配置
    // ========================
    config: {
        baseUrl: '../../pages/', // 默认页面根路径 (相对于js文件)
        apiBaseUrl: detectedApiBaseUrl, // 后端API根路径
        homePage: 'c-client/index.html',
        loginPage: 'c-client/login.html'
    },

    // ========================
    // 2. 页面跳转
    // ========================
    
    /**
     * 跳转到指定页面
     * @param {string} path - 相对路径 (如 'c-client/index.html')
     * @param {object} params - URL参数对象 (如 {id: 1, type: 'food'})
     */
    jumpTo: function(path, params = {}) {
        let url = path;
        
        // 处理参数
        const paramArr = [];
        for (let key in params) {
            paramArr.push(`${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`);
        }
        
        if (paramArr.length > 0) {
            url += (url.includes('?') ? '&' : '?') + paramArr.join('&');
        }
        
        window.location.href = url;
    },

    /**
     * 返回上一页
     */
    goBack: function() {
        window.history.back();
    },

    /**
     * 获取URL参数
     * @param {string} name - 参数名
     * @returns {string|null} 参数值
     */
    getUrlParam: function(name) {
        const reg = new RegExp("(^|&)" + name + "=([^&]*)(&|$)");
        const r = window.location.search.substr(1).match(reg);
        if (r != null) return decodeURIComponent(r[2]); 
        return null;
    },

    // ========================
    // 3. 数据存储 (LocalStorage)
    // ========================

    /**
     * 设置本地缓存
     * @param {string} key 键
     * @param {any} value 值 (自动JSON序列化)
     */
    setStorage: function(key, value) {
        try {
            const data = JSON.stringify(value);
            localStorage.setItem(key, data);
        } catch (e) {
            console.error('Set storage error:', e);
        }
    },

    /**
     * 获取本地缓存
     * @param {string} key 键
     * @returns {any} 解析后的值
     */
    getStorage: function(key) {
        try {
            const data = localStorage.getItem(key);
            return data ? JSON.parse(data) : null;
        } catch (e) {
            console.error('Get storage error:', e);
            return null;
        }
    },

    /**
     * 检查是否登录
     * @returns {boolean}
     */
    isLogin: function() {
        return !!(this.getStorage('currentUser') || this.getStorage('user'));
    },

    /**
     * 拼接API URL
     * @param {string} path - API路径，如 '/login'
     * @returns {string}
     */
    apiUrl: function(path) {
        const base = this.config.apiBaseUrl.replace(/\/$/, '');
        const normalized = path.startsWith('/') ? path : `/${path}`;
        return `${base}${normalized}`;
    },

    /**
     * 统一请求封装，默认携带 Session Cookie
     * @param {string} path - API路径
     * @param {object} options - fetch 配置
     * @returns {Promise<object>}
     */
    apiFetch: async function(path, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };

        const requestOptions = {
            credentials: 'include',
            ...options,
            headers
        };

        const response = await fetch(this.apiUrl(path), requestOptions);
        let payload = {};
        try {
            payload = await response.json();
        } catch (e) {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
        }

        if (!response.ok) {
            return {
                code: response.status,
                msg: payload.msg || `请求失败(${response.status})`,
                data: payload.data || {}
            };
        }
        return payload;
    },

    /**
     * 退出登录
     */
    logout: async function() {
        try {
            await this.apiFetch('/logout', { method: 'POST' });
        } catch (e) {
            console.warn('Logout request failed:', e);
        }
        localStorage.clear();
        this.jumpTo(this.config.loginPage);
    },

    // ========================
    // 4. 表单校验
    // ========================

    validator: {
        /**
         * 校验手机号 (中国大陆)
         */
        isPhone: function(phone) {
            return /^1[3-9]\d{9}$/.test(phone);
        },

        /**
         * 校验密码强度 (6-20位，含字母和数字)
         */
        isPassword: function(pwd) {
            return /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{6,20}$/.test(pwd);
        },

        /**
         * 校验必填项
         */
        isRequired: function(val) {
            return val !== null && val !== undefined && String(val).trim() !== '';
        }
    },

    // ========================
    // 5. UI 交互
    // ========================

    /**
     * 显示加载动画
     * @param {string} msg - 提示文字
     */
    showLoading: function(msg = '加载中...') {
        // 防止重复创建
        if (document.getElementById('common-loading')) return;

        const html = `
            <div id="common-loading" class="loading-mask">
                <div class="spinner-custom"></div>
                <div style="margin-top: 15px; color: #666; font-size: 14px;">${msg}</div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
    },

    /**
     * 隐藏加载动画
     */
    hideLoading: function() {
        const el = document.getElementById('common-loading');
        if (el) el.remove();
    },

    /**
     * 显示轻提示 (Toast)
     * @param {string} msg - 消息内容
     * @param {string} type - 类型 (success/error/info)
     * @param {number} duration - 显示时长(ms)
     */
    toast: function(msg, type = 'info', duration = 2000) {
        const toastId = 'toast-' + Date.now();
        let bgColor = '#333';
        if (type === 'success') bgColor = '#28a745';
        if (type === 'error') bgColor = '#dc3545';

        const html = `
            <div id="${toastId}" style="
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background-color: ${bgColor};
                color: #fff;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 14px;
                z-index: 10000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                opacity: 0;
                transition: opacity 0.3s;
            ">
                ${msg}
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
        
        // 淡入
        setTimeout(() => {
            const el = document.getElementById(toastId);
            if (el) el.style.opacity = '1';
        }, 10);

        // 自动消失
        setTimeout(() => {
            const el = document.getElementById(toastId);
            if (el) {
                el.style.opacity = '0';
                setTimeout(() => el.remove(), 300);
            }
        }, duration);
    }
};

// 导出 (如果是模块化开发)
// export default Common;
