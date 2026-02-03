<template>
  <div class="admin">
    <h1>Admin</h1>
    <p class="muted">Products, Warehouses, Suppliers/Lanes, Planning Policies.</p>

    <section class="card">
      <h2>Products</h2>
      <table class="table">
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
      <form @submit.prevent="addProduct" class="form-inline">
        <input v-model="newProduct.sku" placeholder="SKU" required />
        <input v-model="newProduct.name" placeholder="Name" />
        <input v-model="newProduct.description" placeholder="Description" />
        <button type="submit">Add product</button>
      </form>
    </section>

    <section class="card">
      <h2>Warehouses</h2>
      <table class="table">
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
      <form @submit.prevent="addWarehouse" class="form-inline">
        <input v-model="newWarehouse.code" placeholder="Code" required />
        <input v-model="newWarehouse.name" placeholder="Name" />
        <button type="submit">Add warehouse</button>
      </form>
    </section>

    <section class="card">
      <h2>Suppliers</h2>
      <table class="table">
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
      <form @submit.prevent="addSupplier" class="form-inline">
        <input v-model="newSupplier.code" placeholder="Code" required />
        <input v-model="newSupplier.name" placeholder="Name" />
        <button type="submit">Add supplier</button>
      </form>
    </section>

    <section class="card">
      <h2>Lanes (Supplier → Warehouse)</h2>
      <table class="table">
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
      <form @submit.prevent="addLane" class="form-inline">
        <select v-model="newLane.supplier_id" required>
          <option :value="0">Supplier</option>
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.code }}</option>
        </select>
        <select v-model="newLane.warehouse_id" required>
          <option :value="0">Warehouse</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.code }}</option>
        </select>
        <input v-model="newLane.code" placeholder="Lane code" />
        <button type="submit">Add lane</button>
      </form>
    </section>

    <section class="card">
      <h2>Planning Policies (SKU × Warehouse)</h2>
      <table class="table">
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
      <form @submit.prevent="addPolicy" class="form-inline form-wide">
        <input v-model="newPolicy.sku" placeholder="SKU" required />
        <input v-model="newPolicy.warehouse_code" placeholder="Warehouse code" required />
        <select v-model="newPolicy.mode">
          <option value="WOS_TARGET">WOS_TARGET</option>
          <option value="ROP">ROP</option>
        </select>
        <input v-model.number="newPolicy.target_weeks" type="number" step="0.1" placeholder="Target weeks" />
        <input v-model.number="newPolicy.safety_stock_weeks" type="number" step="0.1" placeholder="Safety weeks" />
        <input v-model.number="newPolicy.forecast_window_weeks" type="number" placeholder="Forecast window" />
        <button type="submit">Add policy</button>
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
.admin { display: flex; flex-direction: column; gap: 1rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.card h2 { margin: 0 0 0.5rem 0; font-size: 1rem; }
.table { width: 100%; border-collapse: collapse; margin-bottom: 0.5rem; }
.table th, .table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
.form-inline { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
.form-inline input, .form-inline select { padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); }
.form-inline button { padding: 0.35rem 0.75rem; background: var(--accent); color: var(--bg); border: none; border-radius: var(--radius); cursor: pointer; }
.form-wide { flex-wrap: wrap; }
.muted { color: var(--muted); margin: 0.5rem 0; }
</style>
