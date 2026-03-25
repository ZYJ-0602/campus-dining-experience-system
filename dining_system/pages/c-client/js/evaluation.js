// js/evaluation.js
// 全局状态
let selectedDishes = [];
let canteens = []; // Store canteens data

// 自动调整 textarea 高度
function initAutoResizeTextarea() {
    document.addEventListener('input', function (e) {
        if (e.target.classList.contains('auto-height-textarea')) {
            e.target.style.height = 'auto'; 
            e.target.style.height = (e.target.scrollHeight) + 'px';
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // 检查登录状态
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        alert("请先登录！");
        location.href = 'login.html';
        return;
    }

    // 1. 加载食堂列表
    loadCanteens();
    
    // 2. 加载推荐菜品列表 (默认显示一些，或者等选择了窗口后再加载，这里先加载所有或部分)
    loadDishes();
    
    // 3. 初始化时间
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    const timeInput = document.getElementById('purchaseTime');
    if (timeInput) {
        timeInput.value = now.toISOString().slice(0, 16);
    }
    
    // 4. 初始化文本框自适应
    initAutoResizeTextarea();
    
    // 绑定窗口切换事件
    document.getElementById('windowSelect').addEventListener('change', onWindowChange);
});

// 加载食堂
async function loadCanteens() {
    try {
        const res = await fetchApi(API.CANTEENS);
        if (res.code === 200) {
            canteens = res.data;
            const select = document.getElementById('canteenSelect');
            select.innerHTML = '<option value="">请选择食堂</option>';
            canteens.forEach(c => {
                select.innerHTML += `<option value="${c.id}">${c.name}</option>`;
            });
        }
    } catch (e) {
        console.error("加载食堂失败", e);
    }
}

// 加载菜品
async function loadDishes(windowId = null) {
    const container = document.getElementById('dishList');
    container.innerHTML = '<div class="text-muted small">加载中...</div>';
    
    let url = API.DISHES;
    if (windowId) {
        url += `?window_id=${windowId}`;
    }

    try {
        const res = await fetchApi(url);
        if (res.code === 200) {
            renderDishList(res.data);
        } else {
            container.innerHTML = '<div class="text-danger small">加载失败</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="text-danger small">网络错误</div>';
    }
}

function renderDishList(dishes) {
    const container = document.getElementById('dishList');
    container.innerHTML = '';
    
    if (dishes.length === 0) {
        container.innerHTML = '<div class="text-muted small">该窗口暂无推荐菜品</div>';
        return;
    }

    dishes.forEach((d, index) => {
        const html = `
            <input type="checkbox" class="dish-checkbox" id="dish_opt_${d.id}" value="${d.name}" data-id="${d.id}" onchange="toggleDish(this)">
            <label for="dish_opt_${d.id}" class="dish-label">${d.name}</label>
        `;
        container.innerHTML += html;
    });
}

// 食堂切换逻辑
async function onCanteenChange() {
    const canteenId = document.getElementById('canteenSelect').value;
    const windowSelect = document.getElementById('windowSelect');
    
    windowSelect.innerHTML = '<option value="">请先选择食堂</option>';
    windowSelect.disabled = true;

    if (canteenId) {
        // 加载窗口
        try {
            const res = await fetchApi(`${API.WINDOWS}?canteen_id=${canteenId}`);
            if (res.code === 200) {
                windowSelect.innerHTML = '<option value="">请选择窗口</option>';
                res.data.forEach(w => {
                    windowSelect.innerHTML += `<option value="${w.id}">${w.name}</option>`;
                });
                windowSelect.disabled = false;
            }
        } catch (e) {
            console.error(e);
        }
    }
}

// 窗口切换逻辑 - 加载该窗口菜品
function onWindowChange() {
    const windowId = document.getElementById('windowSelect').value;
    if (windowId) {
        loadDishes(windowId);
    } else {
        loadDishes(); // Load all or clear
    }
}

// 身份切换逻辑
function onIdentityChange() {
    const identity = document.getElementById('userIdentity').value;
    const studentSection = document.getElementById('studentInfoSection');
    
    if (identity === 'student') {
        studentSection.style.display = 'block';
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

// 菜品选择逻辑 (复选框)
function toggleDish(checkbox) {
    const dishName = checkbox.value;
    const dishId = checkbox.dataset.id; // Get ID
    
    if (checkbox.checked) {
        addDishToRating(dishName, null, dishId);
    } else {
        removeDishFromRating(dishName);
    }
}

// 自定义添加菜品
function addCustomDish() {
    const input = document.getElementById('customDishName');
    const name = input.value.trim();
    if (!name) return alert("请输入菜品名称");
    
    addDishToRating(name, null, 0); // 0 for custom
    input.value = ''; 
}

// 图片预览
function previewDishImg(input) {
    const file = input.files[0];
    const previewArea = document.getElementById('imgPreviewArea');
    const img = previewArea.querySelector('img');
    const tip = document.getElementById('imgUploadTip');
    
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            img.src = e.target.result;
            previewArea.classList.remove('d-none');
            tip.innerText = file.name;
            
            // 如果已输入名称，自动添加带图片的菜品
            const nameInput = document.getElementById('customDishName');
            if (nameInput.value.trim()) {
                addCustomDish(); 
            }
        };
        reader.readAsDataURL(file);
    }
}

// 核心：添加菜品到评分区
function addDishToRating(dishName, imgSrc = null, dishId = 0) {
    if (selectedDishes.some(d => d.name === dishName)) {
        alert("该菜品已在评价列表中");
        return;
    }
    if (selectedDishes.length >= 5) {
        alert("最多选择5个菜品");
        const checkbox = document.querySelector(`.dish-checkbox[value="${dishName}"]`);
        if (checkbox) checkbox.checked = false;
        return;
    }
    
    selectedDishes.push({ name: dishName, id: dishId });
    addFoodRatingCard(dishName, imgSrc);
}

// 核心：从评分区移除
function removeDishFromRating(dishName) {
    selectedDishes = selectedDishes.filter(d => d.name !== dishName);
    const card = document.getElementById(`card_${dishName}`);
    if (card) card.remove();
    
    const checkbox = document.querySelector(`.dish-checkbox[value="${dishName}"]`);
    if (checkbox) checkbox.checked = false;
}

// 动态生成食品评分卡片
function addFoodRatingCard(dishName, imgSrc) {
    const container = document.getElementById('foodRatingContainer');
    
    let imgHtml = '';
    if (imgSrc) { 
        imgHtml = `<img src="${imgSrc}" class="dish-img-preview">`;
    } else {
        const previewImg = document.querySelector('#imgPreviewArea img');
        if (!document.getElementById('imgPreviewArea').classList.contains('d-none') && previewImg.src) {
             imgHtml = `<img src="${previewImg.src}" class="dish-img-preview">`;
             document.getElementById('imgPreviewArea').classList.add('d-none');
             document.getElementById('dishImgUpload').value = '';
             document.getElementById('imgUploadTip').innerText = '未选择图片';
        }
    }

    const html = `
        <div class="eval-card active" id="card_${dishName}">
            <div class="dish-header">
                <div class="dish-info">
                    ${imgHtml}
                    <div>
                        <div class="dish-name-title">${dishName}</div>
                        <div class="mt-1">
                            <span class="badge bg-secondary">食品评价</span>
                            <span class="dish-score-badge">总分: <span id="total_${dishName}">0.0</span></span>
                        </div>
                    </div>
                </div>
                <i class="bi bi-trash delete-dish-btn" onclick="removeDishFromRating('${dishName}')"></i>
            </div>
            
            <div class="row">
                ${generateRangeHTML(dishName, 'taste', '口味')}
                ${generateRangeHTML(dishName, 'color', '色泽')}
                ${generateRangeHTML(dishName, 'appearance', '品相')}
                ${generateRangeHTML(dishName, 'price', '价格合理性')}
                ${generateRangeHTML(dishName, 'portion', '分量')}
                ${generateRangeHTML(dishName, 'speed', '出餐速度')}
            </div>
            <div class="mt-3">
                <textarea class="form-control auto-height-textarea" placeholder="请详细描述你的体验" name="comment"></textarea>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
}

function generateRangeHTML(dishName, key, label) {
    const safeName = dishName.replace(/\s+/g, '');
    const uniqueId = `val_${safeName}_${key}`;
    
    return `
        <div class="col-6 range-wrap">
            <div class="range-label">
                <span>${label}</span>
                <span class="score-value" id="${uniqueId}">0</span>
            </div>
            <input type="range" class="custom-range" min="0" max="10" value="0" 
                data-key="${key}" 
                oninput="updateDishScore(this, '${uniqueId}', '${dishName}')">
        </div>
    `;
}

function updateDishScore(input, valId, dishName) {
    document.getElementById(valId).innerText = input.value;
    
    const card = document.getElementById(`card_${dishName}`);
    const ranges = card.querySelectorAll('input[type="range"]');
    let sum = 0;
    let count = 0;
    
    ranges.forEach(r => {
        const val = parseInt(r.value);
        if (val > 0) {
            sum += val;
            count++;
        }
    });
    
    const avg = count > 0 ? (sum / count).toFixed(1) : "0.0";
    document.getElementById(`total_${dishName}`).innerText = avg;
}

// 提交逻辑
async function submitForm() {
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.innerText = "提交中...";

    try {
        const userStr = localStorage.getItem('user');
        const user = userStr ? JSON.parse(userStr) : null;
        
        if (!user) {
            alert("登录已失效，请重新登录");
            location.href = 'login.html';
            return;
        }

        const data = {
            user_id: user.id, 
            buy_time: document.getElementById('purchaseTime').value,
            canteen_id: document.getElementById('canteenSelect').value,
            window_id: document.getElementById('windowSelect').value,
            identity_type: document.getElementById('userIdentity').value,
            grade: document.getElementById('studentGrade').value,
            age: document.getElementById('studentAge').value,
            dining_years: document.getElementById('diningYears').value,
            
            env_scores: {
                comfort: document.getElementById('env_comfort').value,
                temp: document.getElementById('env_temp').value,
                layout: document.getElementById('env_layout').value,
                comment: document.getElementById('env_comment').value
            },
            
            service_scores: {
                attire: document.getElementById('svc_attire').value,
                attitude: document.getElementById('svc_attitude').value,
                hygiene: document.getElementById('svc_hygiene').value,
                comment: document.getElementById('svc_comment').value,
                personnel: getCheckedValues('svc_personnel')
            },
            
            dishes: []
        };

        selectedDishes.forEach(dish => {
            const card = document.getElementById(`card_${dish.name}`);
            if (card) {
                const dishData = {
                    dish_id: dish.id,
                    dish_name: dish.name,
                    remark: card.querySelector('textarea[name="comment"]').value,
                    food_scores: {}
                };
                
                card.querySelectorAll('input[type="range"]').forEach(input => {
                    dishData.food_scores[input.dataset.key] = input.value;
                });
                
                data.dishes.push(dishData);
            }
        });

        const res = await fetchApi(API.SUBMIT_EVALUATION, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (res.code === 200) {
            alert("评价提交成功！");
            location.href = 'index.html'; 
        } else {
            alert("提交失败：" + (res.msg || "未知错误"));
        }
        
    } catch (e) {
        console.error(e);
        alert("系统错误: " + e.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerText = "提交评价";
    }
}

function getCheckedValues(name) {
    const checkboxes = document.querySelectorAll(`input[name="${name}"]:checked`);
    return Array.from(checkboxes).map(cb => cb.value);
}
