const state = {
    range: 'today'
};

const charts = {
    trend: null,
    topDishes: null,
    peakTime: null
};

document.addEventListener('DOMContentLoaded', () => {
    bindTimeSwitch();
    initCharts();
    loadDashboard();

    window.addEventListener('resize', () => {
        if (charts.trend) charts.trend.resize();
        if (charts.topDishes) charts.topDishes.resize();
        if (charts.peakTime) charts.peakTime.resize();
    });
});

function bindTimeSwitch() {
    const buttons = document.querySelectorAll('#timeSwitch .time-pill');
    buttons.forEach((btn) => {
        btn.addEventListener('click', async () => {
            const range = btn.dataset.range;
            if (!range || range === state.range) return;
            state.range = range;
            buttons.forEach((item) => item.classList.remove('active'));
            btn.classList.add('active');
            await loadDashboard();
        });
    });
}

function initCharts() {
    if (typeof echarts === 'undefined') {
        showToast('图表库加载失败，请刷新页面重试');
        return;
    }

    charts.trend = echarts.init(document.getElementById('trendChart'));
    charts.topDishes = echarts.init(document.getElementById('topDishesChart'));
    charts.peakTime = echarts.init(document.getElementById('peakTimeChart'));
}

async function loadDashboard() {
    showLoading(true);
    const q = `range=${encodeURIComponent(state.range)}`;

    try {
        const [dashboardRes, trendRes, topRes, peakRes] = await Promise.all([
            fetchApi(`${API_BASE_URL}/public/dashboard?${q}`),
            fetchApi(`${API_BASE_URL}/public/trend?${q}`),
            fetchApi(`${API_BASE_URL}/public/top-dishes?${q}`),
            fetchApi(`${API_BASE_URL}/public/peak-time?${q}`)
        ]);

        if (dashboardRes.code !== 200) throw new Error(dashboardRes.msg || '看板概览加载失败');
        if (trendRes.code !== 200) throw new Error(trendRes.msg || '趋势数据加载失败');
        if (topRes.code !== 200) throw new Error(topRes.msg || '菜品排行加载失败');
        if (peakRes.code !== 200) throw new Error(peakRes.msg || '高峰时段加载失败');

        renderOverview(dashboardRes.data || {});
        renderRankingList((dashboardRes.data && dashboardRes.data.canteen_ranking) || []);
        renderTrendChart(trendRes.data || {});
        renderTopDishesChart((topRes.data && topRes.data.list) || []);
        renderPeakTimeChart((peakRes.data && peakRes.data.list) || []);

        if (dashboardRes.data && dashboardRes.data.seeded) {
            showToast('系统检测到空数据，已自动生成演示数据');
        }
    } catch (error) {
        console.error(error);
        showToast(error.message || '数据加载失败，请稍后重试');
    } finally {
        showLoading(false);
    }
}

function renderOverview(data) {
    setText('totalVisits', formatNumber(data.total_visits));
    setText('avgScore', Number(data.avg_score || 0).toFixed(1));
    setText('badReviewCount', formatNumber(data.bad_review_count));
    setText('activeDishCount', formatNumber(data.active_dish_count));
    setText('updateTime', data.update_time || nowString());

    const safetyLink = document.getElementById('safetyLink');
    if (data.safety_notice_url) {
        safetyLink.setAttribute('href', data.safety_notice_url);
    }
}

function renderRankingList(list) {
    const container = document.getElementById('canteenRankingList');
    if (!Array.isArray(list) || list.length === 0) {
        container.innerHTML = '<div class="empty-inline">暂无排行数据</div>';
        return;
    }

    container.innerHTML = list
        .map((item, index) => {
            const name = escapeHtml(item.canteen_name || '未命名食堂');
            const score = Number(item.avg_score || 0).toFixed(1);
            const count = formatNumber(item.eval_count || 0);
            return `
                <div class="ranking-item">
                    <span class="rank-no">${index + 1}</span>
                    <div class="rank-name" title="${name}">${name}</div>
                    <div class="rank-meta">${score} 分 / ${count} 条</div>
                </div>
            `;
        })
        .join('');
}

