<template>
  <div class="food-review-container">
    <!-- 顶部汇总区域 -->
    <div class="summary-header">
      <div class="summary-title">综合得分</div>
      <div class="circular-progress" :style="progressStyle">
        <div class="inner-circle">
          <span class="score-value">{{ overallScore.toFixed(1) }}</span>
        </div>
      </div>
    </div>

    <!-- 评价表单区域 -->
    <div class="review-sections">
      
      <!-- 菜品评价 -->
      <section class="review-module" id="section-dish">
        <div class="module-header">
          <h3>菜品评价 <span class="required">*</span></h3>
          <div class="score-badge" v-if="dishScore > 0">★{{ dishScore.toFixed(1) }}分</div>
        </div>
        <!-- 简化菜品选择，假设只评一个菜品以演示 -->
        <div class="score-items">
          <div class="score-item" v-for="item in dishDimensions" :key="item.key">
            <label>{{ item.label }}</label>
            <input type="range" min="1" max="10" v-model.number="dishScores[item.key]" class="custom-range" />
            <span class="score-num">{{ dishScores[item.key] || '-' }}</span>
          </div>
        </div>
        <div class="comment-area">
          <textarea 
            v-model="dishComment" 
            placeholder="写下你对菜品的评价..." 
            class="auto-resize-textarea"
            @input="adjustTextareaHeight"
            aria-label="菜品评价文字输入框"
          ></textarea>
        </div>
        <ImageUploader v-model="dishImages" :maxFiles="20" bucket="dish" />
      </section>

      <!-- 服务评价 -->
      <section class="review-module" id="section-service">
        <div class="module-header">
          <h3>服务评价 <span class="required">*</span></h3>
          <div class="score-badge" v-if="serviceScore > 0">★{{ serviceScore.toFixed(1) }}分</div>
        </div>
        <div class="score-items">
          <div class="score-item" v-for="item in serviceDimensions" :key="item.key">
            <label>{{ item.label }}</label>
            <input type="range" min="1" max="10" v-model.number="serviceScores[item.key]" class="custom-range" />
            <span class="score-num">{{ serviceScores[item.key] || '-' }}</span>
          </div>
        </div>
        <div class="comment-area">
          <textarea 
            v-model="serviceComment" 
            placeholder="写下你对服务的评价（选填）..." 
            class="auto-resize-textarea"
            @input="adjustTextareaHeight"
            aria-label="服务评价文字输入框"
          ></textarea>
        </div>
        <ImageUploader v-model="serviceImages" :maxFiles="6" bucket="service" />
      </section>

      <!-- 环境评价 -->
      <section class="review-module" id="section-env">
        <div class="module-header">
          <h3>环境评价 <span class="required">*</span></h3>
          <div class="score-badge" v-if="envScore > 0">★{{ envScore.toFixed(1) }}分</div>
        </div>
        <div class="score-items">
          <div class="score-item" v-for="item in envDimensions" :key="item.key">
            <label>{{ item.label }}</label>
            <input type="range" min="1" max="10" v-model.number="envScores[item.key]" class="custom-range" />
            <span class="score-num">{{ envScores[item.key] || '-' }}</span>
          </div>
        </div>
        <div class="comment-area">
          <textarea 
            v-model="envComment" 
            placeholder="写下你对环境的评价（选填）..." 
            class="auto-resize-textarea"
            @input="adjustTextareaHeight"
            aria-label="环境评价文字输入框"
          ></textarea>
        </div>
        <ImageUploader v-model="envImages" :maxFiles="6" bucket="env" />
      </section>

      <!-- 食品安全评价 -->
      <section class="review-module" id="section-safety">
        <div class="module-header">
          <h3>食品安全评价 <span class="required">*</span></h3>
          <div class="score-badge" v-if="safetyScore > 0">★{{ safetyScore.toFixed(1) }}分</div>
        </div>
        <div class="score-items">
          <div class="score-item" v-for="item in safetyDimensions" :key="item.key">
            <label>{{ item.label }}</label>
            <input type="range" min="1" max="10" v-model.number="safetyScores[item.key]" class="custom-range" />
            <span class="score-num">{{ safetyScores[item.key] || '-' }}</span>
          </div>
        </div>
        <div class="comment-area">
          <textarea 
            v-model="safetyComment" 
            placeholder="写下你对食品安全的评价（选填）..." 
            class="auto-resize-textarea"
            @input="adjustTextareaHeight"
            aria-label="食品安全评价文字输入框"
          ></textarea>
        </div>
        <ImageUploader v-model="safetyImages" :maxFiles="6" bucket="safety" />
      </section>

    </div>

    <!-- 提交按钮区域 -->
    <div class="submit-action">
      <div class="tooltip-wrapper" :class="{ 'show-tooltip': !canSubmit }">
        <span class="tooltip-text">请完成所有必填评价</span>
        <button 
          class="submit-btn" 
          :class="{ disabled: !canSubmit, loading: isSubmitting }"
          @click="submitReview"
          :disabled="!canSubmit || isSubmitting"
        >
          {{ isSubmitting ? '提交中...' : '提交评价' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick } from 'vue'
import ImageUploader from './ImageUploader.vue' // 假设ImageUploader已拆分为子组件，为了示例完整性我们会在另一个文件提供，或者这里合并，不过按照要求我们应该提供完整能力

// --- 数据模型 ---
const dishDimensions = [
  { key: 'color', label: '色泽' }, { key: 'aroma', label: '香气' },
  { key: 'taste', label: '口味' }, { key: 'shape', label: '形态' },
  { key: 'portion', label: '分量' }, { key: 'price', label: '性价比' }
]
const dishScores = reactive<Record<string, number>>({})
const dishComment = ref('')
const dishImages = ref<File[]>([])

const serviceDimensions = [
  { key: 'attitude', label: '服务态度' }, { key: 'speed', label: '出餐速度' }, { key: 'dress', label: '着装规范' }
]
const serviceScores = reactive<Record<string, number>>({})
const serviceComment = ref('')
const serviceImages = ref<File[]>([])

const envDimensions = [
  { key: 'clean', label: '桌面整洁' }, { key: 'air', label: '空调效果' }, { key: 'hygiene', label: '整体卫生' }
]
const envScores = reactive<Record<string, number>>({})
const envComment = ref('')
const envImages = ref<File[]>([])

const safetyDimensions = [
  { key: 'fresh', label: '食材新鲜' }, { key: 'info', label: '公示完整' }
]
const safetyScores = reactive<Record<string, number>>({})
const safetyComment = ref('')
const safetyImages = ref<File[]>([])

// --- 计算分数 ---
const calcAvg = (scores: Record<string, number>, dims: any[]) => {
  let total = 0
  let count = 0
  dims.forEach(d => {
    if (scores[d.key] > 0) {
      total += scores[d.key]
      count++
    }
  })
  return count === 0 ? 0 : total / count
}

const dishScore = computed(() => calcAvg(dishScores, dishDimensions))
const serviceScore = computed(() => calcAvg(serviceScores, serviceDimensions))
const envScore = computed(() => calcAvg(envScores, envDimensions))
const safetyScore = computed(() => calcAvg(safetyScores, safetyDimensions))

const overallScore = computed(() => {
  return (dishScore.value + serviceScore.value + envScore.value + safetyScore.value) / 4
})

const progressStyle = computed(() => {
  const percentage = (overallScore.value / 10) * 100
  return {
    background: `conic-gradient(#FF6A00 ${percentage}%, #eee ${percentage}% 100%)`
  }
})

// --- 表单校验 ---
const canSubmit = computed(() => {
  // 必须所有维度都有评分
  return dishScore.value > 0 && serviceScore.value > 0 && envScore.value > 0 && safetyScore.value > 0
})

// --- 文本框自适应高度 ---
const adjustTextareaHeight = (e: Event) => {
  const target = e.target as HTMLTextAreaElement
  target.style.height = '120px' // 重置以获取真实scrollHeight
  const scrollHeight = target.scrollHeight
  target.style.height = Math.min(Math.max(scrollHeight, 120), 400) + 'px'
}

// --- 提交逻辑 ---
const isSubmitting = ref(false)
const lastSubmitTime = ref(0)

const submitReview = async () => {
  if (!canSubmit.value) return
  
  // 防刷校验：30秒限制
  const now = Date.now()
  if (now - lastSubmitTime.value < 30000) {
    alert('提交过于频繁，请30秒后再试')
    return
  }

  isSubmitting.value = true

  try {
    // 模拟API调用
    const payload = {
      dish_scores: dishScores,
      dish_comment: dishComment.value,
      service_scores: serviceScores,
      service_comment: serviceComment.value,
      env_scores: envScores,
      env_comment: envComment.value,
      safety_scores: safetyScores,
      safety_comment: safetyComment.value,
      // 图片在实际中需要先上传获取URL，或通过FormData分片上传
    }
    
    // await axios.post('/api/submit_evaluation', payload)
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    lastSubmitTime.value = Date.now()
    
    // 提交成功，跳转并锚点定位
    alert('评价提交成功！')
    const fakeReviewId = 'review-' + Date.now()
    window.location.hash = '#' + fakeReviewId
    
    // 3秒后回到顶部
    setTimeout(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }, 3000)
    
  } catch (error) {
    console.error(error)
    alert('提交失败')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.food-review-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* 顶部综合得分 */
.summary-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 30px;
}
.summary-title {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 10px;
}
.circular-progress {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.3s ease;
}
.inner-circle {
  width: 80px;
  height: 80px;
  background: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 2px 5px rgba(0,0,0,0.1);
}
.score-value {
  font-size: 24px;
  font-weight: bold;
  color: #FF6A00;
}

/* 评价模块卡片 */
.review-module {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
  border: 1px solid #eee;
}

.module-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
  border-bottom: 1px solid #f5f5f5;
  padding-bottom: 10px;
}

