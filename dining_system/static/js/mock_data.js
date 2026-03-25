/**
 * mock_data.js - 校园食堂点评系统模拟数据源
 * 包含：食堂/窗口/菜品基础数据、评价/笔记内容、运营统计数据
 * 用途：前端页面在无后端接口时的演示填充
 */

// ==========================================
// 1. 基础数据 (Base Data)
// ==========================================

// 食堂列表
const mockCanteenData = [
    {
        id: 1,
        name: "北区食堂",
        location: "校园北区生活区",
        time: "06:30-21:00",
        score: { food: 8.8, env: 8.5, service: 8.2, safety: 9.0 },
        desc: "主打大众餐饮，价格实惠，二楼设有特色风味区。",
        img: "../../static/img/canteen-north.jpg",
        tags: ["大众实惠", "早餐丰富"]
    },
    {
        id: 2,
        name: "南区食堂",
        location: "校园南区教学区旁",
        time: "07:00-22:00",
        score: { food: 9.2, env: 9.0, service: 8.8, safety: 9.5 },
        desc: "环境优美，网红档口聚集地，适合聚餐。",
        img: "../../static/img/canteen-south.jpg",
        tags: ["网红打卡", "环境优美"]
    },
    {
        id: 3,
        name: "西区食堂",
        location: "西区宿舍楼下",
        time: "06:30-20:00",
        score: { food: 8.5, env: 8.0, service: 8.0, safety: 8.8 },
        desc: "提供清真窗口和特色面食，深夜食堂首选。",
        img: "../../static/img/canteen-west.jpg",
        tags: ["特色面食", "清真"]
    }
];

// 窗口数据 (每个食堂3个)
const mockWindowData = [
    { id: 101, canteenId: 1, name: "1号自选快餐", floor: 1, category: "快餐" },
    { id: 102, canteenId: 1, name: "2号特色面馆", floor: 1, category: "面食" },
    { id: 103, canteenId: 1, name: "3号麻辣香锅", floor: 2, category: "风味" },
    { id: 201, canteenId: 2, name: "1号网红盖饭", floor: 1, category: "盖饭" },
    { id: 202, canteenId: 2, name: "2号铁板烧", floor: 2, category: "铁板" },
    { id: 203, canteenId: 2, name: "3号轻食沙拉", floor: 2, category: "轻食" },
    { id: 301, canteenId: 3, name: "1号兰州拉面", floor: 1, category: "清真" },
    { id: 302, canteenId: 3, name: "2号水饺", floor: 1, category: "面食" },
    { id: 303, canteenId: 3, name: "3号炸鸡汉堡", floor: 1, category: "西式" }
];

// 菜品数据 (每个窗口5个)
const mockDishData = [
    // 北区食堂菜品
    { id: 1001, windowId: 101, name: "番茄炒蛋", price: 5.0, score: 9.2, sales: 1200, img: "https://via.placeholder.com/300x200?text=Tomato+Egg" },
    { id: 1002, windowId: 101, name: "红烧肉", price: 12.0, score: 8.8, sales: 800, img: "https://via.placeholder.com/300x200?text=Pork" },
    { id: 1003, windowId: 101, name: "酸辣土豆丝", price: 4.0, score: 8.5, sales: 1500, img: "https://via.placeholder.com/300x200?text=Potato" },
    { id: 1004, windowId: 102, name: "牛肉面", price: 15.0, score: 9.0, sales: 600, img: "https://via.placeholder.com/300x200?text=Beef+Noodle" },
    { id: 1005, windowId: 103, name: "麻辣香锅(荤)", price: 25.0, score: 9.5, sales: 400, img: "https://via.placeholder.com/300x200?text=Spicy+Pot" },
    // 南区食堂菜品
    { id: 2001, windowId: 201, name: "黑椒牛柳盖饭", price: 18.0, score: 9.3, sales: 900, img: "https://via.placeholder.com/300x200?text=Beef+Rice" },
    { id: 2002, windowId: 202, name: "铁板鱿鱼", price: 20.0, score: 8.9, sales: 500, img: "https://via.placeholder.com/300x200?text=Squid" },
    // ...更多菜品按需生成
];

// ==========================================
// 2. 交互数据 (Interaction Data)
// ==========================================

