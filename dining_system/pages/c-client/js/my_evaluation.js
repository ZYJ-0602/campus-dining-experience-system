// js/my_evaluation.js

document.addEventListener('DOMContentLoaded', function() {
    loadEvaluations();
});

async function loadEvaluations() {
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        alert("请先登录");
        location.href = '/login';
        return;
    }
    const user = JSON.parse(userStr);

    try {
        const res = await fetchApi(API.MY_EVALUATIONS);
        
        document.getElementById('loading').classList.add('d-none');
        
        if (res.code === 200 && res.data && res.data.length > 0) {
            renderEvaluations(res.data);
        } else {
            document.getElementById('empty-state').classList.remove('d-none');
        }
    } catch (error) {
        console.error('加载失败:', error);
        document.getElementById('loading').innerHTML = '<p class="text-danger text-center">无法连接到服务器</p>';
    }
}

function renderEvaluations(list) {
    const container = document.getElementById('eval-list');
    let html = '';
    
    list.forEach((item, index) => {
        const collapseId = `collapse${index}`;
        const headingId = `heading${index}`;
        
        // 构建菜品名称字符串
        const dishNames = item.dishes.map(d => d.dish_name).join(', ');
        
        // 构建详细评分HTML
        let detailsHtml = '<div class="row g-3">';
        
        // 环境评分
        if (item.env_scores && Object.keys(item.env_scores).length > 0) {
            detailsHtml += `
                <div class="col-md-6">
                    <h6 class="text-primary-custom small fw-bold">环境评分</h6>
                    <ul class="list-group list-group-flush small">
                        ${Object.entries(item.env_scores).map(([k, v]) => 
                            v ? `<li class="list-group-item d-flex justify-content-between align-items-center px-0 py-1 bg-transparent">
                                <span>${translateKey(k)}</span> <span class="badge bg-warning text-dark rounded-pill">${v}</span>
                            </li>` : ''
                        ).join('')}
                    </ul>
                </div>`;
        }
        
        // 服务评分
        if (item.service_scores && Object.keys(item.service_scores).length > 0) {
            detailsHtml += `
                <div class="col-md-6">
                    <h6 class="text-primary-custom small fw-bold">服务评分</h6>
                    <ul class="list-group list-group-flush small">
                        ${Object.entries(item.service_scores).map(([k, v]) => 
                            (v && k!=='personnel') ? `<li class="list-group-item d-flex justify-content-between align-items-center px-0 py-1 bg-transparent">
                                <span>${translateKey(k)}</span> <span class="badge bg-warning text-dark rounded-pill">${v}</span>
                            </li>` : ''
                        ).join('')}
                    </ul>
                </div>`;
        }
        
        // 菜品评分
        if (item.dishes && item.dishes.length > 0) {
            detailsHtml += '<div class="col-12 mt-3"><h6 class="text-primary-custom small fw-bold">菜品评分</h6>';
            item.dishes.forEach(d => {
                if (d.food_scores) {
                    detailsHtml += `
                        <div class="mb-2 p-2 bg-white border rounded">
                            <div class="fw-bold text-dark mb-1">${d.dish_name}</div>
                            <div class="d-flex flex-wrap gap-2">
                                ${Object.entries(d.food_scores).map(([k, v]) => 
                                    `<span class="badge bg-light text-secondary border fw-normal">${translateKey(k)}: <b class="text-warning">${v}</b></span>`
                                ).join('')}
                            </div>
                            ${d.remark ? `<div class="small text-muted mt-1">备注: ${d.remark}</div>` : ''}
                        </div>`;
                }
            });
            detailsHtml += '</div>';
        }
        
        detailsHtml += '</div>';

        html += `
            <div class="accordion-item">
                <h2 class="accordion-header" id="${headingId}">
                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                        <div class="d-flex flex-column w-100">
                            <div class="d-flex justify-content-between align-items-center me-3">
                                <span class="fw-bold text-dark">${item.canteen_name} - ${item.window_name}</span>
                                <small class="text-muted" style="font-size: 0.8rem">${item.buy_time.split(' ')[0]}</small>
                            </div>
                            <div class="text-muted small text-truncate mt-1 pe-3">
                                ${dishNames || '无菜品信息'}
                            </div>
                        </div>
                    </button>
                </h2>
                <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#accordionExample">
                    <div class="accordion-body bg-light">
                        <p class="small text-muted mb-2">提交时间: ${item.create_time}</p>
                        ${detailsHtml}
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// 简单的键名翻译
function translateKey(key) {
    const map = {
        'comfort': '整体舒适度', 'temp': '温湿度', 'layout': '桌椅整洁', 'comment': '备注',
        'attire': '着装', 'attitude': '态度', 'hygiene': '卫生',
        'taste': '口味', 'color': '色泽', 'appearance': '品相', 'price': '价格', 'portion': '分量', 'speed': '速度'
    };
    return map[key] || key;
}
