<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ t('reports.title') }}</h2>
      <p>{{ t('reports.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Quarterly Performance -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.quarterly.title') }}</h3>
        </div>
        <div v-if="quarterlyRows.length" class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.quarterly.table.quarter') }}</th>
                <th>{{ t('reports.quarterly.table.totalOrders') }}</th>
                <th>{{ t('reports.quarterly.table.totalRevenue') }}</th>
                <th>{{ t('reports.quarterly.table.avgOrderValue') }}</th>
                <th>{{ t('reports.quarterly.table.fulfillmentRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in quarterlyRows" :key="q.quarter">
                <td><strong>{{ q.quarter }}</strong></td>
                <td>{{ q.totalOrders }}</td>
                <td>{{ q.totalRevenue }}</td>
                <td>{{ q.avgOrderValue }}</td>
                <td>
                  <span :class="q.fulfillmentClass">
                    {{ q.fulfillmentRate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="no-data">{{ t('common.noData') }}</div>
      </div>

      <!-- Monthly Trends Chart -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthlyTrend.title') }}</h3>
        </div>
        <div v-if="chartBars.length" class="chart-container">
          <div class="bar-chart">
            <div v-for="bar in chartBars" :key="bar.month" class="bar-wrapper">
              <div class="bar-container">
                <div
                  class="bar"
                  role="img"
                  :style="{ height: bar.heightPercent + '%' }"
                  :title="bar.tooltip"
                  :aria-label="bar.label + ' - ' + bar.tooltip"
                ></div>
              </div>
              <div class="bar-label">{{ bar.label }}</div>
            </div>
          </div>
        </div>
        <div v-else class="no-data">{{ t('common.noData') }}</div>
      </div>

      <!-- Month-over-Month Comparison -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthOverMonth.title') }}</h3>
        </div>
        <div v-if="monthlyRows.length" class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.monthOverMonth.table.month') }}</th>
                <th>{{ t('reports.monthOverMonth.table.orders') }}</th>
                <th>{{ t('reports.monthOverMonth.table.revenue') }}</th>
                <th>{{ t('reports.monthOverMonth.table.change') }}</th>
                <th>{{ t('reports.monthOverMonth.table.growthRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in monthlyRows" :key="row.month">
                <td><strong>{{ row.label }}</strong></td>
                <td>{{ row.orderCount }}</td>
                <td>{{ row.revenue }}</td>
                <td>
                  <span v-if="row.hasPrevious" :class="row.changeClass">
                    {{ row.changeLabel }}
                  </span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="row.hasPrevious" :class="row.changeClass">
                    {{ row.growthRate }}
                  </span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="no-data">{{ t('common.noData') }}</div>
      </div>

      <!-- Summary Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.totalRevenueYtd') }}</div>
          <div class="stat-value">{{ totalRevenueLabel }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.avgMonthlyRevenue') }}</div>
          <div class="stat-value">{{ avgMonthlyRevenueLabel }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.totalOrdersYtd') }}</div>
          <div class="stat-value">{{ totalOrdersLabel }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.bestQuarter') }}</div>
          <div class="stat-value">{{ bestQuarter }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Reports',
  setup() {
    const { t, currentLocale, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const quarterlyData = ref([])
    const monthlyData = ref([])

    // Use shared filters so the global FilterBar drives this page like every other view
    const {
      selectedPeriod,
      selectedLocation,
      selectedCategory,
      selectedStatus,
      getCurrentFilters
    } = useFilters()

    // BCP 47 tag used by every Intl call below, derived from the active locale
    const localeTag = computed(() => (currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'))

    // Shared formatters: the report endpoints omit some numeric keys when a
    // bucket has no orders, so every formatter tolerates null/undefined/NaN.
    const formatMoney = (value) => {
      if (value == null || Number.isNaN(value)) return '-'
      return formatCurrency(value, currentCurrency.value)
    }

    const formatCount = (value) => {
      if (value == null || Number.isNaN(value)) return '-'
      return value.toLocaleString(localeTag.value)
    }

    const formatMonth = (monthStr) => {
      // Validate the YYYY-MM shape before parsing; a malformed or missing value
      // would otherwise render as "undefined undefined" in the table and chart.
      if (!monthStr || !/^\d{4}-\d{2}$/.test(monthStr)) return '-'
      const date = new Date(`${monthStr}-01T00:00:00`)
      if (Number.isNaN(date.getTime())) return '-'
      return date.toLocaleDateString(localeTag.value, { month: 'short', year: 'numeric' })
    }

    // Service-level thresholds mirrored from the Dashboard's order fill rate
    // badges: >=90% on target, >=75% at risk, below that is a breach.
    const getFulfillmentClass = (rate) => {
      const value = rate ?? 0
      if (value >= 90) return 'badge success'
      if (value >= 75) return 'badge warning'
      return 'badge danger'
    }

    const loadData = async () => {
      try {
        loading.value = true
        // Reset the previous failure so a successful reload (every filter
        // change triggers one) clears a stale error banner.
        error.value = null

        const filters = getCurrentFilters()
        // The two report endpoints are independent, so fetch them concurrently.
        const [quarterly, monthly] = await Promise.all([
          api.getQuarterlyReports(filters),
          api.getMonthlyTrends(filters)
        ])
        quarterlyData.value = quarterly
        monthlyData.value = monthly
      } catch (err) {
        console.error('Failed to load reports:', err)
        error.value = t('reports.errors.loadFailed', { message: err.message })
      } finally {
        loading.value = false
      }
    }

    // Summary stats are pure derivations of the fetched data
    const totalRevenue = computed(() =>
      monthlyData.value.reduce((sum, month) => sum + (month.revenue || 0), 0)
    )

    const avgMonthlyRevenue = computed(() =>
      monthlyData.value.length ? totalRevenue.value / monthlyData.value.length : 0
    )

    const totalOrders = computed(() =>
      monthlyData.value.reduce((sum, month) => sum + (month.order_count || 0), 0)
    )

    const bestQuarter = computed(() => {
      const best = quarterlyData.value.reduce(
        (current, quarter) =>
          !current || quarter.total_revenue > current.total_revenue ? quarter : current,
        null
      )
      return best ? best.quarter : '-'
    })

    const totalRevenueLabel = computed(() => formatMoney(totalRevenue.value))
    const avgMonthlyRevenueLabel = computed(() => formatMoney(avgMonthlyRevenue.value))
    const totalOrdersLabel = computed(() => formatCount(totalOrders.value))

    // Scanned once per data change instead of once per bar per render
    const maxRevenue = computed(() =>
      monthlyData.value.length
        ? Math.max(...monthlyData.value.map((month) => month.revenue || 0))
        : 0
    )

    const chartBars = computed(() =>
      monthlyData.value.map((month) => ({
        month: month.month,
        label: formatMonth(month.month),
        // Height is a percentage of the fixed-height .bar-container so the bars
        // scale with the container instead of using hardcoded pixel heights.
        heightPercent: maxRevenue.value > 0 ? ((month.revenue || 0) / maxRevenue.value) * 100 : 0,
        tooltip: t('reports.chart.revenueTooltip', { revenue: formatMoney(month.revenue) })
      }))
    )

    const quarterlyRows = computed(() =>
      quarterlyData.value.map((quarter) => ({
        quarter: quarter.quarter,
        totalOrders: formatCount(quarter.total_orders),
        totalRevenue: formatMoney(quarter.total_revenue),
        avgOrderValue: formatMoney(quarter.avg_order_value),
        // Fixed precision keeps the badge width stable across quarters
        fulfillmentRate: (quarter.fulfillment_rate ?? 0).toFixed(1),
        fulfillmentClass: getFulfillmentClass(quarter.fulfillment_rate)
      }))
    )

    // Rows carry their own month-over-month comparison so the template never
    // reaches back into the array by index while rendering.
    const monthlyRows = computed(() =>
      monthlyData.value.map((month, index) => {
        const previous = index > 0 ? monthlyData.value[index - 1] : null
        const current = month.revenue || 0
        const previousRevenue = previous ? previous.revenue || 0 : null
        const change = previous ? current - previousRevenue : 0

        let changeLabel = formatMoney(0)
        if (change > 0) {
          changeLabel = `+${formatMoney(change)}`
        } else if (change < 0) {
          changeLabel = `-${formatMoney(Math.abs(change))}`
        }

        let changeClass = ''
        if (change > 0) {
          changeClass = 'positive-change'
        } else if (change < 0) {
          changeClass = 'negative-change'
        }

        // A zero or missing baseline makes the percentage undefined, not 0%
        let growthRate = t('reports.monthOverMonth.notAvailable')
        if (previousRevenue) {
          const rate = ((current - previousRevenue) / previousRevenue) * 100
          growthRate = `${rate > 0 ? '+' : ''}${rate.toFixed(1)}%`
        }

        return {
          month: month.month,
          label: formatMonth(month.month),
          orderCount: formatCount(month.order_count),
          revenue: formatMoney(month.revenue),
          hasPrevious: previous !== null,
          changeLabel,
          changeClass,
          growthRate
        }
      })
    )

    // Watch for filter changes and reload data
    watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], () => {
      loadData()
    })

    onMounted(loadData)

    return {
      t,
      loading,
      error,
      quarterlyRows,
      monthlyRows,
      chartBars,
      totalRevenueLabel,
      avgMonthlyRevenueLabel,
      totalOrdersLabel,
      bestQuarter
    }
  }
}
</script>

<style scoped>
/* Only Reports-specific rules live here; .card, .stats-grid, .stat-card,
   .badge, .loading and .error come from the global styles in App.vue so this
   page stays in sync with the rest of the design system. */
.reports {
  padding: 0;
}

.reports-table {
  width: 100%;
  border-collapse: collapse;
}

.chart-container {
  padding: 2rem 1rem;
  min-height: 300px;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 250px;
  gap: 0.5rem;
}

.bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 80px;
}

.bar-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
  width: 100%;
}

.bar {
  width: 100%;
  background: linear-gradient(to top, #3b82f6, #60a5fa);
  border-radius: 4px 4px 0 0;
  transition: all 0.3s;
  cursor: pointer;
}

.bar:hover {
  background: linear-gradient(to top, #2563eb, #3b82f6);
}

.bar-label {
  font-size: 0.75rem;
  color: #64748b;
  text-align: center;
  transform: rotate(-45deg);
  white-space: nowrap;
  margin-top: 1.5rem;
}

.positive-change {
  color: #16a34a;
  font-weight: 600;
}

.negative-change {
  color: #dc2626;
  font-weight: 600;
}

.no-data {
  padding: 2rem;
  text-align: center;
  color: #94a3b8;
  font-size: 0.875rem;
}
</style>