// 评价数据
const mockEvaluationData = [
    { id: 1, dishId: 1001, user: "小明", avatar: "user1", score: 9.0, tags: ["口感绝佳", "分量足"], content: "今天的番茄炒蛋特别好吃，酸甜适中！", time: "2024-05-01 12:30", type: "food" },
    { id: 2, dishId: 1001, user: "张三", avatar: "user2", score: 8.0, tags: ["食材新鲜"], content: "味道不错，就是稍微有点咸。", time: "2024-04-30 18:15", type: "food" },
    { id: 3, dishId: 1002, user: "李四", avatar: "user3", score: 10.0, tags: ["服务热情"], content: "阿姨打菜手不抖，好评！", time: "2024-04-29 12:00", type: "service" },
    { id: 4, dishId: 2001, user: "王五", avatar: "user4", score: 7.0, tags: ["环境一般"], content: "桌子有点油，希望改进。", time: "2024-04-28 12:45", type: "env" },
    { id: 5, dishId: 1001, user: "赵六", avatar: "user5", score: 9.5, tags: ["性价比高"], content: "这个价格能吃到这么多肉，很良心。", time: "2024-04-27 18:00", type: "food" }
];

// 笔记数据
const mockPostData = [
    { 
        id: 1, 
        title: "北区食堂这道菜绝了！", 
        content: "番茄炒蛋真的太好吃了，强烈推荐给大家！阿姨手也不抖，分量很足。一定要点微辣！里面的宽粉和鱼豆腐巨好吃，分量也很足，两个人吃大概40块钱。\n避雷提示：饭点的排队人超多，建议错峰去。", 
        author: "小明", 
        avatar: "user1", 
        likes: 128, 
        img: "https://via.placeholder.com/600x400/FFE4B5/333?text=Tomato+Egg", 
        images: [
            "https://via.placeholder.com/600x400/FFE4B5/333?text=Tomato+Egg",
            "https://via.placeholder.com/600x400/E6E6FA/333?text=Environment",
            "https://via.placeholder.com/600x400/FFC0CB/333?text=Menu"
        ],
        status: "passed",
        tags: ["推荐", "北区食堂", "番茄炒蛋"],
        canteen: "北区食堂",
        window: "1号窗口",
        dish: "番茄炒蛋",
        time: "2024-05-01 12:30",
        comment_count: 5,
        is_liked: false,
        is_starred: false
    },
    { 
        id: 2, 
        title: "南区二楼避雷", 
        content: "这个菜有点不新鲜，吃了肚子不舒服，大家注意避雷。肉质很柴，感觉是复热的。", 
        author: "张三", 
        avatar: "user2", 
        likes: 45, 
        img: "https://via.placeholder.com/600x400/87CEEB/333?text=Bad+Food", 
        images: ["https://via.placeholder.com/600x400/87CEEB/333?text=Bad+Food"],
        status: "passed",
        tags: ["避雷", "南区食堂"],
        canteen: "南区食堂",
        window: "2号窗口",
        dish: "未知菜品",
        time: "2024-04-30 18:15",
        comment_count: 2,
        is_liked: false,
        is_starred: false
    },
    { 
        id: 3, 
        title: "西区麻辣烫yyds", 
        content: "味道正宗，价格实惠，就是排队的人有点多。推荐加辣油，非常香！", 
        author: "李四", 
        avatar: "user3", 
        likes: 230, 
        img: "https://via.placeholder.com/600x400/90EE90/333?text=Spicy+Hot+Pot", 
        images: ["https://via.placeholder.com/600x400/90EE90/333?text=Spicy+Hot+Pot"],
        status: "passed",
        tags: ["推荐", "西区食堂", "麻辣烫"],
        canteen: "西区食堂",
        window: "3号窗口",
        dish: "麻辣烫",
        time: "2024-04-29 12:00",
        comment_count: 8,
        is_liked: true,
        is_starred: true
    },
    { id: 4, title: "关于食堂卫生的建议", content: "希望能加强餐具消毒，发现有残留油渍。", author: "王五", avatar: "user4", likes: 12, img: "", images: [], status: "pending", tags: ["建议", "卫生"], canteen: "全校", window: "-", dish: "-", time: "2024-04-28", comment_count: 0 }
];

// 食安公示数据
const mockSafetyData = [
    { id: 1, canteenId: 1, title: "2024年5月食材检测报告", type: "report", date: "2024-05-01", status: "valid" },
    { id: 2, canteenId: 1, title: "食品经营许可证", type: "cert", date: "2023-01-01", status: "valid" },
    { id: 3, canteenId: 1, title: "从业人员健康证公示", type: "health", date: "2024-01-01", status: "valid" },
    { id: 4, canteenId: 2, title: "餐具消毒检测记录", type: "report", date: "2024-04-30", status: "expired" }
];

// ==========================================
// 3. 运营数据 (Admin Dashboard)
// ==========================================

