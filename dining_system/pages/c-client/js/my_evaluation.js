// js/my_evaluation.js

let evaluationCache = [];
let currentPage = 1;
let pageSize = 8;
let totalPages = 0;
let totalCount = 0;

document.addEventListener('DOMContentLoaded', function() {
    const filter = document.getElementById('statusFilter');
    if (filter) {
        filter.addEventListener('change', function() {
            currentPage = 1;
            loadEvaluations();
        });
    }
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            if (currentPage <= 1) return;
            currentPage -= 1;
            loadEvaluations();
        });
    }
    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            if (currentPage >= totalPages) return;
            currentPage += 1;
            loadEvaluations();
        });
    }
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
        const filter = document.getElementById('statusFilter');
        const mode = filter ? filter.value : 'all';
        const qs = new URLSearchParams({
            with_pagination: '1',
            page: String(currentPage),
            limit: String(pageSize),
        });
        if (mode === 'pending' || mode === 'handled') {
            qs.set('governance_status', mode);
        }
        const res = await fetchApi(`${API.MY_EVALUATIONS}?${qs.toString()}`);
        
        document.getElementById('loading').classList.add('d-none');
        
        if (res.code === 200 && res.data) {
            evaluationCache = Array.isArray(res.data.list) ? res.data.list : [];
            totalPages = Number(res.data.pages || 0);
            totalCount = Number(res.data.total || 0);
            applyFilterAndRender();
        } else {
            document.getElementById('empty-state').classList.remove('d-none');
            updatePaginationBar();
        }
    } catch (error) {
        console.error('加载失败:', error);
        document.getElementById('loading').innerHTML = '<p class="text-danger text-center">无法连接到服务器</p>';
    }
}

function applyFilterAndRender() {
    const list = evaluationCache.slice();

    if (list.length === 0) {
        document.getElementById('eval-list').innerHTML = '';
        document.getElementById('empty-state').classList.remove('d-none');
        updatePaginationBar();
        return;
    }
    document.getElementById('empty-state').classList.add('d-none');
    updatePaginationBar();
    renderEvaluations(list);
}

function updatePaginationBar() {
    const bar = document.getElementById('paginationBar');
    const info = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    if (!bar || !info || !prevBtn || !nextBtn) return;

    if (totalCount <= 0) {
        bar.classList.add('d-none');
        return;
    }

    bar.classList.remove('d-none');
    info.innerText = `第 ${currentPage}/${Math.max(totalPages, 1)} 页，共 ${totalCount} 条`;
    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
}

function governanceLabel(status) {
    if (status === 'pending') return '待处理';
    if (status === 'handled') return '已处理';
    return '正常';
}

function renderEvaluations(list) {
    const container = document.getElementById('eval-list');
    let html = '';
    
    list.forEach((item, index) => {
        const collapseId = `collapse${index}`;
        const headingId = `heading${index}`;
        const governanceClass = item.governance_status === 'handled'
            ? 'bg-success-subtle text-success'
            : (item.governance_status === 'pending' ? 'bg-warning-subtle text-warning' : 'bg-light text-secondary');
        const timeline = Array.isArray(item.governance_timeline) ? item.governance_timeline : [];
        
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

        const timelineHtml = timeline.length
            ? `<div class="mt-3">
                    <h6 class="text-primary-custom small fw-bold">处理进度时间线</h6>
                    <div class="timeline small">
                        ${timeline.map((node) => {
                            let dotClass = 'processing';
                            let badgeClass = 'bg-secondary-subtle text-secondary';
                            let statusText = '进行中';
                            if (node.status === 'done') {
                                dotClass = 'done';
                                badgeClass = 'bg-success-subtle text-success';
                                statusText = '已完成';
                            } else if (node.status === 'pending') {
                                dotClass = 'pending';
                                badgeClass = 'bg-warning-subtle text-warning';
                                statusText = '待处理';
                            }
                            if (node.type === 'rectification' && node.is_public) {
                                statusText = '已公示';
                            }

                            return `<div class="timeline-item">
                                <span class="timeline-dot ${dotClass}"></span>
                                <div class="d-flex justify-content-between align-items-center">
                                    <span>${node.title || '-'}</span>
                                    <span class="badge ${badgeClass}">${statusText}</span>
                                </div>
                                <div class="text-muted mt-1">${node.time || '-'}</div>
                            </div>`;
                        }).join('')}
                    </div>
               </div>`
            : '';

        const hasRectification = Array.isArray(item.rectifications) && item.rectifications.length > 0;
        const detailBtnHtml = hasRectification
            ? `<button class="btn btn-outline-primary btn-sm mt-2" onclick="showRectificationModal(${item.id})">查看整改详情</button>`
            : '';

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
                            <div class="mt-1">
                                <span class="badge ${governanceClass}">处理状态：${governanceLabel(item.governance_status)}</span>
                            </div>
                        </div>
                    </button>
                </h2>
                <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#accordionExample">
                    <div class="accordion-body bg-light">
                        <p class="small text-muted mb-2">提交时间: ${item.create_time}</p>
                        ${item.warning_id ? `<p class="small mb-2">预警单号: #${item.warning_id}，整改记录: ${Number(item.rectification_count || 0)} 条</p>` : ''}
                        ${item.latest_rectification_title ? `<p class="small mb-2">最近整改: ${item.latest_rectification_title}${item.latest_rectification_public ? '（已公示）' : '（未公示）'} ${item.latest_rectification_time ? `· ${item.latest_rectification_time}` : ''}</p>` : ''}
                        ${detailBtnHtml}
                        ${detailsHtml}
                        ${timelineHtml}
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

window.showRectificationModal = function(evaluationId) {
    const target = evaluationCache.find(item => Number(item.id) === Number(evaluationId));
    const list = target && Array.isArray(target.rectifications) ? target.rectifications : [];
    const body = document.getElementById('rectificationModalBody');
    if (!list.length) {
        body.innerHTML = '<div class="text-muted">暂无整改详情</div>';
    } else {
        body.innerHTML = list.map((row, idx) => {
            const imgHtml = Array.isArray(row.images) && row.images.length
                ? `<div class="mt-2 d-flex flex-wrap gap-2">${row.images.map((img) => `<a href="${img}" target="_blank"><img src="${img}" alt="整改附件" style="width:72px;height:72px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;"></a>`).join('')}</div>`
                : '';
            return `<div class="border rounded p-3 mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="m-0">${escapeHtml(row.title || '整改记录')}</h6>
                    <span class="badge ${row.is_public ? 'bg-success-subtle text-success' : 'bg-secondary-subtle text-secondary'}">${row.is_public ? '已公示' : '未公示'}</span>
                </div>
                <div class="small text-muted mb-2">更新时间：${escapeHtml(row.update_time || '-')}</div>
                <div class="small"><b>问题描述：</b>${escapeHtml(row.issue_desc || '-')}</div>
                <div class="small mt-1"><b>整改措施：</b>${escapeHtml(row.action_detail || '-')}</div>
                ${imgHtml}
            </div>`;
        }).join('');
    }
    const modal = new bootstrap.Modal(document.getElementById('rectificationModal'));
    modal.show();
};

function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, (m) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[m]));
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
