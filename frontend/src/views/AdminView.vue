<template>
  <div class="page-content-inner">
    <p class="muted">Products, Warehouses, Suppliers/Lanes, Planning Policies.</p>

    <section class="content-section">
      <h2>Products</h2>
      <div class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Name</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in products" :key="p.id">
              <td>{{ p.sku }}</td>
              <td>{{ p.name ?? '—' }}</td>
              <td>{{ p.description ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form @submit.prevent="addProduct" class="form-inline">
        <input v-model="newProduct.sku" class="app-input" placeholder="SKU" required style="max-width: 8rem;" />
        <input v-model="newProduct.name" class="app-input" placeholder="Name" style="max-width: 10rem;" />
        <input v-model="newProduct.description" class="app-input" placeholder="Description" style="max-width: 14rem;" />
        <button type="submit" class="app-btn app-btn-primary">Add product</button>
      </form>
    </section>

    <section class="content-section">
      <h2>Warehouses</h2>
      <div class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in warehouses" :key="w.id">
              <td>{{ w.code }}</td>
              <td>{{ w.name ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form @submit.prevent="addWarehouse" class="form-inline">
        <input v-model="newWarehouse.code" class="app-input" placeholder="Code" required style="max-width: 8rem;" />
        <input v-model="newWarehouse.name" class="app-input" placeholder="Name" style="max-width: 10rem;" />
        <button type="submit" class="app-btn app-btn-primary">Add warehouse</button>
      </form>
    </section>

    <section class="content-section">
      <h2>Suppliers</h2>
      <div class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in suppliers" :key="s.id">
              <td>{{ s.code }}</td>
              <td>{{ s.name ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form @submit.prevent="addSupplier" class="form-inline">
        <input v-model="newSupplier.code" class="app-input" placeholder="Code" required style="max-width: 8rem;" />
        <input v-model="newSupplier.name" class="app-input" placeholder="Name" style="max-width: 10rem;" />
        <button type="submit" class="app-btn app-btn-primary">Add supplier</button>
      </form>
    </section>

    <section class="content-section">
      <h2>Lanes (Supplier → Warehouse)</h2>
      <div class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Warehouse</th>
              <th>Code</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in lanes" :key="l.id">
              <td>{{ supplierCode(l.supplier_id) }}</td>
              <td>{{ warehouseCode(l.warehouse_id) }}</td>
              <td>{{ l.code ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form @submit.prevent="addLane" class="form-inline">
        <select v-model="newLane.supplier_id" class="app-select" required style="max-width: 10rem;">
          <option :value="0">Supplier</option>
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.code }}</option>
        </select>
        <select v-model="newLane.warehouse_id" class="app-select" required style="max-width: 10rem;">
          <option :value="0">Warehouse</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.code }}</option>
        </select>
        <input v-model="newLane.code" class="app-input" placeholder="Lane code" style="max-width: 8rem;" />
        <button type="submit" class="app-btn app-btn-primary">Add lane</button>
      </form>
    </section>

    <section class="content-section">
      <h2>Planning Policies (SKU × Warehouse)</h2>
      <div class="app-table-wrap">
        <table class="app-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Warehouse</th>
              <th>Mode</th>
              <th>Target weeks</th>
              <th>Safety weeks</th>
              <th>Forecast window</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in planningPolicies" :key="p.id">
              <td>{{ p.sku }}</td>
              <td>{{ p.warehouse_code }}</td>
              <td>{{ p.mode }}</td>
              <td>{{ p.target_weeks }}</td>
              <td>{{ p.safety_stock_weeks }}</td>
              <td>{{ p.forecast_window_weeks }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form @submit.prevent="addPolicy" class="form-inline form-wide">
        <input v-model="newPolicy.sku" class="app-input" placeholder="SKU" required style="max-width: 8rem;" />
        <input v-model="newPolicy.warehouse_code" class="app-input" placeholder="Warehouse code" required style="max-width: 10rem;" />
        <select v-model="newPolicy.mode" class="app-select" style="max-width: 10rem;">
          <option value="WOS_TARGET">WOS_TARGET</option>
          <option value="ROP">ROP</option>
        </select>
        <input v-model.number="newPolicy.target_weeks" type="number" step="0.1" class="app-input" placeholder="Target weeks" style="max-width: 6rem;" />
        <input v-model.number="newPolicy.safety_stock_weeks" type="number" step="0.1" class="app-input" placeholder="Safety weeks" style="max-width: 6rem;" />
        <input v-model.number="newPolicy.forecast_window_weeks" type="number" class="app-input" placeholder="Forecast window" style="max-width: 6rem;" />
        <button type="submit" class="app-btn app-btn-primary">Add policy</button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAdminStore } from '@/stores/admin'
import type { PlanningPolicy, Supplier, Warehouse } from '@/api/client'

const store = useAdminStore()
const products = computed(() => store.products)
const warehouses = computed(() => store.warehouses)
const suppliers = computed(() => store.suppliers)
const lanes = computed(() => store.lanes)
const planningPolicies = computed(() => store.planningPolicies)

const newProduct = ref({ sku: '', name: '', description: '' })
const newWarehouse = ref({ code: '', name: '' })
const newSupplier = ref({ code: '', name: '' })
const newLane = ref({ supplier_id: 0, warehouse_id: 0, code: '' })
const newPolicy = ref<Partial<PlanningPolicy> & { sku: string; warehouse_code: string }>({
  sku: '',
  warehouse_code: '',
  mode: 'WOS_TARGET',
  target_weeks: '4',
  safety_stock_weeks: '1',
  forecast_window_weeks: 8,
})

function supplierCode(id: number) {
  return store.suppliers.find((s: Supplier) => s.id === id)?.code ?? id
}
function warehouseCode(id: number) {
  return store.warehouses.find((w: Warehouse) => w.id === id)?.code ?? id
}

async function addProduct() {
  await store.createProduct(newProduct.value)
  newProduct.value = { sku: '', name: '', description: '' }
}
async function addWarehouse() {
  await store.createWarehouse(newWarehouse.value)
  newWarehouse.value = { code: '', name: '' }
}
async function addSupplier() {
  await store.createSupplier(newSupplier.value)
  newSupplier.value = { code: '', name: '' }
}
async function addLane() {
  if (newLane.value.supplier_id && newLane.value.warehouse_id) {
    await store.createLane({
      supplier_id: newLane.value.supplier_id,
      warehouse_id: newLane.value.warehouse_id,
      code: newLane.value.code || undefined,
    })
    newLane.value = { supplier_id: 0, warehouse_id: 0, code: '' }
  }
}
async function addPolicy() {
  await store.createPlanningPolicy({
    sku: newPolicy.value.sku!,
    warehouse_code: newPolicy.value.warehouse_code!,
    mode: newPolicy.value.mode ?? 'WOS_TARGET',
    target_weeks: newPolicy.value.target_weeks ?? '4',
    safety_stock_weeks: newPolicy.value.safety_stock_weeks ?? '1',
    forecast_window_weeks: newPolicy.value.forecast_window_weeks ?? 8,
  })
  newPolicy.value = { sku: '', warehouse_code: '', mode: 'WOS_TARGET', target_weeks: '4', safety_stock_weeks: '1', forecast_window_weeks: 8 }
}

onMounted(async () => {
  await Promise.all([
    store.fetchProducts(),
    store.fetchWarehouses(),
    store.fetchSuppliers(),
    store.fetchLanes(),
    store.fetchPlanningPolicies(),
  ])
})
</script>

<style scoped>
.form-inline { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-top: 0.5rem; }
.form-wide { flex-wrap: wrap; }
</style>
