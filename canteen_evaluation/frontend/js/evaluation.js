// 全局状态
let selectedDishes = [];

document.addEventListener('DOMContentLoaded', function() {
    // 1. 加载菜品列表
    loadDishes();
    
    // 2. 初始化时间
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('purchaseTime').value = now.toISOString().slice(0, 16);
});

// 加载菜品
async function loadDishes() {
    try {
        const res = await fetch('/api/dishes');
        const dishes = await res.json();
        const container = document.getElementById('dishList');
        
        dishes.forEach(dish => {
            const html = `
                <input type="checkbox" class="dish-checkbox" id="dish_${dish.id}" value="${dish.name}" onchange="toggleDish(this)">
                <label for="dish_${dish.id}" class="dish-label">${dish.name}</label>
            `;
            container.innerHTML += html;
        });
    } catch (e) {
        console.error("加载菜品失败", e);
    }
}

// 身份切换逻辑
function onIdentityChange() {
    const identity = document.getElementById('userIdentity').value;
    const studentSection = document.getElementById('studentInfoSection');
    
    if (identity === 'student') {
        studentSection.style.display = 'block';
        // 设置必填
        document.getElementById('studentGrade').required = true;
        document.getElementById('studentAge').required = true;
        document.getElementById('diningYears').required = true;
    } else {
        studentSection.style.display = 'none';
        document.getElementById('studentGrade').required = false;
        document.getElementById('studentAge').required = false;
        document.getElementById('diningYears').required = false;
    }
}

// 菜品选择逻辑
function toggleDish(checkbox) {
    const dishName = checkbox.value;
    const container = document.getElementById('foodRatingContainer');
    
    if (checkbox.checked) {
        if (selectedDishes.length >= 5) {
            alert("最多选择5个菜品");
            checkbox.checked = false;
            return;
        }
        selectedDishes.push(dishName);
        // 添加评分卡片
        addFoodRatingCard(dishName);
    } else {
        selectedDishes = selectedDishes.filter(d => d !== dishName);
        // 移除评分卡片
        const card = document.getElementById(`card_${dishName}`);
        if (card) card.remove();
    }
}

// 动态生成食品评分卡片
function addFoodRatingCard(dishName) {
    const container = document.getElementById('foodRatingContainer');
    const html = `
        <div class="eval-card active" id="card_${dishName}">
            <div class="card-title">
                <i class="bi bi-egg-fried"></i> 评价：${dishName}
            </div>
            <div class="row">
                ${generateRangeHTML('taste', '口味')}
                ${generateRangeHTML('color', '色泽')}
                ${generateRangeHTML('appearance', '品相')}
                ${generateRangeHTML('price', '价格合理性')}
                ${generateRangeHTML('portion', '分量')}
                ${generateRangeHTML('speed', '出餐速度')}
            </div>
            <div class="mt-3">
                <textarea class="form-control" placeholder="备注（可选）" name="comment"></textarea>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
}

function generateRangeHTML(key, label) {
    return `
        <div class="col-6 range-wrap">
            <div class="range-label">
                <span>${label}</span>
                <span class="score-value" id="val_${key}">0</span>
            </div>
            <input type="range" class="custom-range" min="0" max="10" value="0" 
                data-key="${key}" oninput="this.previousElementSibling.querySelector('.score-value').innerText = this.value">
        </div>
    `;
}

// 提交逻辑
async function submitForm() {
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.innerText = "提交中...";

    try {
        // 1. 收集基础信息
        const data = {
            purchase_time: document.getElementById('purchaseTime').value,
            user_identity: document.getElementById('userIdentity').value,
            student_grade: document.getElementById('studentGrade').value,
            student_age: document.getElementById('studentAge').value,
            dining_years: document.getElementById('diningYears').value,
            
            // 环境
            env_comfort: document.getElementById('env_comfort').value,
            env_temp: document.getElementById('env_temp').value,
            env_layout: document.getElementById('env_layout').value,
            env_comment: document.getElementById('env_comment').value,
            
            // 服务
            svc_attire: document.getElementById('svc_attire').value,
            svc_attitude: document.getElementById('svc_attitude').value,
            svc_hygiene: document.getElementById('svc_hygiene').value,
            svc_comment: document.getElementById('svc_comment').value,
            svc_personnel: getCheckedValues('svc_personnel'),
            
            // 菜品 (数组)
            dishes: []
        };

        // 2. 收集菜品评分
        selectedDishes.forEach(dishName => {
            const card = document.getElementById(`card_${dishName}`);
            const dishData = {
                name: dishName,
                comment: card.querySelector('textarea[name="comment"]').value
            };
            card.querySelectorAll('input[type="range"]').forEach(input => {
                dishData[input.dataset.key] = input.value;
            });
            data.dishes.push(dishData);
        });

        // 3. 发送请求
        const res = await fetch('/api/submit_review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await res.json();
        
        if (res.ok) {
            alert("评价提交成功！");
            location.reload();
        } else {
            alert("提交失败：" + result.error);
        }
        
    } catch (e) {
        alert("网络错误，请稍后重试");
        console.error(e);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerText = "提交评价";
    }
}

function getCheckedValues(name) {
    const checked = [];
    document.querySelectorAll(`input[name="${name}"]:checked`).forEach(el => checked.push(el.value));
    return checked;
}
