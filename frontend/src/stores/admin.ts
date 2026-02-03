import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, {
  type Product,
  type Warehouse,
  type Supplier,
  type Lane,
  type PlanningPolicy,
} from '@/api/client'

export const useAdminStore = defineStore('admin', () => {
  const products = ref<Product[]>([])
  const warehouses = ref<Warehouse[]>([])
  const suppliers = ref<Supplier[]>([])
  const lanes = ref<Lane[]>([])
  const planningPolicies = ref<PlanningPolicy[]>([])

  async function fetchProducts() {
    const { data } = await api.get<Product[]>('/products')
    products.value = data
    return data
  }

  async function fetchWarehouses() {
    const { data } = await api.get<Warehouse[]>('/warehouses')
    warehouses.value = data
    return data
  }

  async function fetchSuppliers() {
    const { data } = await api.get<Supplier[]>('/suppliers')
    suppliers.value = data
    return data
  }

  async function fetchLanes() {
    const { data } = await api.get<Lane[]>('/lanes')
    lanes.value = data
    return data
  }

  async function fetchPlanningPolicies(sku?: string, warehouseCode?: string) {
    const params = new URLSearchParams()
    if (sku) params.set('sku', sku)
    if (warehouseCode) params.set('warehouse_code', warehouseCode)
    const { data } = await api.get<PlanningPolicy[]>(`/planning-policies?${params}`)
    planningPolicies.value = data
    return data
  }

  async function createProduct(p: { sku: string; name?: string; description?: string }) {
    const { data } = await api.post<Product>('/products', p)
    products.value.push(data)
    return data
  }

  async function createWarehouse(w: { code: string; name?: string }) {
    const { data } = await api.post<Warehouse>('/warehouses', w)
    warehouses.value.push(data)
    return data
  }

  async function createSupplier(s: { code: string; name?: string }) {
    const { data } = await api.post<Supplier>('/suppliers', s)
    suppliers.value.push(data)
    return data
  }

  async function createLane(l: { supplier_id: number; warehouse_id: number; code?: string }) {
    const { data } = await api.post<Lane>('/lanes', l)
    lanes.value.push(data)
    return data
  }

  async function createPlanningPolicy(p: Partial<PlanningPolicy> & { sku: string; warehouse_code: string }) {
    const { data } = await api.post<PlanningPolicy>('/planning-policies', p)
    planningPolicies.value.push(data)
    return data
  }

  return {
    products,
    warehouses,
    suppliers,
    lanes,
    planningPolicies,
    fetchProducts,
    fetchWarehouses,
    fetchSuppliers,
    fetchLanes,
    fetchPlanningPolicies,
    createProduct,
    createWarehouse,
    createSupplier,
    createLane,
    createPlanningPolicy,
  }
})
