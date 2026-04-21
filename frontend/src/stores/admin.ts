import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, {
  type Product,
  type Warehouse,
  type Supplier,
  type Lane,
  type PlanningPolicy,
  type WarehouseProduct,
  type SupplierProduct,
} from '@/api/client'

export const useAdminStore = defineStore('admin', () => {
  const products = ref<Product[]>([])
  const warehouses = ref<Warehouse[]>([])
  const suppliers = ref<Supplier[]>([])
  const lanes = ref<Lane[]>([])
  const planningPolicies = ref<PlanningPolicy[]>([])
  const warehouseProducts = ref<WarehouseProduct[]>([])
  const supplierProducts = ref<SupplierProduct[]>([])

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

  async function fetchWarehouseProducts(warehouseId: number) {
    const { data } = await api.get<WarehouseProduct[]>('/warehouse-products', { params: { warehouse_id: warehouseId } })
    warehouseProducts.value = data
    return data
  }

  function clearWarehouseProducts() {
    warehouseProducts.value = []
  }

  async function fetchSupplierProducts(supplierId: number) {
    const { data } = await api.get<SupplierProduct[]>('/supplier-products', { params: { supplier_id: supplierId } })
    supplierProducts.value = data
    return data
  }

  function clearSupplierProducts() {
    supplierProducts.value = []
  }

  async function createProduct(p: { sku: string; name?: string; description?: string; uom?: string; active?: boolean }) {
    const { data } = await api.post<Product>('/products', p)
    products.value.push(data)
    return data
  }

  async function updateProduct(id: number, p: Partial<{ sku: string; name: string; description: string; uom: string; active: boolean }>) {
    const { data } = await api.put<Product>(`/products/${id}`, p)
    const i = products.value.findIndex((x) => x.id === id)
    if (i >= 0) products.value[i] = data
    return data
  }

  async function createWarehouse(w: {
    code: string
    name?: string | null
    timezone?: string
    active?: boolean
    is_own_site?: boolean
    operator_name?: string | null
    address?: string | null
    site_type?: string
  }) {
    const { data } = await api.post<Warehouse>('/warehouses', w)
    warehouses.value.push(data)
    return data
  }

  async function updateWarehouse(
    id: number,
    w: {
      code: string
      name?: string | null
      timezone?: string
      active?: boolean
      is_own_site?: boolean
      operator_name?: string | null
      address?: string | null
      site_type?: string
    },
  ) {
    const { data } = await api.put<Warehouse>(`/warehouses/${id}`, w)
    const i = warehouses.value.findIndex((x) => x.id === id)
    if (i >= 0) warehouses.value[i] = data
    return data
  }

  async function deleteWarehouse(id: number) {
    await api.delete(`/warehouses/${id}`)
    warehouses.value = warehouses.value.filter((x) => x.id !== id)
  }

  async function createSupplier(s: { code: string; name?: string; active?: boolean }) {
    const { data } = await api.post<Supplier>('/suppliers', s)
    suppliers.value.push(data)
    return data
  }

  async function updateSupplier(id: number, s: Partial<{ code: string; name: string; active: boolean }>) {
    const { data } = await api.put<Supplier>(`/suppliers/${id}`, s)
    const i = suppliers.value.findIndex((x) => x.id === id)
    if (i >= 0) suppliers.value[i] = data
    return data
  }

  async function createLane(l: { supplier_id: number; warehouse_id: number; code?: string }) {
    const { data } = await api.post<Lane>('/lanes', l)
    lanes.value.push(data)
    return data
  }

  async function deleteLane(id: number) {
    await api.delete(`/lanes/${id}`)
    lanes.value = lanes.value.filter((x) => x.id !== id)
  }

  async function createPlanningPolicy(p: Partial<PlanningPolicy> & { sku: string; warehouse_code: string }) {
    const { data } = await api.post<PlanningPolicy>('/planning-policies', p)
    planningPolicies.value.push(data)
    return data
  }

  async function updatePlanningPolicy(id: number, p: Partial<PlanningPolicy>) {
    const { data } = await api.put<PlanningPolicy>(`/planning-policies/${id}`, p)
    const i = planningPolicies.value.findIndex((x) => x.id === id)
    if (i >= 0) planningPolicies.value[i] = data
    return data
  }

  async function deletePlanningPolicy(id: number) {
    await api.delete(`/planning-policies/${id}`)
    planningPolicies.value = planningPolicies.value.filter((x) => x.id !== id)
  }

  async function createWarehouseProduct(body: { warehouse_id: number; product_id: number; safety_stock_mode?: string; safety_stock_units?: number | null; safety_stock_weeks?: number | null; haulage_buffer_weeks?: number; stocking_buffer_weeks?: number; reorder_review_weeks?: number; active?: boolean }) {
    const { data } = await api.post<WarehouseProduct>('/warehouse-products', body)
    warehouseProducts.value.push(data)
    return data
  }

  async function updateWarehouseProduct(id: number, body: Partial<{ safety_stock_mode: string; safety_stock_units: number | null; safety_stock_weeks: number | null; haulage_buffer_weeks: number; stocking_buffer_weeks: number; reorder_review_weeks: number; active: boolean }>) {
    const { data } = await api.put<WarehouseProduct>(`/warehouse-products/${id}`, body)
    const i = warehouseProducts.value.findIndex((x) => x.id === id)
    if (i >= 0) warehouseProducts.value[i] = data
    return data
  }

  async function deleteWarehouseProduct(id: number) {
    await api.delete(`/warehouse-products/${id}`)
    warehouseProducts.value = warehouseProducts.value.filter((x) => x.id !== id)
  }

  async function createSupplierProduct(body: { supplier_id: number; product_id: number; lead_time_weeks?: number; moq_units?: number | null; pack_size_units?: number | null; active?: boolean }) {
    const { data } = await api.post<SupplierProduct>('/supplier-products', body)
    supplierProducts.value.push(data)
    return data
  }

  async function updateSupplierProduct(id: number, body: Partial<{ lead_time_weeks: number; moq_units: number | null; pack_size_units: number | null; active: boolean }>) {
    const { data } = await api.put<SupplierProduct>(`/supplier-products/${id}`, body)
    const i = supplierProducts.value.findIndex((x) => x.id === id)
    if (i >= 0) supplierProducts.value[i] = data
    return data
  }

  async function deleteSupplierProduct(id: number) {
    await api.delete(`/supplier-products/${id}`)
    supplierProducts.value = supplierProducts.value.filter((x) => x.id !== id)
  }

  return {
    products,
    warehouses,
    suppliers,
    lanes,
    planningPolicies,
    warehouseProducts,
    supplierProducts,
    fetchProducts,
    fetchWarehouses,
    fetchSuppliers,
    fetchLanes,
    fetchPlanningPolicies,
    fetchWarehouseProducts,
    clearWarehouseProducts,
    fetchSupplierProducts,
    clearSupplierProducts,
    createProduct,
    updateProduct,
    createWarehouse,
    updateWarehouse,
    deleteWarehouse,
    createSupplier,
    updateSupplier,
    createLane,
    deleteLane,
    createPlanningPolicy,
    updatePlanningPolicy,
    deletePlanningPolicy,
    createWarehouseProduct,
    updateWarehouseProduct,
    deleteWarehouseProduct,
    createSupplierProduct,
    updateSupplierProduct,
    deleteSupplierProduct,
  }
})
