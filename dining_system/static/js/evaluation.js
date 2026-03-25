// 全局状态
let selectedDishes = [];

// 自动调整 textarea 高度
function initAutoResizeTextarea() {
    document.addEventListener('input', function (e) {
        if (e.target.classList.contains('auto-height-textarea')) {
            e.target.style.height = 'auto'; // 先重置高度以获取准确的scrollHeight
            e.target.style.height = (e.target.scrollHeight) + 'px'; // 设置为内容高度
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // 1. 加载菜品列表
    loadDishes();
    
    // 2. 初始化时间
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    const timeInput = document.getElementById('purchaseTime');
    if (timeInput) {
        timeInput.value = now.toISOString().slice(0, 16);
    }
    
    // 3. 初始化文本框自适应
    initAutoResizeTextarea();
});

// 加载菜品 (优先本地模拟，失败才请求接口)
async function loadDishes() {
    const container = document.getElementById('dishList');
    container.innerHTML = ''; // 清空加载中提示
    
    const mockDishes = [
        "番茄炒蛋", "红烧肉", "麻婆豆腐", "宫保鸡丁", 
        "清蒸鱼", "酸辣土豆丝", "青椒肉丝", "玉米排骨汤"
    ];

    try {
        // 尝试请求接口（如果后端已启动）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1000); // 1秒超时
        
        const res = await fetch('http://127.0.0.1:5000/api/dishes', { signal: controller.signal });
        clearTimeout(timeoutId);
        
        if (res.ok) {
            const dishes = await res.json();
            renderDishList(dishes.map(d => d.name));
            return;
        }
    } catch (e) {
        console.warn("后端接口连接失败，使用本地模拟数据");
    }

    // 降级使用模拟数据
    renderDishList(mockDishes);
}

function renderDishList(names) {
    const container = document.getElementById('dishList');
    names.forEach((name, index) => {
        const html = `
            <input type="checkbox" class="dish-checkbox" id="dish_opt_${index}" value="${name}" onchange="toggleDish(this)">
            <label for="dish_opt_${index}" class="dish-label">${name}</label>
        `;
        container.innerHTML += html;
    });
}

// 模拟食堂窗口数据
const mockCanteens = {
    "1": [ // 北区
        { id: "101", name: "1号自选快餐" },
        { id: "102", name: "2号特色面馆" },
        { id: "103", name: "3号麻辣香锅" }
    ],
    "2": [ // 南区
        { id: "201", name: "1号网红盖饭" },
        { id: "202", name: "2号铁板烧" }
    ],
    "3": [ // 西区
        { id: "301", name: "1号兰州拉面" },
        { id: "302", name: "2号水饺" }
    ]
};

// 食堂切换逻辑
function onCanteenChange() {
    const canteenId = document.getElementById('canteenSelect').value;
    const windowSelect = document.getElementById('windowSelect');
    
    // 重置窗口下拉框
    windowSelect.innerHTML = '<option value="">请先选择食堂</option>';
    windowSelect.disabled = true;

    if (canteenId && mockCanteens[canteenId]) {
        windowSelect.innerHTML = '<option value="">请选择窗口</option>';
        mockCanteens[canteenId].forEach(w => {
            windowSelect.innerHTML += `<option value="${w.id}">${w.name}</option>`;
        });
        windowSelect.disabled = false;
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
    
    if (checkbox.checked) {
        addDishToRating(dishName);
    } else {
        removeDishFromRating(dishName);
    }
}

// 自定义添加菜品
function addCustomDish() {
    const input = document.getElementById('customDishName');
    const name = input.value.trim();
    if (!name) return alert("请输入菜品名称");
    
    addDishToRating(name);
    input.value = ''; // 清空输入
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
                addCustomDish(); // 添加逻辑需改造以支持图片
            }
        };
        reader.readAsDataURL(file);
    }
}

// 核心：添加菜品到评分区
function addDishToRating(dishName, imgSrc = null) {
    if (selectedDishes.includes(dishName)) {
        alert("该菜品已在评价列表中");
        return;
    }
    if (selectedDishes.length >= 5) {
        alert("最多选择5个菜品");
        // 如果是checkbox触发的，取消勾选
        const checkbox = document.querySelector(`.dish-checkbox[value="${dishName}"]`);
        if (checkbox) checkbox.checked = false;
        return;
    }
    
    selectedDishes.push(dishName);
    addFoodRatingCard(dishName, imgSrc);
}

