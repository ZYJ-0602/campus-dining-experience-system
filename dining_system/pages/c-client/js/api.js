function resolveApiBaseUrl() {
    if (window.Common && window.Common.config && window.Common.config.apiBaseUrl) {
        return window.Common.config.apiBaseUrl;
    }

    // 本地静态服务调试场景：前端通常跑在 8000，后端跑在 5000
    if (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') {
        if (window.location.port === '8000' || window.location.port === '5500') {
            return 'http://127.0.0.1:5000/api';
        }
    }

    // 生产环境默认同域反向代理
    return '/api';
}

const API_BASE_URL = resolveApiBaseUrl();

const API = {
    LOGIN: `${API_BASE_URL}/login`,
    LOGOUT: `${API_BASE_URL}/logout`,
    REGISTER: `${API_BASE_URL}/register`,
    USER_PROFILE: `${API_BASE_URL}/user/profile`,
    AUTH_ME: `${API_BASE_URL}/auth/me`,
    CANTEENS: `${API_BASE_URL}/canteens`,
    CAMPUSES: `${API_BASE_URL}/public/campuses`,
    WINDOWS: `${API_BASE_URL}/windows`,
    DISHES: `${API_BASE_URL}/dishes`,
    SUBMIT_EVALUATION: `${API_BASE_URL}/submit_evaluation`,
    RECOMMENDATIONS: `${API_BASE_URL}/public/recommendations`,
    RECOMMENDATION_TRACK: `${API_BASE_URL}/public/recommendations/track`,
    RECOMMENDATION_AB_METRICS: `${API_BASE_URL}/admin/recommendation_ab_metrics`,
    PUBLIC_CANTEENS: `${API_BASE_URL}/public/canteens`,
    MY_EVALUATIONS: `${API_BASE_URL}/my_evaluations`,
    MY_NOTES: `${API_BASE_URL}/my_notes`,
    FAVORITES: `${API_BASE_URL}/favorites`,
    FEEDBACK: `${API_BASE_URL}/feedback`,
    DISH_EVALUATIONS: `${API_BASE_URL}/dish_evaluations`,
    CANTEEN_DETAIL: `${API_BASE_URL}/canteen_detail`,
    SEND_SMS: `${API_BASE_URL}/send_sms`,
    RESET_PASSWORD: `${API_BASE_URL}/reset_password`
};

function parseStoredUser() {
    try {
        const raw = localStorage.getItem('user');
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        return null;
    }
}

function persistAuthUser(userData) {
    if (!userData || typeof userData !== 'object') {
        localStorage.removeItem('user');
        localStorage.removeItem('isLogin');
        return;
    }

    const oldUser = parseStoredUser();
    if (oldUser && oldUser.id && userData.id && Number(oldUser.id) !== Number(userData.id)) {
        sessionStorage.setItem('auth_user_switched', '1');
    }

    localStorage.setItem('user', JSON.stringify(userData));
    localStorage.setItem('isLogin', 'true');
}

async function syncUserFromAuthMe(showSwitchAlert = false) {
    const res = await fetchApi(API.AUTH_ME, { method: 'GET', skipAuthAutoClear: true });
    if (res.code !== 200) {
        localStorage.removeItem('user');
        localStorage.removeItem('isLogin');
        return { ok: false, data: null };
    }

    persistAuthUser(res.data || {});
    if (showSwitchAlert && sessionStorage.getItem('auth_user_switched') === '1') {
        sessionStorage.removeItem('auth_user_switched');
        alert('检测到当前浏览器登录账号发生变化，页面身份已自动同步为最新登录账号。');
    }
    return { ok: true, data: res.data || {} };
}

// 简单的请求封装
async function fetchApi(url, options = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json'
    };

    const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 10000;
    const controller = new AbortController();
    const externalSignal = options.signal;
    if (externalSignal) {
        if (externalSignal.aborted) {
            controller.abort();
        } else {
            externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
        }
    }
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const requestOptions = {
        ...options,
        headers: { ...defaultHeaders, ...options.headers },
        credentials: options.credentials || 'include',
        signal: controller.signal
    };
    
    try {
        const response = await fetch(url, requestOptions);
        // 先读取响应体，即使状态码是 4xx/5xx，后端可能也返回了错误信息 JSON
        let data;
        try {
            data = await response.json();
        } catch (e) {
            // 如果不是 JSON，说明是严重的服务器错误或网络问题
            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status}`);
            }
            // 如果是 200 但非 JSON，视为空对象
            data = {};
        }

        // 统一返回格式，优先使用后端返回的 msg
        if (!response.ok) {
            if (response.status === 401 && !requestOptions.skipAuthAutoClear) {
                localStorage.removeItem('user');
                localStorage.removeItem('isLogin');
            }
            return { 
                code: response.status, 
                msg: data.msg || `服务器错误 (${response.status})` 
            };
        }
        
        return data;
    } catch (error) {
        console.error('API Error:', error);
        if (error.name === 'AbortError') {
            return { code: 408, msg: `请求超时(${Math.ceil(timeoutMs / 1000)}秒)，请稍后重试` };
        }
        // 如果是 fetch 本身抛出的错误（如网络断开、跨域被拦截），通常 message 是 "Failed to fetch"
        const msg = error.message === 'Failed to fetch' 
            ? '无法连接到服务器，请检查后端服务是否启动' 
            : `网络请求失败: ${error.message}`;
        return { code: 500, msg: msg };
    } finally {
        clearTimeout(timeoutId);
    }
}
