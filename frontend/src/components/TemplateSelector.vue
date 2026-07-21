<template>
  <div class="template-selector">
    <h3 class="selector-title">模板选择</h3>

    <div class="template-cards">
      <div
        v-for="tpl in templates"
        :key="tpl.key"
        class="template-card"
        :class="{ 'template-card--selected': modelValue === tpl.key }"
        @click="$emit('update:modelValue', tpl.key)"
      >
        <span class="template-card__icon">{{ tpl.icon }}</span>
        <span class="template-card__name">{{ tpl.name }}</span>
        <span class="template-card__desc">{{ tpl.description }}</span>
      </div>
    </div>

    <div class="selector-extra">
      <label class="extra-label">自定义提取需求（可选）</label>
      <el-input
        :model-value="customRequirement"
        type="textarea"
        :rows="3"
        placeholder="例如：提取发票号码、开票日期、金额、销售方名称、购买方名称"
        @update:model-value="$emit('update:customRequirement', $event)"
      />
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'general' },
  customRequirement: { type: String, default: '' },
})

defineEmits(['update:modelValue', 'update:customRequirement'])

const templates = [
  {
    key: 'invoice',
    icon: '🧾',
    name: '增值税发票',
    description: '发票号码、日期、金额、税率、购销方',
  },
  {
    key: 'receipt',
    icon: '📃',
    name: '收据',
    description: '收据号、日期、金额、收款方、付款方',
  },
  {
    key: 'bank_receipt',
    icon: '🏦',
    name: '银行回单',
    description: '交易流水号、金额、收付款账户、摘要',
  },
  {
    key: 'general',
    icon: '📋',
    name: '通用票据',
    description: '自动识别，适用于其他类型票据',
  },
]
</script>

<style scoped>
.template-selector {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
}

.selector-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 16px;
}

.template-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.template-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 16px;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-surface-card);
}

.template-card:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-sm);
}

.template-card--selected {
  border-color: var(--color-primary);
  background: rgba(79, 70, 229, 0.04);
  box-shadow: 0 0 0 1px var(--color-primary);
}

.template-card__icon {
  font-size: 28px;
  line-height: 1;
}

.template-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.template-card__desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  text-align: center;
  line-height: 1.4;
}

.extra-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 8px;
}
</style>
