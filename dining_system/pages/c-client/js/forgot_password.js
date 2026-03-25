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

// 发送短信验证码 (模拟)
let countdown = 0;
let timer = null;

async function sendSmsCode() {
    const phoneInput = document.getElementById('resetPhone');
    const phone = phoneInput.value;
    
    if (!/^1[3-9]\d{9}$/.test(phone)) {
        alert('请输入正确的手机号码！');
        phoneInput.focus();
        return;
    }

    if (countdown > 0) return;

    const btn = document.getElementById('btnSendCode');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '发送中...';

    try {
        const res = await fetchApi(API.SEND_SMS, {
            method: 'POST',
            body: JSON.stringify({ phone })
        });

        if (res.code === 200) {
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
        } else {
            alert(res.msg || '发送失败');
            btn.disabled = false;
            btn.textContent = originalText;
        }
    } catch (error) {
        console.error(error);
        alert('网络错误，请重试');
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// 处理密码重置
async function handleReset(e) {
    e.preventDefault();
    const phone = document.getElementById('resetPhone').value;
    const code = document.getElementById('resetCode').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    if (newPassword !== confirmPassword) {
        alert('两次输入的密码不一致！');
        return;
    }

    if (code.length !== 6) {
        alert('请输入6位验证码！');
        return;
    }

    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 重置中...';
    btn.disabled = true;

    try {
        const res = await fetchApi(API.RESET_PASSWORD, {
            method: 'POST',
            body: JSON.stringify({
                phone,
                code,
                password: newPassword
            })
        });

        if (res.code === 200) {
            alert('密码重置成功！请使用新密码登录');
            location.href = 'login.html';
        } else {
            alert(res.msg || '重置失败');
        }
    } catch (error) {
        console.error(error);
        alert('系统错误，请重试');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('resetForm').addEventListener('submit', handleReset);
    
    // 绑定密码显示切换
    const toggle = document.querySelector('.password-toggle');
    if(toggle) {
        toggle.addEventListener('click', function() {
            togglePassword('newPassword', this);
        });
    }
});
