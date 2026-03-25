<template>
  <div class="image-uploader">
    <div class="uploader-header">
      <span class="label">图片上传</span>
      <span class="count">{{ files.length }} / {{ maxFiles }}</span>
    </div>
    
    <div class="upload-grid" @dragover.prevent @drop="handleDropSort">
      <!-- 已上传图片列表 -->
      <div 
        class="preview-item" 
        v-for="(file, index) in files" 
        :key="file.id"
        draggable="true"
        @dragstart="onDragStart($event, index)"
        @dragover.prevent="onDragOver($event, index)"
        @drop="onDrop($event, index)"
        @dragenter.prevent
      >
        <img :src="file.preview" alt="preview" />
        <button class="delete-btn" @click="removeFile(index)" aria-label="删除图片">×</button>
        <div class="status-overlay" v-if="file.status === 'uploading'">
          <div class="spinner"></div>
        </div>
        <div class="status-overlay error" v-if="file.status === 'error'">
          <span>失败</span>
          <button @click="retryUpload(index)">重试</button>
        </div>
      </div>

      <!-- 上传按钮 -->
      <label class="upload-trigger" v-if="files.length < maxFiles">
        <input 
          type="file" 
          accept="image/jpeg, image/webp, image/png" 
          multiple 
          @change="handleFileSelect" 
          hidden 
        />
        <div class="trigger-content">
          <span class="plus-icon">+</span>
          <span class="text">添加图片</span>
        </div>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  maxFiles: number
  bucket: string
  modelValue: any[]
}>()

const emit = defineEmits(['update:modelValue'])

interface UploadFile {
  id: string
  file: File
  preview: string
  status: 'pending' | 'uploading' | 'success' | 'error'
  retryCount: number
}

const files = ref<UploadFile[]>([])

watch(files, (newFiles) => {
  // 只将实际的文件对象传给父组件（实际业务中可能是传URL）
  emit('update:modelValue', newFiles.map(f => f.file))
}, { deep: true })

// 拖拽排序逻辑
let draggedIndex = -1

const onDragStart = (e: DragEvent, index: number) => {
  draggedIndex = index
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    // 必须设置data才能拖拽
    e.dataTransfer.setData('text/plain', index.toString())
  }
}

const onDragOver = (e: DragEvent, index: number) => {
  e.preventDefault()
}

const onDrop = (e: DragEvent, index: number) => {
  e.preventDefault()
  if (draggedIndex === -1 || draggedIndex === index) return
  
  const items = [...files.value]
  const [draggedItem] = items.splice(draggedIndex, 1)
  items.splice(index, 0, draggedItem)
  
  files.value = items
  draggedIndex = -1
}

const handleDropSort = (e: DragEvent) => {
  e.preventDefault()
  // 外部容器的 drop，防止默认打开图片
}

// 文件选择与压缩
const handleFileSelect = async (e: Event) => {
  const input = e.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  
  const newFiles = Array.from(input.files)
  
  // 检查数量
  if (files.value.length + newFiles.length > props.maxFiles) {
    alert(`最多只能上传 ${props.maxFiles} 张图片`)
    newFiles.splice(props.maxFiles - files.value.length)
  }

  for (const file of newFiles) {
    // 强制类型检查
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      alert('仅支持 jpeg, png, webp 格式')
      continue
    }

    try {
      const compressedFile = await compressImage(file)
      const preview = URL.createObjectURL(compressedFile)
      
      const uploadItem: UploadFile = {
        id: Math.random().toString(36).substring(2),
        file: compressedFile,
        preview,
        status: 'pending',
        retryCount: 0
      }
      
      files.value.push(uploadItem)
      
      // 触发上传
      uploadToServer(files.value.length - 1)
      
    } catch (err) {
      console.error('图片处理失败', err)
    }
  }
  
  input.value = '' // reset
}

const removeFile = (index: number) => {
  URL.revokeObjectURL(files.value[index].preview)
  files.value.splice(index, 1)
}

// 图片压缩逻辑
const compressImage = (file: File): Promise<File> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.readAsDataURL(file)
    reader.onload = (e) => {
      const img = new Image()
      img.src = e.target?.result as string
      img.onload = () => {
        let width = img.width
        let height = img.height
        
        // 压缩后尺寸 ≥ 1080 px 短边
        const shortEdge = Math.min(width, height)
        if (shortEdge > 1080) {
          const ratio = 1080 / shortEdge
          width = Math.floor(width * ratio)
          height = Math.floor(height * ratio)
        }

        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        ctx?.drawImage(img, 0, 0, width, height)
        
        // 尝试不同质量以满足 <= 2MB
        let quality = 0.9
        const compress = () => {
          canvas.toBlob((blob) => {
            if (!blob) {
              reject(new Error('压缩失败'))
              return
            }
            if (blob.size > 2 * 1024 * 1024 && quality > 0.1) {
              quality -= 0.1
              compress()
            } else {
              const newFile = new File([blob], file.name.replace(/\.[^/.]+$/, ".jpg"), {
                type: 'image/jpeg',
                lastModified: Date.now()
              })
              resolve(newFile)
            }
          }, 'image/jpeg', quality)
        }
        compress()
      }
      img.onerror = reject
    }
    reader.onerror = reject
  })
}

// 模拟分片上传与重试
const uploadToServer = async (index: number) => {
  const item = files.value[index]
  if (!item) return
  
  item.status = 'uploading'
  
  try {
    // 模拟上传请求
    await new Promise((resolve, reject) => {
      setTimeout(() => {
        // 模拟随机失败
        if (Math.random() > 0.8) reject(new Error('Network error'))
        else resolve(true)
      }, 1000)
    })
    
    item.status = 'success'
  } catch (error) {
    if (item.retryCount < 3) {
      item.retryCount++
      console.log(`上传失败，正在重试 (${item.retryCount}/3)...`)
      uploadToServer(index)
    } else {
      item.status = 'error'
    }
  }
}

const retryUpload = (index: number) => {
  files.value[index].retryCount = 0
  uploadToServer(index)
}
</script>

<style scoped>
.image-uploader {
  margin-top: 10px;
}
.uploader-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  color: #666;
}
.upload-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.preview-item {
  width: 100px;
  height: 100px;
  border-radius: 8px;
  position: relative;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  cursor: grab;
}
.preview-item:active {
  cursor: grabbing;
}
.preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.delete-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0,0,0,0.5);
  color: white;
  border: none;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.delete-btn:hover {
  background: rgba(255,0,0,0.8);
}
.upload-trigger {
  width: 100px;
  height: 100px;
  border: 2px dashed #ddd;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #fcfcfc;
}
.upload-trigger:hover {
  border-color: #FF6A00;
  color: #FF6A00;
}
.trigger-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #999;
}
.plus-icon {
  font-size: 24px;
  font-weight: 300;
}
.text {
  font-size: 12px;
  margin-top: 4px;
}

.status-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255,255,255,0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.status-overlay.error {
  background: rgba(255,0,0,0.6);
  color: white;
  font-size: 12px;
}
.status-overlay.error button {
  margin-top: 4px;
  padding: 2px 8px;
  background: white;
  color: red;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #ccc;
  border-top-color: #FF6A00;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