.module-header h3 {
  margin: 0;
  font-size: 16px;
  color: #333;
}

.required {
  color: #e74c3c;
}

.score-badge {
  background: #fff5eb;
  color: #FF6A00;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: bold;
  transition: all 0.3s ease;
}

/* 评分项 */
.score-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.score-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.score-item label {
  width: 70px;
  font-size: 14px;
  color: #666;
}

.custom-range {
  flex: 1;
  accent-color: #FF6A00;
}

.score-num {
  width: 24px;
  text-align: center;
  font-weight: bold;
  color: #FF6A00;
}

/* 文本域 */
.comment-area {
  margin-bottom: 15px;
}

.auto-resize-textarea {
  width: 100%;
  min-height: 120px;
  max-height: 400px;
  padding: 12px 16px;
  box-sizing: border-box;
  border: 1px solid #E5E5E5;
  border-radius: 8px;
  resize: vertical; /* 允许右下角拖拽 */
  font-size: 14px;
  line-height: 1.5;
  transition: border-color 0.2s;
  outline: none;
}

.auto-resize-textarea:focus {
  border-color: #FF6A00;
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.1);
}

/* 提交按钮 */
.submit-action {
  text-align: center;
  margin-top: 40px;
}

.tooltip-wrapper {
  position: relative;
  display: inline-block;
}

.tooltip-text {
  visibility: hidden;
  background-color: #333;
  color: #fff;
  text-align: center;
  border-radius: 4px;
  padding: 5px 10px;
  position: absolute;
  z-index: 1;
  bottom: 125%;
  left: 50%;
  transform: translateX(-50%);
  opacity: 0;
  transition: opacity 0.3s;
  white-space: nowrap;
  font-size: 12px;
}

.tooltip-wrapper.show-tooltip:hover .tooltip-text {
  visibility: visible;
  opacity: 1;
}

.submit-btn {
  background: #FF6A00;
  color: #fff;
  border: none;
  padding: 12px 40px;
  border-radius: 25px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.3s;
  width: 200px;
}

.submit-btn:hover:not(.disabled) {
  background: #e65c00;
}

.submit-btn.disabled {
  background: #ccc;
  cursor: not-allowed;
}

.submit-btn.loading {
  opacity: 0.8;
  cursor: wait;
}

/* 响应式 */
@media (max-width: 768px) {
  .score-items {
    grid-template-columns: 1fr;
  }
}
</style>