const mockAdminData = {
    // 顶部统计卡片
    stats: {
        todayEvals: 156,
        todayPosts: 23,
        pendingAudit: 5,
        avgScore: 8.9
    },
    // 评分趋势 (折线图数据)
    scoreTrend: {
        dates: ["5-1", "5-2", "5-3", "5-4", "5-5", "5-6", "5-7"],
        food: [8.5, 8.6, 8.8, 8.7, 8.9, 9.0, 8.8],
        service: [8.0, 8.2, 8.1, 8.3, 8.5, 8.4, 8.6],
        env: [7.5, 7.6, 7.8, 7.9, 8.0, 8.1, 8.2]
    },
    // 热门菜品 (柱状图数据)
    hotDishes: {
        names: ["番茄炒蛋", "红烧肉", "麻辣香锅", "牛肉面", "炸鸡"],
        sales: [1200, 950, 880, 760, 650]
    },
    // 差评分布 (饼图数据)
    badReviews: [
        { value: 45, name: "口味偏咸" },
        { value: 30, name: "出餐慢" },
        { value: 25, name: "分量少" },
        { value: 15, name: "服务态度" },
        { value: 10, name: "环境卫生" }
    ]
};

// ==========================================
// 4. 数据加载工具函数 (Loader)
// ==========================================

