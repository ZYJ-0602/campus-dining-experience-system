// 密码显示/隐藏切换
function togglePassword(inputId, iconEl) {
    const input = document.getElementById(inputId);
    const icon = iconEl.querySelector('i');
    
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('bi-eye-slash', 'bi-eye');
    } else {
        input.type = 'password';
        icon.classList.replace('bi-eye', 'bi-eye-slash');
    }
}

// 刷新图片验证码 (已移除)
// function refreshCaptcha(imgEl) {
//    const randomCode = Math.floor(1000 + Math.random() * 9000);
//    imgEl.src = `https://via.placeholder.com/100x42/eee/999?text=${randomCode}`;
//    imgEl.dataset.code = randomCode;
// }

// 发送短信验证码 (模拟)
let countdown = 0;
let timer = null;

function sendSmsCode() {
    const phoneInput = document.getElementById('regPhone');
    const phone = phoneInput.value;
    
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        alert('请输入正确的手机号码！');
        phoneInput.focus();
        return;
    }

    if (countdown > 0) return;

    const btn = document.getElementById('btnSendCode');
    btn.disabled = true;
    btn.textContent = '发送中...';

    setTimeout(() => {
        alert(`验证码已发送至 ${phone}，请注意查收（测试码：123456）`);
        
        countdown = 60;
        btn.textContent = `${countdown}s后重发`;
        
        timer = setInterval(() => {
            countdown--;
            if (countdown <= 0) {
                clearInterval(timer);
                btn.disabled = false;
                btn.textContent = '获取验证码';
            } else {
                btn.textContent = `${countdown}s后重发`;
            }
        }, 1000);
    }, 1000);
}

// 处理登录
async function handleLogin(e) {
    e.preventDefault();
    const account = document.getElementById('loginAccount').value.trim();
    const password = document.getElementById('loginPassword').value;
    const btn = e.target.querySelector('button[type="submit"]');

    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 登录中...';
    btn.disabled = true;

    try {
        const res = await fetchApi(API.LOGIN, {
            method: 'POST',
            // 确保只发送简单的 JSON，不要带复杂的 headers
            body: JSON.stringify({ username: account, password })
        });

        if (res.code === 200) {
            // 存储登录状态
            localStorage.setItem('user', JSON.stringify(res.data));
            localStorage.setItem('isLogin', 'true');
            if (window.Common && typeof window.Common.setStorage === 'function') {
                window.Common.setStorage('currentUser', res.data);
            }
            
            // 修复：跳转路径可能需要根据部署环境调整，这里使用相对路径
            location.href = './index.html'; 
        } else {
            alert(res.msg || '登录失败');
        }
    } catch (error) {
        console.error(error);
        alert('系统错误，请重试');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// 处理注册
async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('regUsername').value.trim();
    const phone = document.getElementById('regPhone').value;
    const password = document.getElementById('regPassword').value;
    const confirmPwd = document.getElementById('regConfirmPassword').value;
    const smsCode = document.getElementById('regSmsCode').value;

    if (password !== confirmPwd) {
        alert('两次输入的密码不一致！');
        return;
    }

    if (smsCode !== '123456') {
        alert('短信验证码错误！(测试请使用 123456)');
        return;
    }

    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 注册中...';
    btn.disabled = true;

    try {
        const res = await fetchApi(API.REGISTER, {
            method: 'POST',
            body: JSON.stringify({ username, phone, password })
        });

        if (res.code === 200) {
            alert('注册成功！已自动登录');
            localStorage.setItem('user', JSON.stringify(res.data));
            localStorage.setItem('isLogin', 'true');
            if (window.Common && typeof window.Common.setStorage === 'function') {
                window.Common.setStorage('currentUser', res.data);
            }
            location.href = 'index.html';
        } else {
            alert(res.msg || '注册失败');
        }
    } catch (error) {
        console.error(error);
        alert('系统错误，请重试');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// 切换Tab辅助函数 (仅供外部链接调用)
function switchTab(tabId) {
    const tabEl = document.getElementById(tabId);
    if (!tabEl) return;
    
    // 使用 Bootstrap 的 Tab 实例进行切换
    const tab = bootstrap.Tab.getOrCreateInstance(tabEl);
    tab.show();
}

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
    // 绑定表单提交事件
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    
    if(loginForm) loginForm.addEventListener('submit', handleLogin);
    if(registerForm) registerForm.addEventListener('submit', handleRegister);

    // 绑定 Tab 切换事件，确保点击时能切换
    const tabEls = document.querySelectorAll('button[data-bs-toggle="tab"]');
    tabEls.forEach(tabEl => {
        tabEl.addEventListener('click', function(event) {
            // 确保点击时切换
            // switchTab(this.id); // 移除这行，Bootstrap data-bs-toggle="tab" 会自动处理，重复调用可能导致冲突
        });
    });

    // 支持独立注册入口：login.html?tab=register 或 login.html#register
    const params = new URLSearchParams(window.location.search);
    const tabParam = (params.get('tab') || '').toLowerCase();
    const hash = (window.location.hash || '').toLowerCase();
    if (tabParam === 'register' || hash === '#register') {
        switchTab('register-tab');
    }
});