function renderTrendChart(data) {
    if (!charts.trend) return;

    const labels = Array.isArray(data.labels) ? data.labels : [];
    const values = Array.isArray(data.values) ? data.values : [];

    setText('trendRangeLabel', trendRangeText(state.range));

    charts.trend.setOption({
        grid: { top: 28, right: 14, bottom: 28, left: 36 },
        tooltip: { trigger: 'axis' },
        xAxis: {
            type: 'category',
            data: labels,
            axisLabel: { color: '#7f7f7f' },
            axisLine: { lineStyle: { color: '#e7e7e7' } }
        },
        yAxis: {
            type: 'value',
            axisLabel: { color: '#7f7f7f' },
            splitLine: { lineStyle: { color: '#f1f1f1' } }
        },
        series: [
            {
                type: 'line',
                data: values,
                smooth: true,
                symbol: 'circle',
                symbolSize: 6,
                lineStyle: { width: 3, color: '#ff7f24' },
                itemStyle: { color: '#ff7f24' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(255,127,36,0.35)' },
                        { offset: 1, color: 'rgba(255,127,36,0.03)' }
                    ])
                }
            }
        ]
    });
}

function renderTopDishesChart(list) {
    if (!charts.topDishes) return;

    const safeList = Array.isArray(list) ? list : [];
    const names = safeList.map((item) => item.name || '未命名菜品').slice(0, 10).reverse();
    const values = safeList.map((item) => Number(item.value || 0)).slice(0, 10).reverse();

    charts.topDishes.setOption({
        grid: { top: 8, right: 26, bottom: 10, left: 10, containLabel: true },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        xAxis: {
            type: 'value',
            splitLine: { lineStyle: { color: '#f2f2f2' } },
            axisLabel: { color: '#7f7f7f' }
        },
        yAxis: {
            type: 'category',
            data: names,
            axisLabel: {
                color: '#666',
                width: 110,
                overflow: 'truncate'
            },
            axisLine: { show: false },
            axisTick: { show: false }
        },
        series: [
            {
                type: 'bar',
                data: values,
                barWidth: '58%',
                itemStyle: {
                    color: '#ff9f5e',
                    borderRadius: [0, 8, 8, 0]
                },
                label: {
                    show: true,
                    position: 'right',
                    color: '#8f8f8f'
                }
            }
        ]
    });
}

function renderPeakTimeChart(list) {
    if (!charts.peakTime) return;

    const safeList = Array.isArray(list) ? list : [];
    const total = safeList.reduce((sum, item) => sum + Number(item.value || 0), 0);

    charts.peakTime.setOption({
        tooltip: {
            trigger: 'item',
            formatter: (params) => {
                const value = Number(params.value || 0);
                const pct = total > 0 ? ((value * 100) / total).toFixed(1) : '0.0';
                return `${params.name}<br/>${value} 人次 (${pct}%)`;
            }
        },
        legend: {
            bottom: 0,
            left: 'center',
            textStyle: { color: '#777', fontSize: 11 }
        },
        series: [
            {
                type: 'pie',
                radius: ['42%', '68%'],
                center: ['50%', '45%'],
                itemStyle: {
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    formatter: '{b}\n{d}%',
                    fontSize: 11,
                    color: '#666'
                },
                data: safeList.map((item) => ({
                    name: item.name || '-',
                    value: Number(item.value || 0)
                }))
            }
        ],
        color: ['#ff7f24', '#ff9f5e', '#ffc083', '#ffd7ad', '#ffe7cc', '#f59e66']
    });
}

function showLoading(show) {
    const mask = document.getElementById('loadingMask');
    if (!mask) return;
    if (show) {
        mask.classList.add('show');
    } else {
        mask.classList.remove('show');
    }
}

function showToast(message) {
    const wrap = document.getElementById('toastWrap');
    if (!wrap) return;

    const node = document.createElement('div');
    node.className = 'toast-item';
    node.textContent = message;
    wrap.appendChild(node);

    setTimeout(() => {
        node.remove();
    }, 2400);
}

function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
}

function formatNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0';
}

function trendRangeText(range) {
    if (range === 'today') return '今日按小时';
    if (range === 'week') return '近7天按天';
    return '近30天按天';
}

function nowString() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
