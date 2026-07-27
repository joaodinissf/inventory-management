<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <div>
            <div class="budget-label">{{ t('restocking.budgetLabel') }}</div>
            <div class="budget-hint">{{ t('restocking.budgetHint') }}</div>
          </div>
          <div class="budget-value">{{ formatCurrency(budget) }}</div>
        </div>
        <input
          v-model.number="budget"
          type="range"
          class="budget-slider"
          :min="0"
          :max="budgetMax"
          :step="budgetStep"
        />
        <div class="budget-scale">
          <span>{{ formatCurrency(0) }}</span>
          <span>{{ formatCurrency(budgetMax) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.allocated') }}</div>
          <div class="stat-value">{{ formatCurrency(allocated) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(remaining) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.coverage') }}</div>
          <div class="stat-value">
            {{ t('restocking.coverageValue', { covered: fullyCoveredCount, total: candidateCount }) }}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>

        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.shortfall') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in recommendations" :key="row.item_sku">
                <td><strong>{{ row.item_sku }}</strong></td>
                <td>{{ row.item_name }}</td>
                <td>{{ row.shortfall }}</td>
                <td>
                  <strong>{{ row.quantity }}</strong>
                  <span v-if="!row.fully_covered" class="badge warning partial-badge">
                    {{ t('restocking.partial') }}
                  </span>
                </td>
                <td>{{ formatCurrency(row.unit_cost) }}</td>
                <td><strong>{{ formatCurrency(row.line_total) }}</strong></td>
                <td>{{ t('orders.leadTimeDays', { days: row.lead_time_days }) }}</td>
                <td>{{ row.supplier }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-actions">
          <button
            class="place-order-btn"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>

          <div v-if="lastOrder" class="submit-success">
            {{ t('restocking.orderPlaced', {
              orderNumber: lastOrder.order_number,
              days: lastOrder.max_lead_time_days
            }) }}
            <router-link to="/orders" class="orders-link">
              {{ t('restocking.viewInOrders') }}
            </router-link>
          </div>

          <div v-if="submitError" class="submit-error">
            {{ t('restocking.orderFailed', { message: submitError }) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const submitError = ref(null)
    const lastOrder = ref(null)

    // Only items whose forecast outruns current demand can be restocked. The one
    // decreasing-trend item falls out here without needing a special case.
    const candidates = computed(() => {
      return forecasts.value
        .map(f => ({ ...f, shortfall: Math.max(0, f.forecasted_demand - f.current_demand) }))
        .filter(f => f.shortfall > 0)
        .sort((a, b) => b.shortfall - a.shortfall)
    })

    const candidateCount = computed(() => candidates.value.length)

    const totalShortfallCost = computed(() => {
      return candidates.value.reduce((sum, item) => sum + item.shortfall * item.unit_cost, 0)
    })

    // Round the ceiling up to the next $5K so the top of the slider comfortably
    // covers every shortfall, rather than landing exactly on the total.
    const budgetMax = computed(() => {
      return Math.max(5000, Math.ceil(totalShortfallCost.value / 5000) * 5000)
    })

    const budgetStep = computed(() => Math.max(1, Math.round(budgetMax.value / 150)))

    // Greedy allocation: close the largest shortfalls first, on the basis that the
    // item furthest behind its forecast is the one most likely to stock out. When
    // the budget cannot cover the next item in full, buy as many units as it can
    // afford and stop -- anything cheaper further down the list would be a smaller
    // shortfall, and skipping ahead would contradict the stated priority order.
    const recommendations = computed(() => {
      const rows = []
      let remainingBudget = budget.value

      for (const item of candidates.value) {
        const fullCost = item.shortfall * item.unit_cost

        if (fullCost <= remainingBudget) {
          rows.push(buildRow(item, item.shortfall, true))
          remainingBudget -= fullCost
          continue
        }

        const affordableQty = item.unit_cost > 0
          ? Math.floor(remainingBudget / item.unit_cost)
          : 0

        if (affordableQty > 0) {
          rows.push(buildRow(item, affordableQty, false))
        }
        break
      }

      return rows
    })

    const buildRow = (item, quantity, fullyCovered) => ({
      item_sku: item.item_sku,
      item_name: item.item_name,
      shortfall: item.shortfall,
      quantity,
      unit_cost: item.unit_cost,
      line_total: Math.round(quantity * item.unit_cost * 100) / 100,
      lead_time_days: item.lead_time_days,
      supplier: item.supplier,
      fully_covered: fullyCovered
    })

    const allocated = computed(() => {
      return recommendations.value.reduce((sum, row) => sum + row.line_total, 0)
    })

    const remaining = computed(() => budget.value - allocated.value)

    const fullyCoveredCount = computed(() => {
      return recommendations.value.filter(row => row.fully_covered).length
    })

    const formatCurrency = (value) => formatCurrencyUtil(value, currentCurrency.value)

    const loadForecasts = async () => {
      try {
        loading.value = true
        forecasts.value = await api.getDemandForecasts()
        // Open on a half-funded budget so the page demonstrates partial coverage
        // rather than an empty or fully-satisfied list.
        budget.value = Math.round(budgetMax.value / 2 / budgetStep.value) * budgetStep.value
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      submitting.value = true
      submitError.value = null
      lastOrder.value = null

      try {
        lastOrder.value = await api.createRestockOrder({
          budget: budget.value,
          items: recommendations.value.map(row => ({
            sku: row.item_sku,
            name: row.item_name,
            quantity: row.quantity,
            unit_price: row.unit_cost,
            lead_time_days: row.lead_time_days,
            supplier: row.supplier
          }))
        })
      } catch (err) {
        submitError.value = err.response?.data?.detail || err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      budgetMax,
      budgetStep,
      recommendations,
      candidateCount,
      allocated,
      remaining,
      fullyCoveredCount,
      formatCurrency,
      submitting,
      submitError,
      lastOrder,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-hint {
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1;
  white-space: nowrap;
}

/* Range inputs are the first in this codebase, so the track and thumb need
   explicit styling for both WebKit and Firefox to look consistent. */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 4px;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #94a3b8;
  margin-top: 0.5rem;
}

.partial-badge {
  margin-left: 0.5rem;
}

.empty-state {
  padding: 2.5rem 1.5rem;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.order-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.place-order-btn {
  background: #3b82f6;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-btn:hover:not(:disabled) {
  background: #2563eb;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.submit-success {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.875rem;
  color: #059669;
  font-weight: 500;
}

.orders-link {
  color: #3b82f6;
  text-decoration: underline;
}

.submit-error {
  font-size: 0.875rem;
  color: #dc2626;
  font-weight: 500;
}
</style>