// 核心：从评分区移除
function removeDishFromRating(dishName) {
    selectedDishes = selectedDishes.filter(d => d !== dishName);
    const card = document.getElementById(`card_${dishName}`);
    if (card) card.remove();
    
    // 同步取消上方复选框
    const checkbox = document.querySelector(`.dish-checkbox[value="${dishName}"]`);
    if (checkbox) checkbox.checked = false;
}

// 动态生成食品评分卡片
function addFoodRatingCard(dishName, imgSrc) {
    const container = document.getElementById('foodRatingContainer');
    
    // 图片HTML
    let imgHtml = '';
    if (imgSrc) { // 暂未实现图片传递到此处，预留接口
        imgHtml = `<img src="${imgSrc}" class="dish-img-preview">`;
    } else {
        // 尝试从预览区获取图片（如果是自定义添加且有预览）
        const previewImg = document.querySelector('#imgPreviewArea img');
        if (!document.getElementById('imgPreviewArea').classList.contains('d-none') && previewImg.src) {
             imgHtml = `<img src="${previewImg.src}" class="dish-img-preview">`;
             // 重置预览区，防止下个菜品重复使用
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
                <textarea class="form-control auto-height-textarea" placeholder="请详细描述你的体验（如：口感不错，但分量偏少）" name="comment"></textarea>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
}

function generateRangeHTML(dishName, key, label) {
    // 移除空格作为ID
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

// 实时更新分数
function updateDishScore(input, valId, dishName) {
    // 1. 更新当前项显示
    document.getElementById(valId).innerText = input.value;
    
    // 2. 计算该菜品总分
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
        // 构造后端期望的 JSON 格式
        const data = {
            user_id: 1, // 硬编码，实际应从登录状态获取
            buy_time: document.getElementById('purchaseTime').value,
            canteen_id: document.getElementById('canteenSelect').value,
            window_id: document.getElementById('windowSelect').value,
            identity_type: document.getElementById('userIdentity').value,
            grade: document.getElementById('studentGrade').value,
            age: document.getElementById('studentAge').value,
            dining_years: document.getElementById('diningYears').value,
            
            // 环境评分 (归纳为 env_scores)
            env_scores: {
                comfort: document.getElementById('env_comfort').value,
                temp: document.getElementById('env_temp').value,
                layout: document.getElementById('env_layout').value,
                comment: document.getElementById('env_comment').value
            },
            
            // 服务评分 (归纳为 service_scores)
            service_scores: {
                attire: document.getElementById('svc_attire').value,
                attitude: document.getElementById('svc_attitude').value,
                hygiene: document.getElementById('svc_hygiene').value,
                comment: document.getElementById('svc_comment').value,
                personnel: getCheckedValues('svc_personnel') // 数组
            },
            
            dishes: []
        };

        selectedDishes.forEach(dishName => {
            const card = document.getElementById(`card_${dishName}`);
            if (card) {
                const dishData = {
                    dish_name: dishName, // 后端字段名: dish_name
                    remark: card.querySelector('textarea[name="comment"]').value, // 后端字段名: remark
                    food_scores: {} // 后端字段名: food_scores
                };
                
                // 收集菜品各项评分
                card.querySelectorAll('input[type="range"]').forEach(input => {
                    dishData.food_scores[input.dataset.key] = input.value;
                });
                
                data.dishes.push(dishData);
            }
        });

        console.log("Submitting data:", data);

        // 尝试提交
        try {
            const res = await fetch('http://127.0.0.1:5000/api/submit_evaluation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            if (res.ok) {
                alert("评价提交成功！");
                window.location.href = 'index.html'; 
            } else {
                const result = await res.json();
                alert("提交失败：" + (result.msg || "未知错误"));
            }
        } catch (netErr) {
             console.error("网络错误:", netErr);
             alert("无法连接到后端服务器，请检查服务是否启动 (localhost:5000)");
        }
        
    } catch (e) {
        console.error(e);
        alert("系统错误: " + e.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerText = "提交评价";
    }
}

// 辅助函数：获取复选框选中的值
function getCheckedValues(name) {
    const checkboxes = document.querySelectorAll(`input[name="${name}"]:checked`);
    return Array.from(checkboxes).map(cb => cb.value);
}