const MockLoader = {
    /**
     * 获取URL参数
     */
    getParam: function(name) {
        const reg = new RegExp("(^|&)" + name + "=([^&]*)(&|$)");
        const r = window.location.search.substr(1).match(reg);
        if (r != null) return decodeURIComponent(r[2]);
        return null;
    },

    /**
     * 加载菜品详情页数据
     * 适配页面：dish_detail.html
     */
    loadDishDetail: function() {
        const id = parseInt(this.getParam('id')) || 1001; // 默认加载ID 1001
        const dish = mockDishData.find(d => d.id === id) || mockDishData[0];
        
        // 填充基础信息
        document.querySelector('.dish-title').textContent = dish.name;
        document.querySelector('.dish-price').textContent = `¥${dish.price.toFixed(1)}`;
        document.querySelector('.dish-score').textContent = dish.score;
        document.querySelector('.dish-sales').textContent = `月售 ${dish.sales}+`;
        document.querySelector('.dish-img').src = dish.img;
        
        // 填充评价列表
        const evals = mockEvaluationData.filter(e => e.dishId === id);
        const evalContainer = document.querySelector('.eval-list');
        if (evalContainer) {
            evalContainer.innerHTML = evals.length ? evals.map(e => `
                <div class="eval-item border-bottom py-3">
                    <div class="d-flex justify-content-between mb-2">
                        <div class="d-flex align-items-center">
                            <img src="https://ui-avatars.com/api/?name=${e.avatar}&background=random" class="rounded-circle me-2" width="30">
                            <span class="fw-bold text-dark">${e.user}</span>
                        </div>
                        <span class="text-muted small">${e.time}</span>
                    </div>
                    <div class="mb-2">
                        <span class="text-warning me-2">${e.score}分</span>
                        ${e.tags.map(t => `<span class="badge bg-light text-dark me-1">${t}</span>`).join('')}
                    </div>
                    <p class="text-secondary mb-0">${e.content}</p>
                </div>
            `).join('') : '<div class="text-center py-4 text-muted">暂无评价</div>';
        }
    },

    /**
     * 加载食堂详情页数据
     * 适配页面：canteen_detail.html
     */
    loadCanteenDetail: function() {
        // 模拟根据名称加载，实际项目应用ID
        const name = this.getParam('name') || "北区食堂";
        const canteen = mockCanteenData.find(c => c.name === name) || mockCanteenData[0];
        
        // 填充信息
        document.querySelector('.canteen-name').textContent = canteen.name;
        document.querySelector('.canteen-location').textContent = canteen.location;
        document.querySelector('.canteen-time').textContent = `营业时间：${canteen.time}`;
        
        // 初始化雷达图 (需页面引入ECharts)
        if (typeof echarts !== 'undefined' && document.getElementById('radarChart')) {
            const chart = echarts.init(document.getElementById('radarChart'));
            chart.setOption({
                radar: {
                    indicator: [
                        { name: '口味', max: 10 },
                        { name: '环境', max: 10 },
                        { name: '服务', max: 10 },
                        { name: '食安', max: 10 }
                    ],
                    radius: '70%'
                },
                series: [{
                    type: 'radar',
                    data: [{
                        value: [canteen.score.food, canteen.score.env, canteen.score.service, canteen.score.safety],
                        name: '评分',
                        itemStyle: { color: '#FF7F24' },
                        areaStyle: { opacity: 0.3 }
                    }]
                }]
            });
        }
    },

    /**
     * 加载运营看板图表
     * 适配页面：admin_index.html
     */
    loadAdminCharts: function() {
        if (typeof echarts === 'undefined') return;

        // 1. 评分趋势图
        const trendDom = document.getElementById('trendChart');
        if (trendDom) {
            const trendChart = echarts.init(trendDom);
            trendChart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: ['口味', '服务', '环境'] },
                xAxis: { type: 'category', data: mockAdminData.scoreTrend.dates },
                yAxis: { type: 'value', min: 0, max: 10 },
                series: [
                    { name: '口味', type: 'line', data: mockAdminData.scoreTrend.food, smooth: true },
                    { name: '服务', type: 'line', data: mockAdminData.scoreTrend.service, smooth: true },
                    { name: '环境', type: 'line', data: mockAdminData.scoreTrend.env, smooth: true }
                ]
            });
        }

        // 2. 热门菜品图
        const hotDom = document.getElementById('hotDishChart');
        if (hotDom) {
            const hotChart = echarts.init(hotDom);
            hotChart.setOption({
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: mockAdminData.hotDishes.names },
                yAxis: { type: 'value' },
                series: [{
                    type: 'bar',
                    data: mockAdminData.hotDishes.sales,
                    itemStyle: { color: '#FF7F24' },
                    barWidth: '40%'
                }]
            });
        }
    },

    /**
     * 加载帖子详情页数据
     * 适配页面：post_detail.html
     */
    loadPostDetail: function() {
        const id = parseInt(this.getParam('id')) || 1;
        const post = mockPostData.find(p => p.id === id) || mockPostData[0];
        
        // 关键：将数据暴露给全局，以便 post_detail.html 的交互逻辑使用
        window.mockPost = post;
        
        // 渲染文本
        const titleEl = document.getElementById('postTitle');
        if (titleEl) titleEl.innerText = post.title;
        
        const contentEl = document.getElementById('postContent');
        if (contentEl) contentEl.innerText = post.content;
        
        const authorNameEl = document.getElementById('authorName');
        if (authorNameEl) authorNameEl.innerText = post.author;
        
        const timeEl = document.getElementById('postTime');
        if (timeEl) timeEl.innerText = post.time || "刚刚";
        
        const avatarEl = document.getElementById('authorAvatar');
        if (avatarEl) avatarEl.src = `https://ui-avatars.com/api/?name=${post.avatar}&background=random`;
        
        const locationEl = document.getElementById('locationText');
        if (locationEl && post.canteen) locationEl.innerText = `${post.canteen} - ${post.window || ''} - ${post.dish || ''}`;
        
        // 渲染图片
        const wrapper = document.getElementById('imgWrapper');
        if (wrapper && post.images && post.images.length > 0) {
            wrapper.innerHTML = ''; // 清空原有内容
            post.images.forEach(img => {
                const slide = document.createElement('div');
                slide.className = 'swiper-slide';
                slide.innerHTML = `<img src="${img}" onclick="showBigImg('${img}')">`;
                wrapper.appendChild(slide);
            });
            // 触发Swiper更新（如果有全局swiper实例）
            if (window.mySwiper) window.mySwiper.update();
        } else if (wrapper) {
            // 如果没有图片，显示占位或隐藏
            wrapper.innerHTML = '<div class="swiper-slide d-flex align-items-center justify-content-center bg-light text-muted">无图片</div>';
        }

        // 渲染标签
        const tagsDiv = document.getElementById('postTags');
        if (tagsDiv && post.tags) {
            tagsDiv.innerHTML = '';
            post.tags.forEach(tag => {
                tagsDiv.innerHTML += `<span class="tag-pill"># ${tag}</span>`;
            });
        }

        // 调用页面内的 updateInteractionUI 更新互动状态
        if (typeof updateInteractionUI === 'function') {
            updateInteractionUI();
        } else {
             // 如果页面没有定义 updateInteractionUI，手动更新DOM
            const likeCountEl = document.getElementById('likeCount');
            if (likeCountEl) likeCountEl.innerText = post.likes || 0;
            
            const commentCountEl = document.getElementById('commentCountHeader');
            if (commentCountEl) commentCountEl.innerText = post.comment_count || 0;
            
            const commentCountBarEl = document.getElementById('commentCountBar');
            if (commentCountBarEl) commentCountBarEl.innerText = post.comment_count || 0;
        }
        
        // 加载评论（如果页面有定义）
        if (typeof loadComments === 'function') {
            loadComments();
        }
    },

    /**
     * 自动初始化
     * 根据当前页面URL自动调用对应的加载函数
     */
    init: function() {
        const path = window.location.pathname;
        
        if (path.includes('dish_detail')) {
            this.loadDishDetail();
        } else if (path.includes('canteen_detail')) {
            this.loadCanteenDetail();
        } else if (path.includes('admin_index')) {
            this.loadAdminCharts();
        } else if (path.includes('post_detail')) {
            this.loadPostDetail();
        }
        
        console.log('Mock Data Loaded for:', path);
    }
};

// 页面加载完成后自动执行
document.addEventListener('DOMContentLoaded', function() {
    MockLoader.init();
});
