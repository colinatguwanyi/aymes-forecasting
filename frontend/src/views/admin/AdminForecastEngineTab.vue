<template>
  <div class="page-shell space-y-5">

    <!-- Engine page header -->
    <div class="engine-header">
      <div class="engine-header__title">
        <h2 class="text-lg font-semibold text-slate-800">Forecast Engine</h2>
        <p class="text-sm text-slate-500 mt-0.5">
          MySQL-backed demand forecasting pipeline — Prophet &amp; XGBoost models, stock-aware preprocessing, and legacy-compatible output.
        </p>
      </div>
      <div class="engine-header__note">
        <span class="engine-note-icon">ⓘ</span>
        <span class="text-xs text-slate-500">
          Planning views (Dashboard, Stock Projection) use the <strong>baseline forecast system</strong> and are not affected by this engine.
          This engine produces a separate, newer forecast output.
        </span>
      </div>
    </div>

    <!-- Legacy DB status banner -->
    <div
      v-if="legacyDbStatus !== null"
      class="legacy-banner"
      :class="legacyDbStatus.can_connect ? 'legacy-banner--ok' : 'legacy-banner--warn'"
    >
      <span class="legacy-banner__icon">{{ legacyDbStatus.can_connect ? '✓' : '⚠' }}</span>
      <span v-if="legacyDbStatus.can_connect">
        Legacy MySQL (aymes_reports) connected — parity validation available.
      </span>
      <span v-else>
        Legacy MySQL not yet accessible — parity validation disabled. Credential whitelisting pending.
        Forecast runs still execute from the form below; only optional legacy export/parity need this connection.
        <span class="legacy-banner__detail">{{ (legacyDbStatus.errors || [])[0] }}</span>
      </span>
    </div>

    <!-- In-page section tabs -->
    <div class="section-tabs">
      <button
        class="section-tab"
        :class="{ active: activeSection === 'configs' }"
        @click="activeSection = 'configs'"
      >Configuration</button>
      <button
        class="section-tab"
        :class="{ active: activeSection === 'runs' }"
        @click="activeSection = 'runs'"
      >Forecast Runs</button>
      <button
        class="section-tab"
        :class="{ active: activeSection === 'debug' }"
        @click="activeSection = 'debug'"
      >Debug &amp; Health</button>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════
         CONFIGS SECTION
    ═══════════════════════════════════════════════════════════════ -->
    <template v-if="activeSection === 'configs'">

      <!-- Runtime Configs -->
      <section class="card card-body">
        <div class="card-section-header">
          <div>
            <h3 class="section-title">Runtime Configs</h3>
            <p class="muted text-sm mt-0.5">Forecast horizon, stock thresholds, model routing settings.</p>
          </div>
          <div class="flex gap-2">
            <label class="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer select-none">
              <input type="checkbox" v-model="showAllRuntimeConfigs" class="rounded" />
              Show inactive
            </label>
            <button class="btn-sm btn-primary" @click="openRuntimeForm(null)">+ Add Config</button>
          </div>
        </div>

        <div v-if="runtimeLoading" class="py-4 text-center muted text-sm">Loading…</div>
        <div v-else-if="!filteredRuntimeConfigs.length" class="py-6 text-center muted text-sm">
          No runtime configs found. Create one to define forecast engine parameters.
        </div>
        <table v-else class="admin-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Horizon</th>
              <th>Min History</th>
              <th>Constrained Handling</th>
              <th>Stock Class.</th>
              <th>Launch Routing</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rc in filteredRuntimeConfigs" :key="rc.id">
              <td class="font-medium">{{ rc.config_name }}</td>
              <td>{{ rc.forecast_horizon_weeks }}w</td>
              <td>{{ rc.min_history_weeks }}w</td>
              <td><code class="code-pill">{{ rc.constrained_weeks_handling }}</code></td>
              <td>
                <span class="bool-badge" :class="rc.enable_stock_classification ? 'bool-badge--yes' : 'bool-badge--no'">
                  {{ rc.enable_stock_classification ? 'on' : 'off' }}
                </span>
              </td>
              <td>
                <span class="bool-badge" :class="rc.enable_launch_routing ? 'bool-badge--yes' : 'bool-badge--no'">
                  {{ rc.enable_launch_routing ? 'on' : 'off' }}
                </span>
              </td>
              <td>
                <span class="status-badge" :class="rc.is_active ? 'status-badge--active' : 'status-badge--inactive'">
                  {{ rc.is_active ? 'active' : 'inactive' }}
                </span>
              </td>
              <td class="text-right">
                <button class="link-btn" @click="openRuntimeForm(rc)">Edit</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Runtime Config Form (inline) -->
      <section v-if="runtimeFormOpen" class="card card-body form-panel">
        <h4 class="section-title mb-4">{{ runtimeFormMode === 'create' ? 'New Runtime Config' : 'Edit Runtime Config' }}</h4>
        <form class="space-y-4" @submit.prevent="submitRuntimeForm">
          <div class="form-grid-2">
            <div>
              <label class="form-label">Config Name <span class="required">*</span></label>
              <input v-model="runtimeForm.config_name" type="text" class="input" required :disabled="runtimeFormMode === 'edit'" />
            </div>
            <div class="flex items-end gap-4 pb-1">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" v-model="runtimeForm.is_active" class="rounded" />
                Mark as active
              </label>
            </div>
          </div>
          <div class="form-grid-3">
            <div>
              <label class="form-label">Forecast Horizon (weeks)</label>
              <input v-model.number="runtimeForm.forecast_horizon_weeks" type="number" min="1" max="104" class="input" />
            </div>
            <div>
              <label class="form-label">Min History (weeks)</label>
              <input v-model.number="runtimeForm.min_history_weeks" type="number" min="1" max="260" class="input" />
            </div>
            <div>
              <label class="form-label">Min Sparse History (weeks)</label>
              <input v-model.number="runtimeForm.min_sparse_history_weeks" type="number" min="1" max="52" class="input" />
            </div>
          </div>
          <div class="form-grid-3">
            <div>
              <label class="form-label">Outlier Threshold</label>
              <input v-model.number="runtimeForm.outlier_threshold" type="number" min="0.01" max="2" step="0.01" class="input" />
            </div>
            <div>
              <label class="form-label">Zero Stock Threshold (units)</label>
              <input v-model.number="runtimeForm.zero_stock_units_threshold" type="number" min="0" step="0.5" class="input" />
            </div>
            <div>
              <label class="form-label">Low Stock Cover (weeks)</label>
              <input v-model.number="runtimeForm.low_stock_cover_weeks_threshold" type="number" min="0" step="0.5" class="input" />
            </div>
          </div>
          <div class="form-grid-3">
            <div>
              <label class="form-label">Constrained Weeks Handling</label>
              <select v-model="runtimeForm.constrained_weeks_handling" class="input">
                <option value="flag_only">flag_only</option>
                <option value="flag_and_exclude">flag_and_exclude</option>
                <option value="impute_unconstrained">impute_unconstrained</option>
              </select>
            </div>
            <div class="flex items-end gap-4 pb-1">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" v-model="runtimeForm.enable_stock_classification" class="rounded" />
                Enable stock classification
              </label>
            </div>
            <div class="flex items-end gap-4 pb-1">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" v-model="runtimeForm.enable_launch_routing" class="rounded" />
                Enable launch routing
              </label>
            </div>
          </div>

          <div v-if="runtimeFormError" class="error-msg">{{ runtimeFormError }}</div>
          <div class="flex gap-2">
            <button type="submit" class="btn-primary" :disabled="runtimeFormSaving">
              {{ runtimeFormSaving ? 'Saving…' : (runtimeFormMode === 'create' ? 'Create Config' : 'Save Changes') }}
            </button>
            <button type="button" class="btn-secondary" @click="closeRuntimeForm">Cancel</button>
          </div>
        </form>
      </section>

      <!-- Source Configs -->
      <section class="card card-body">
        <div class="card-section-header">
          <div>
            <h3 class="section-title">Source Configs</h3>
            <p class="muted text-sm mt-0.5">MySQL sales data connection and table references.</p>
          </div>
          <div class="flex gap-2">
            <label class="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer select-none">
              <input type="checkbox" v-model="showAllSourceConfigs" class="rounded" />
              Show inactive
            </label>
            <button class="btn-sm btn-primary" @click="openSourceForm(null)">+ Add Source</button>
          </div>
        </div>

        <div v-if="sourceLoading" class="py-4 text-center muted text-sm">Loading…</div>
        <div v-else-if="!filteredSourceConfigs.length" class="py-6 text-center muted text-sm">
          No source configs found.
        </div>
        <table v-else class="admin-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Host</th>
              <th>Database</th>
              <th>Schema</th>
              <th>Sales Table</th>
              <th>SOH Mode</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sc in filteredSourceConfigs" :key="sc.id">
              <td class="font-medium">{{ sc.source_name }}</td>
              <td class="text-sm muted">{{ sc.mysql_host || '(default)' }}{{ sc.mysql_port ? ':' + sc.mysql_port : '' }}</td>
              <td>{{ sc.mysql_database }}</td>
              <td>{{ sc.mysql_schema_name }}</td>
              <td><code class="code-pill">{{ sc.mysql_sales_table }}</code></td>
              <td><code class="code-pill">{{ sc.soh_source_mode }}</code></td>
              <td>
                <span class="status-badge" :class="sc.is_active ? 'status-badge--active' : 'status-badge--inactive'">
                  {{ sc.is_active ? 'active' : 'inactive' }}
                </span>
              </td>
              <td class="text-right">
                <button class="link-btn mr-2" @click="openSourceForm(sc)">Edit</button>
                <button class="link-btn" @click="toggleSourceActive(sc)">
                  {{ sc.is_active ? 'Deactivate' : 'Activate' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Source Config Create / Edit Form -->
      <section v-if="sourceFormOpen" class="card card-body form-panel">
        <h4 class="section-title mb-4">{{ sourceFormMode === 'create' ? 'New Source Config' : 'Edit Source Config' }}</h4>
        <form class="space-y-4" @submit.prevent="submitSourceForm">
          <div class="form-grid-2">
            <div>
              <label class="form-label">Source Name <span class="required">*</span></label>
              <input v-model="sourceForm.source_name" type="text" class="input" required placeholder="e.g. live_aymes" :disabled="sourceFormMode === 'edit'" />
            </div>
            <div>
              <label class="form-label">MySQL Database <span class="required">*</span></label>
              <input v-model="sourceForm.mysql_database" type="text" class="input" required placeholder="e.g. aymes_reports" />
            </div>
          </div>
          <div class="form-grid-3">
            <div>
              <label class="form-label">Host</label>
              <input v-model="sourceForm.mysql_host" type="text" class="input" placeholder="(uses app default)" />
            </div>
            <div>
              <label class="form-label">Port</label>
              <input v-model.number="sourceForm.mysql_port" type="number" class="input" placeholder="3306" />
            </div>
            <div>
              <label class="form-label">SOH Source Mode</label>
              <select v-model="sourceForm.soh_source_mode" class="input">
                <option value="external_current_source">external_current_source</option>
                <option value="mysql_soh_table">mysql_soh_table</option>
                <option value="none">none</option>
              </select>
            </div>
          </div>
          <div class="form-grid-2">
            <div>
              <label class="form-label">Schema Name</label>
              <input v-model="sourceForm.mysql_schema_name" type="text" class="input" />
            </div>
            <div>
              <label class="form-label">Sales Table</label>
              <input v-model="sourceForm.mysql_sales_table" type="text" class="input" />
            </div>
          </div>
          <div class="flex items-center gap-2">
            <input type="checkbox" id="srcActive" v-model="sourceForm.is_active" class="rounded" />
            <label for="srcActive" class="text-sm cursor-pointer">Active</label>
          </div>
          <div v-if="sourceFormError" class="error-msg">{{ sourceFormError }}</div>
          <div class="flex gap-2">
            <button type="submit" class="btn-primary" :disabled="sourceFormSaving">
              {{ sourceFormSaving ? 'Saving…' : (sourceFormMode === 'create' ? 'Create Source Config' : 'Save Changes') }}
            </button>
            <button type="button" class="btn-secondary" @click="closeSourceForm">Cancel</button>
          </div>
        </form>
      </section>

    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         RUNS SECTION
    ═══════════════════════════════════════════════════════════════ -->
    <template v-if="activeSection === 'runs'">

      <!-- Create Run Form -->
      <section class="card card-body">
        <div class="card-section-header">
          <div>
            <h3 class="section-title">Forecast Runs</h3>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select v-model="runsStatusFilter" class="input input-sm">
              <option value="">All statuses</option>
              <option value="queued">queued</option>
              <option value="running">running</option>
              <option value="success">success</option>
              <option value="failed">failed</option>
              <option value="partial">partial</option>
            </select>
            <div class="flex items-center gap-2">
              <input id="hideFailedRunsAdmin" v-model="hideFailedRuns" type="checkbox" class="rounded" />
              <label for="hideFailedRunsAdmin" class="text-sm cursor-pointer text-slate-700 m-0">Hide failed runs</label>
            </div>
            <button class="btn-sm btn-primary" @click="createRunFormOpen = !createRunFormOpen">+ New Run</button>
            <button class="btn-sm btn-secondary" @click="loadRuns">Refresh</button>
          </div>
        </div>

        <!-- Create Run inline form -->
        <div v-if="createRunFormOpen" class="form-panel mt-3 mb-4">
          <h4 class="text-sm font-semibold text-slate-700 mb-3">Create Queued Run</h4>
          <form class="space-y-3" @submit.prevent="submitCreateRun">
            <div class="form-grid-3">
              <div>
                <label class="form-label">Inference Date <span class="required">*</span></label>
                <input v-model="createRunForm.inference_date" type="date" class="input" required />
              </div>
              <div>
                <label class="form-label">Horizon (weeks)</label>
                <input v-model.number="createRunForm.horizon_weeks" type="number" min="1" max="104" class="input" />
              </div>
              <div>
                <label class="form-label">Run Type</label>
                <select v-model="createRunForm.run_type" class="input">
                  <option value="manual">manual</option>
                  <option value="scheduled">scheduled</option>
                </select>
              </div>
            </div>
            <div class="form-grid-2">
              <div>
                <label class="form-label">Source Config</label>
                <select v-model="createRunForm.source_config_id" class="input">
                  <option :value="null">— none —</option>
                  <option v-for="sc in allSourceConfigs" :key="sc.id" :value="sc.id">{{ sc.source_name }}</option>
                </select>
              </div>
              <div>
                <label class="form-label">Runtime Config</label>
                <select v-model="createRunForm.runtime_config_id" class="input">
                  <option :value="null">— none —</option>
                  <option v-for="rc in allRuntimeConfigs" :key="rc.id" :value="rc.id">{{ rc.config_name }}</option>
                </select>
              </div>
            </div>
            <div v-if="createRunError" class="error-msg">{{ createRunError }}</div>
            <div class="flex gap-2">
              <button type="submit" class="btn-primary" :disabled="createRunSaving">
                {{ createRunSaving ? 'Creating…' : 'Create Run' }}
              </button>
              <button type="button" class="btn-secondary" @click="createRunFormOpen = false">Cancel</button>
            </div>
          </form>
        </div>

        <!-- Runs table -->
        <div v-if="runsLoading" class="py-4 text-center muted text-sm">Loading…</div>
        <div v-else-if="!filteredRuns.length" class="py-6 text-center muted text-sm">
          No runs found{{ runsStatusFilter ? ' with status "' + runsStatusFilter + '"' : '' }}.
        </div>
        <div v-else-if="!runsTableRows.length" class="py-6 text-center muted text-sm">
          No runs to show with <strong>Hide failed runs</strong> on{{ runsStatusFilter ? ' and status "' + runsStatusFilter + '"' : '' }}.
          Uncheck the box or adjust the status filter.
        </div>
        <table v-else class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Inference Date</th>
              <th>Status</th>
              <th class="whitespace-nowrap">Fail note</th>
              <th>Type</th>
              <th>Horizon</th>
              <th>Created By</th>
              <th>Started</th>
              <th>Completed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="run in runsTableRows" :key="run.id">
              <tr
                class="cursor-pointer hover:bg-slate-50"
                :class="{ 'bg-blue-50': selectedRunId === run.id }"
                @click="toggleRunDetail(run)"
              >
                <td class="font-mono text-sm">#{{ run.id }}</td>
                <td>{{ run.inference_date }}</td>
                <td><span class="run-status-badge" :class="'run-status--' + runStatusCssKey(run.run_status)">{{ run.run_status }}</span></td>
                <td class="text-xs align-top">
                  <template v-if="isFailedRunStatus(run.run_status)">
                    <span
                      v-if="run.error_message && String(run.error_message).trim()"
                      class="fail-note-pill fail-note-pill--ok"
                      :title="String(run.error_message).trim()"
                    >Has reason</span>
                    <span v-else class="fail-note-pill fail-note-pill--warn">No reason</span>
                  </template>
                  <span v-else class="muted">—</span>
                </td>
                <td class="muted text-sm">{{ run.run_type }}</td>
                <td class="muted text-sm">{{ run.horizon_weeks }}w</td>
                <td class="muted text-sm">{{ run.created_by || '—' }}</td>
                <td class="muted text-sm">{{ fmtDatetime(run.started_at) }}</td>
                <td class="muted text-sm">{{ fmtDatetime(run.completed_at) }}</td>
                <td class="text-right">
                  <span class="muted text-xs">{{ selectedRunId === run.id ? '▲' : '▼' }}</span>
                </td>
              </tr>

              <!-- Inline Run Detail -->
              <tr v-if="selectedRunId === run.id" :key="'detail-' + run.id">
                <td colspan="10" class="run-detail-cell">
                  <div class="run-detail-panel">

                    <!-- Detail sub-tabs -->
                    <div class="detail-tabs">
                      <button class="detail-tab" :class="{ active: detailTab === 'meta' }" @click="detailTab = 'meta'">Metadata</button>
                      <button class="detail-tab" :class="{ active: detailTab === 'models' }" @click="switchDetailTab('models', run.id)">
                        Models
                        <span v-if="runModels.length" class="detail-tab-count">{{ runModels.length }}</span>
                      </button>
                      <button class="detail-tab" :class="{ active: detailTab === 'results' }" @click="switchDetailTab('results', run.id)">
                        Results
                        <span v-if="allResults.length" class="detail-tab-count">{{ allResults.length }}</span>
                      </button>
                      <button class="detail-tab" :class="{ active: detailTab === 'diag' }" @click="switchDetailTab('diag', run.id)">
                        Diagnostics
                        <span v-if="runDiagnostics.length" class="detail-tab-count">{{ runDiagnostics.length }}</span>
                      </button>
                      <button class="detail-tab" :class="{ active: detailTab === 'actions' }" @click="detailTab = 'actions'">Actions</button>
                      <button class="detail-tab" :class="{ active: detailTab === 'supply' }" @click="switchDetailTab('supply', run.id)">
                        Supply-Aware
                        <span v-if="supplyRows.length" class="detail-tab-count">{{ supplyRows.length }}</span>
                      </button>
                    </div>

                    <!-- Metadata -->
                    <div v-if="detailTab === 'meta'" class="detail-content">
                      <dl class="meta-grid">
                        <dt>Run ID</dt><dd>#{{ run.id }}</dd>
                        <dt>UUID</dt><dd class="font-mono text-xs break-all">{{ run.run_uuid }}</dd>
                        <dt>Status</dt><dd><span class="run-status-badge" :class="'run-status--' + runStatusCssKey(run.run_status)">{{ run.run_status }}</span></dd>
                        <dt>Inference Date</dt><dd>{{ run.inference_date }}</dd>
                        <dt>Horizon</dt><dd>{{ run.horizon_weeks }} weeks</dd>
                        <dt>Source Config</dt><dd>{{ sourceConfigName(run.source_config_id) }}</dd>
                        <dt>Runtime Config</dt><dd>{{ runtimeConfigName(run.runtime_config_id) }}</dd>
                        <dt>Created By</dt><dd>{{ run.created_by || '—' }}</dd>
                        <dt>Started At</dt><dd>{{ run.started_at || '—' }}</dd>
                        <dt>Completed At</dt><dd>{{ run.completed_at || '—' }}</dd>
                        <template v-if="isFailedRunStatus(run.run_status)">
                          <dt>Error</dt>
                          <dd
                            v-if="run.error_message && String(run.error_message).trim()"
                            class="error-msg-inline"
                          >{{ String(run.error_message).trim() }}</dd>
                          <dd v-else class="text-slate-500 italic text-sm">No reason recorded</dd>
                        </template>
                      </dl>

                      <!-- Execute panel -->
                      <div class="mt-4 p-3 bg-slate-50 rounded border border-slate-200">
                        <p class="text-sm font-medium text-slate-700 mb-1">Execute this run</p>
                        <p class="text-xs text-slate-500 mb-2">
                          New runs stay <strong>queued</strong> until you run the pipeline here (not automatic).
                          Use a <strong>Source config</strong> (MySQL sales connection) — not the same as <strong>Runtime config</strong> (e.g. «std»).
                        </p>
                        <div class="form-grid-3">
                          <div>
                            <label class="form-label">Source config (sales data)</label>
                            <select
                              v-if="allSourceConfigs.length"
                              v-model="executeForm.source_config_name"
                              class="input input-sm"
                            >
                              <option value="" disabled>— Choose source —</option>
                              <option
                                v-for="sc in allSourceConfigs"
                                :key="sc.id"
                                :value="sc.source_name"
                              >
                                {{ sc.source_name }}{{ sc.is_active ? '' : ' (inactive)' }}
                              </option>
                            </select>
                            <input
                              v-else
                              v-model="executeForm.source_config_name"
                              type="text"
                              class="input input-sm"
                              placeholder="Add a Source config under Configuration first"
                            />
                            <p v-if="!allSourceConfigs.length && !sourceLoading" class="text-xs text-amber-800 mt-1">
                              No source configs. Switch to the <strong>Configuration</strong> section and create <strong>Source Configs</strong> (separate from Runtime).
                            </p>
                          </div>
                          <div>
                            <label class="form-label">From Date</label>
                            <input v-model="executeForm.from_date" type="date" class="input input-sm" />
                          </div>
                          <div>
                            <label class="form-label">To Date</label>
                            <input v-model="executeForm.to_date" type="date" class="input input-sm" />
                          </div>
                        </div>
                        <div class="mt-2 flex gap-2 items-center">
                          <button
                            class="btn-sm btn-primary"
                            :disabled="executeLoading || !executeForm.source_config_name || !executeForm.from_date || !executeForm.to_date"
                            @click="executeRun(run.id)"
                          >{{ executeLoading ? 'Running…' : 'Execute' }}</button>
                          <OperationStatusPanel :operation="executeOperation.operation" class="w-full mt-2" />
                        </div>
                      </div>
                    </div>

                    <!-- Models -->
                    <div v-if="detailTab === 'models'" class="detail-content">
                      <div v-if="modelsLoading" class="muted text-sm py-3">Loading…</div>
                      <div v-else-if="!runModels.length" class="muted text-sm py-3">No model records yet — run has not been executed.</div>
                      <table v-else class="admin-table text-sm">
                        <thead>
                          <tr>
                            <th>Model</th>
                            <th>Family</th>
                            <th>Series Variant</th>
                            <th>Status</th>
                            <th>Attempted</th>
                            <th>Succeeded</th>
                            <th>Failed</th>
                            <th>MAPE</th>
                            <th>MAE</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="m in runModels" :key="m.id">
                            <td class="font-medium">{{ m.model_code }}</td>
                            <td>{{ m.model_family }}</td>
                            <td><code class="code-pill">{{ m.series_variant }}</code></td>
                            <td><span class="run-status-badge" :class="'run-status--' + runStatusCssKey(m.run_status)">{{ m.run_status }}</span></td>
                            <td>{{ m.products_attempted }}</td>
                            <td class="text-green-700">{{ m.products_succeeded }}</td>
                            <td :class="m.products_failed > 0 ? 'text-red-600' : ''">{{ m.products_failed }}</td>
                            <td>{{ m.mape !== null ? (m.mape * 100).toFixed(1) + '%' : '—' }}</td>
                            <td>{{ m.mae !== null ? m.mae.toFixed(2) : '—' }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <!-- Results -->
                    <div v-if="detailTab === 'results'" class="detail-content">
                      <!-- Filters -->
                      <div class="flex gap-2 mb-3 flex-wrap items-center">
                        <input v-model="resultsProductFilter" type="text" placeholder="Filter product…" class="input input-sm w-36" />
                        <input v-model="resultsModelFilter" type="text" placeholder="Filter model…" class="input input-sm w-36" />
                        <label class="flex items-center gap-1.5 text-sm cursor-pointer select-none">
                          <input type="checkbox" v-model="resultsBestOnly" class="rounded" />
                          Best model only
                        </label>
                        <button class="btn-sm btn-secondary" @click="loadResults(run.id)">Load / Refresh</button>
                        <span v-if="allResults.length" class="text-xs muted self-center">{{ filteredResults.length }} rows</span>
                      </div>
                      <p v-if="allResults.length && !resultsLoading" class="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 mb-3">
                        Horizon totals sum <strong>all visible rows</strong>. Turn on <strong>Best model only</strong> if you see double-counting across models for the same week.
                      </p>
                      <!-- Evidence: stats + charts (same data as table — review before export) -->
                      <div v-if="allResults.length && !resultsLoading && filteredResults.length" class="results-evidence space-y-4 mb-4">
                        <div class="results-evidence__stats">
                          <div class="evidence-stat">
                            <span class="evidence-stat__label">Rows (filtered)</span>
                            <span class="evidence-stat__val">{{ resultsStats.rowCount.toLocaleString() }}</span>
                          </div>
                          <div class="evidence-stat">
                            <span class="evidence-stat__label">Distinct products</span>
                            <span class="evidence-stat__val">{{ resultsStats.skuCount.toLocaleString() }}</span>
                          </div>
                          <div class="evidence-stat">
                            <span class="evidence-stat__label">Forecast horizon</span>
                            <span class="evidence-stat__val text-sm leading-tight">{{ resultsStats.weekMin }} → {{ resultsStats.weekMax }}</span>
                          </div>
                          <div class="evidence-stat">
                            <span class="evidence-stat__label">Σ forecast units (filtered)</span>
                            <span class="evidence-stat__val">{{ resultsStats.totalForecast.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</span>
                          </div>
                        </div>
                        <div class="results-chart-card">
                          <p class="text-sm font-medium text-slate-800 mb-1">Total forecast units by week</p>
                          <p class="text-xs text-slate-500 mb-2">Sum of <code>forecast_units</code> in the table below (after filters).</p>
                          <div class="results-chart-canvas">
                            <canvas ref="horizonChartCanvas" />
                          </div>
                        </div>
                        <div class="results-chart-card">
                          <div class="flex flex-wrap gap-2 items-end mb-2">
                            <div>
                              <label class="form-label text-xs mb-0.5">Weekly series — one product</label>
                              <select v-model="resultsChartSku" class="input input-sm min-w-56 max-w-md">
                                <option value="">— Select SKU —</option>
                                <option v-for="opt in resultsChartSkuOptions" :key="opt.code" :value="opt.code">
                                  {{ opt.code }} (Σ {{ opt.total.toLocaleString(undefined, { maximumFractionDigits: 0 }) }})
                                </option>
                              </select>
                            </div>
                          </div>
                          <p class="text-xs text-slate-500 mb-2">Forecast vs actual (if the engine stored actuals) for the selected row set.</p>
                          <div v-show="!resultsChartSku" class="text-sm text-slate-500 py-6 text-center border border-dashed border-slate-200 rounded-md">
                            Choose a SKU to plot a weekly line chart.
                          </div>
                          <div v-show="resultsChartSku" class="results-chart-canvas">
                            <canvas ref="skuChartCanvas" />
                          </div>
                        </div>
                        <p class="text-xs text-slate-500">
                          Use these views to sanity-check output, then <strong>Actions → Export Files</strong> (CSV + manifest) or legacy export when ready.
                        </p>
                      </div>
                      <div v-if="resultsLoading" class="py-4 text-center muted text-sm">Loading…</div>
                      <div v-else-if="!allResults.length && !resultsLoading" class="py-8 text-center muted text-sm">
                        <p class="font-medium">No results loaded</p>
                        <p class="text-xs mt-1">Click "Load / Refresh" to fetch forecast results for this run.<br />Results are only available after the run has been executed.</p>
                      </div>
                      <div v-else-if="filteredResults.length === 0" class="py-6 text-center muted text-sm">
                        No rows match the current filters.
                      </div>
                      <div v-else class="results-table-wrap">
                        <table class="admin-table text-xs">
                          <thead>
                            <tr>
                              <th>Product</th>
                              <th>Name</th>
                              <th>Week</th>
                              <th>Model</th>
                              <th>Variant</th>
                              <th class="text-right">Forecast</th>
                              <th class="text-right">Actual</th>
                              <th class="text-right">Interpolated</th>
                              <th class="text-right">MAPE</th>
                              <th>Best</th>
                              <th>Pred Best</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="r in filteredResults" :key="r.id" :class="r.is_best_model ? 'results-row--best' : ''">
                              <td class="font-mono font-medium">{{ r.product_code }}</td>
                              <td class="muted">{{ r.product_name || '—' }}</td>
                              <td class="tabular-nums">{{ r.forecast_week }}</td>
                              <td>{{ r.model_name }}</td>
                              <td><code class="code-pill">{{ r.model_details }}</code></td>
                              <td class="text-right tabular-nums font-medium">{{ fmtNum(r.forecast_units) }}</td>
                              <td class="text-right tabular-nums muted">{{ fmtNum(r.actual_units) }}</td>
                              <td class="text-right tabular-nums muted">{{ fmtNum(r.interpolated_units) }}</td>
                              <td class="text-right tabular-nums">{{ r.mape !== null ? (r.mape * 100).toFixed(1) + '%' : '—' }}</td>
                              <td>
                                <span v-if="r.is_best_model" class="bool-badge bool-badge--yes">✓ best</span>
                                <span v-else class="muted text-xs">—</span>
                              </td>
                              <td>
                                <span v-if="r.predicted_best_model_bool" class="bool-badge bool-badge--yes">✓</span>
                                <span v-else class="muted text-xs">—</span>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <!-- Diagnostics -->
                    <div v-if="detailTab === 'diag'" class="detail-content">
                      <div class="flex gap-2 mb-3">
                        <select v-model="diagLevelFilter" @change="loadDiagnostics(run.id)" class="input input-sm">
                          <option value="">All levels</option>
                          <option value="info">info</option>
                          <option value="warning">warning</option>
                          <option value="error">error</option>
                        </select>
                        <span class="text-sm muted self-center">{{ runDiagnostics.length }} records</span>
                      </div>
                      <div v-if="diagLoading" class="muted text-sm py-3">Loading…</div>
                      <div v-else-if="!runDiagnostics.length" class="muted text-sm py-3">No diagnostics found.</div>
                      <div v-else class="diag-list">
                        <div v-for="d in runDiagnostics" :key="d.id" class="diag-row" :class="'diag-row--' + d.diagnostic_level">
                          <span class="diag-level">{{ d.diagnostic_level }}</span>
                          <span class="diag-type muted">{{ d.diagnostic_type }}</span>
                          <span v-if="d.product_code" class="diag-sku">{{ d.product_code }}</span>
                          <span class="diag-msg">{{ d.message }}</span>
                        </div>
                      </div>
                    </div>

                    <!-- Actions -->
                    <div v-if="detailTab === 'actions'" class="detail-content space-y-4">
                      <!-- Export Legacy -->
                      <div class="action-card">
                        <div class="action-card__header">
                          <strong>Export to Legacy Tables</strong>
                          <p class="muted text-sm mt-0.5">Write results to aymes_reports.aymes_demand_planning_forecast_by_model_new.</p>
                        </div>
                        <div class="flex gap-2 items-center mt-2">
                          <label class="flex items-center gap-1.5 text-sm cursor-pointer">
                            <input type="checkbox" v-model="exportLegacySafeReplace" class="rounded" />
                            Safe replace (promote staging → live)
                          </label>
                          <button class="btn-sm btn-primary" :disabled="actionLoading === 'export-legacy'" @click="doExportLegacy(run.id)">
                            {{ actionLoading === 'export-legacy' ? 'Exporting…' : 'Export Legacy' }}
                          </button>
                        </div>
                        <div v-if="actionResults['export-legacy']" class="action-result mt-2">
                          <pre class="result-json">{{ JSON.stringify(actionResults['export-legacy'], null, 2) }}</pre>
                        </div>
                        <OperationStatusPanel v-if="actionOperation.operation.id === 'export-legacy'" :operation="actionOperation.operation" class="mt-2" />
                      </div>

                      <!-- Export Files -->
                      <div class="action-card">
                        <div class="action-card__header">
                          <strong>Export Files (CSV + Manifest)</strong>
                          <p class="muted text-sm mt-0.5">Generate legacy-compatible CSV files and run_manifest.json.</p>
                        </div>
                        <div class="mt-2">
                          <button class="btn-sm btn-primary" :disabled="actionLoading === 'export-files'" @click="doExportFiles(run.id)">
                            {{ actionLoading === 'export-files' ? 'Exporting…' : 'Export Files' }}
                          </button>
                        </div>
                        <div v-if="actionResults['export-files']" class="action-result mt-2">
                          <p class="text-sm text-slate-700">Output path: <code>{{ (actionResults['export-files'] as any).output_path }}</code></p>
                          <p class="text-sm muted mt-1">Files generated: {{ ((actionResults['export-files'] as any).files_generated || []).join(', ') }}</p>
                        </div>
                        <OperationStatusPanel v-if="actionOperation.operation.id === 'export-files'" :operation="actionOperation.operation" class="mt-2" />
                      </div>

                      <!-- Parity Validation -->
                      <div class="action-card" :class="{ 'action-card--disabled': !legacyDbStatus?.can_connect }">
                        <div class="action-card__header">
                          <strong>Parity Validation</strong>
                          <p class="muted text-sm mt-0.5">
                            Compare output against legacy Vertex table.
                            <span v-if="!legacyDbStatus?.can_connect" class="text-amber-600 font-medium">
                              Requires whitelisted MySQL access — not yet available.
                            </span>
                          </p>
                        </div>
                        <div class="flex gap-2 items-center mt-2 flex-wrap">
                          <label class="form-label mb-0 text-sm">Sample size</label>
                          <input v-model.number="paritySampleSize" type="number" min="10" max="500" class="input input-sm w-20" :disabled="!legacyDbStatus?.can_connect" />
                          <span class="text-xs muted">max 500</span>
                          <button
                            class="btn-sm"
                            :class="legacyDbStatus?.can_connect ? 'btn-primary' : 'btn-disabled'"
                            :disabled="!legacyDbStatus?.can_connect || actionLoading === 'validate-parity'"
                            @click="doValidateParity(run.id)"
                          >{{ actionLoading === 'validate-parity' ? 'Validating…' : 'Validate Parity' }}</button>
                        </div>
                        <div v-if="actionResults['validate-parity']" class="action-result mt-2">
                          <pre class="result-json">{{ JSON.stringify(actionResults['validate-parity'], null, 2) }}</pre>
                        </div>
                        <OperationStatusPanel v-if="actionOperation.operation.id === 'validate-parity'" :operation="actionOperation.operation" class="mt-2" />
                      </div>

                      <!-- Manual Status Override -->
                      <div class="action-card">
                        <div class="action-card__header">
                          <strong>Manual Status Override</strong>
                          <p class="muted text-sm mt-0.5">Force-set the run status. Use with care — this bypasses normal lifecycle transitions.</p>
                        </div>
                        <div class="flex gap-2 items-center mt-2 flex-wrap">
                          <select v-model="statusOverrideValue" class="input input-sm w-36">
                            <option value="">— select status —</option>
                            <option value="queued">queued</option>
                            <option value="running">running</option>
                            <option value="success">success</option>
                            <option value="partial">partial</option>
                            <option value="failed">failed</option>
                          </select>
                          <button
                            class="btn-sm btn-secondary"
                            :disabled="!statusOverrideValue || statusOverrideLoading"
                            @click="doStatusOverride(run.id)"
                          >{{ statusOverrideLoading ? 'Updating…' : 'Set Status' }}</button>
                        </div>
                        <div v-if="statusOverrideValue === 'failed'" class="mt-2 max-w-lg">
                          <label class="form-label text-xs">Error message (optional)</label>
                          <textarea
                            v-model="statusOverrideErrorMessage"
                            class="input input-sm w-full resize-y"
                            placeholder="Reason for marking failed (audit / test-bed cleanup)"
                            rows="3"
                          />
                        </div>
                        <OperationStatusPanel :operation="statusOverrideOperation.operation" class="mt-2" />
                      </div>
                    </div>

                    <!-- Supply-Aware Forecast -->
                    <div v-if="detailTab === 'supply'" class="detail-content">
                      <div class="supply-header">
                        <div>
                          <p class="text-sm text-slate-600">
                            Supply-adjusted output — base forecast constrained by available stock (SOH + inbound).
                            The base forecast in the SAP/legacy pipeline is <strong>not modified</strong>.
                          </p>
                          <p v-if="supplyMeta" class="text-xs muted mt-1">
                            {{ supplyMeta.rows_written }} rows &middot;
                            {{ supplyMeta.products_processed }} products &middot;
                            source: <code>{{ supplyMeta.stock_source }}</code> &middot;
                            stockouts: {{ supplyMeta.stockout_count }} &middot;
                            excess: {{ supplyMeta.excess_count }}
                          </p>
                        </div>
                        <div class="flex gap-2 items-center flex-wrap">
                          <label class="flex items-center gap-1.5 text-sm cursor-pointer select-none">
                            <input type="checkbox" v-model="supplyUseMock" class="rounded" />
                            Use mock stock data
                          </label>
                          <button
                            class="btn-sm btn-primary"
                            :disabled="supplyComputeLoading"
                            @click="doComputeSupply(run.id)"
                          >{{ supplyComputeLoading ? 'Computing…' : 'Compute Supply-Adjusted' }}</button>
                          <button v-if="supplyRows.length" class="btn-sm btn-secondary" @click="loadSupplyRows(run.id)">Refresh</button>
                        </div>
                      </div>

                      <OperationStatusPanel :operation="supplyComputeOperation.operation" class="mt-2" />

                      <!-- Filters -->
                      <div v-if="supplyRows.length || supplyLoading" class="flex gap-3 mt-3 flex-wrap items-center">
                        <input v-model="supplyProductFilter" type="text" placeholder="Filter by product…" class="input input-sm w-40" />
                        <label class="flex items-center gap-1.5 text-sm cursor-pointer select-none">
                          <input type="checkbox" v-model="supplyStockoutFilter" class="rounded" />
                          Stockouts only
                        </label>
                        <label class="flex items-center gap-1.5 text-sm cursor-pointer select-none">
                          <input type="checkbox" v-model="supplyExcessFilter" class="rounded" />
                          Excess only
                        </label>
                        <button class="btn-sm btn-secondary" @click="loadSupplyRows(run.id)">Apply</button>
                        <span class="text-xs muted">{{ supplyRows.length }} rows shown</span>
                      </div>

                      <div v-if="supplyLoading" class="py-4 text-center muted text-sm">Loading…</div>
                      <div v-else-if="!supplyRows.length && !supplyComputeLoading" class="py-6 text-center muted text-sm">
                        No supply-adjusted data. Click "Compute Supply-Adjusted" to generate it.
                        <br />
                        <span class="text-xs">Check "Use mock stock data" to test without real SOH/inbound.</span>
                      </div>
                      <div v-else-if="supplyRows.length" class="mt-3 supply-table-wrap">
                        <table class="admin-table text-sm">
                          <thead>
                            <tr>
                              <th>Product</th>
                              <th>Warehouse</th>
                              <th>Week</th>
                              <th class="text-right">Base Forecast</th>
                              <th class="text-right">SOH</th>
                              <th class="text-right">Inbound</th>
                              <th class="text-right">Available</th>
                              <th class="text-right">Adjusted Forecast</th>
                              <th>Stockout</th>
                              <th>Excess</th>
                              <th class="text-right text-xs muted">Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="row in supplyRows" :key="row.id" :class="{
                              'supply-row--stockout': row.stockout_flag,
                              'supply-row--excess': row.excess_stock_flag,
                            }">
                              <td class="font-medium">{{ row.product_code }}</td>
                              <td class="muted">{{ row.warehouse_code || '—' }}</td>
                              <td>{{ row.forecast_week }}</td>
                              <td class="text-right">{{ fmtNum(row.base_forecast) }}</td>
                              <td class="text-right muted">{{ fmtNum(row.stock_on_hand) }}</td>
                              <td class="text-right muted">{{ fmtNum(row.inbound_orders) }}</td>
                              <td class="text-right font-medium">{{ fmtNum(row.available_stock) }}</td>
                              <td class="text-right font-semibold" :class="row.stockout_flag ? 'text-red-600' : 'text-green-700'">
                                {{ fmtNum(row.adjusted_forecast) }}
                              </td>
                              <td>
                                <span v-if="row.stockout_flag" class="flag-badge flag-badge--red">stockout</span>
                                <span v-else class="muted text-xs">—</span>
                              </td>
                              <td>
                                <span v-if="row.excess_stock_flag" class="flag-badge flag-badge--amber">excess</span>
                                <span v-else class="muted text-xs">—</span>
                              </td>
                              <td class="text-right text-xs muted">{{ row.stock_source }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </section>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         DEBUG & HEALTH SECTION
    ═══════════════════════════════════════════════════════════════ -->
    <template v-if="activeSection === 'debug'">

      <!-- Legacy Output Health -->
      <section class="card card-body">
        <div class="card-section-header">
          <div>
            <h3 class="section-title">Legacy Output — Connection Health</h3>
            <p class="muted text-sm mt-0.5">Reports the connectivity status of the aymes_reports legacy MySQL database.</p>
          </div>
          <button class="btn-sm btn-secondary" @click="loadLegacyHealth">Recheck</button>
        </div>
        <div v-if="!legacyDbStatus" class="muted text-sm py-3">Checking…</div>
        <div v-else class="debug-health-row">
          <span class="debug-health-dot" :class="legacyDbStatus.can_connect ? 'dot--ok' : 'dot--err'"></span>
          <span class="font-medium text-sm">{{ legacyDbStatus.can_connect ? 'Connected' : 'Not connected' }}</span>
          <span v-if="legacyDbStatus.can_connect" class="text-xs muted ml-2">Parity validation is available.</span>
          <span v-else class="text-xs text-amber-700 ml-2">{{ (legacyDbStatus.errors || [])[0] || 'Unknown error' }}</span>
        </div>
      </section>

      <!-- Data Source Debug Views -->
      <section class="card card-body">
        <div class="card-section-header">
          <div>
            <h3 class="section-title">Data Source Debug Views</h3>
            <p class="muted text-sm mt-0.5">Inspect the underlying data that feeds into the forecast engine. These call live backend endpoints.</p>
          </div>
        </div>
        <div class="space-y-4">
          <!-- Sales Source Weekly -->
          <div class="debug-panel">
            <div class="debug-panel__header">
              <div>
                <p class="font-medium text-sm">Sales Source Weekly</p>
                <p class="text-xs muted mt-0.5">Raw weekly sales data as seen by the engine — <code class="code-pill">GET /v1/forecast/views/sales-source-weekly</code></p>
              </div>
              <button class="btn-sm btn-secondary" :disabled="debugSalesLoading" @click="loadDebugSales">
                {{ debugSalesLoading ? 'Loading…' : 'Fetch' }}
              </button>
            </div>
            <div v-if="debugSalesError" class="error-msg mt-2">{{ debugSalesError }}</div>
            <div v-if="debugSalesData" class="mt-2">
              <p class="text-xs muted mb-1">{{ Array.isArray(debugSalesData) ? debugSalesData.length + ' rows returned' : '' }}</p>
              <pre class="result-json">{{ JSON.stringify(Array.isArray(debugSalesData) ? debugSalesData.slice(0, 20) : debugSalesData, null, 2) }}</pre>
              <p v-if="Array.isArray(debugSalesData) && debugSalesData.length > 20" class="text-xs muted mt-1">Showing first 20 of {{ debugSalesData.length }} rows.</p>
            </div>
          </div>

          <!-- Training Base -->
          <div class="debug-panel">
            <div class="debug-panel__header">
              <div>
                <p class="font-medium text-sm">Training Base View</p>
                <p class="text-xs muted mt-0.5">Processed training series before model fitting — <code class="code-pill">GET /v1/forecast/views/training-base</code></p>
              </div>
              <button class="btn-sm btn-secondary" :disabled="debugTrainingLoading" @click="loadDebugTraining">
                {{ debugTrainingLoading ? 'Loading…' : 'Fetch' }}
              </button>
            </div>
            <div v-if="debugTrainingError" class="error-msg mt-2">{{ debugTrainingError }}</div>
            <div v-if="debugTrainingData" class="mt-2">
              <p class="text-xs muted mb-1">{{ Array.isArray(debugTrainingData) ? debugTrainingData.length + ' rows returned' : '' }}</p>
              <pre class="result-json">{{ JSON.stringify(Array.isArray(debugTrainingData) ? debugTrainingData.slice(0, 20) : debugTrainingData, null, 2) }}</pre>
              <p v-if="Array.isArray(debugTrainingData) && debugTrainingData.length > 20" class="text-xs muted mt-1">Showing first 20 of {{ debugTrainingData.length }} rows.</p>
            </div>
          </div>
        </div>
      </section>

    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Chart, registerables } from 'chart.js'
import api from '../../api/client'
import OperationStatusPanel from '@/components/common/OperationStatusPanel.vue'
import { useOperation } from '@/composables/useOperation'

Chart.register(...registerables)

// ─── Types ───────────────────────────────────────────────────────────────────

interface SourceConfig {
  id: number
  source_name: string
  mysql_database: string
  mysql_host: string | null
  mysql_port: number | null
  mysql_schema_name: string
  mysql_sales_table: string
  soh_source_mode: string
  is_active: boolean
}

interface RuntimeConfig {
  id: number
  config_name: string
  is_active: boolean
  forecast_horizon_weeks: number
  min_history_weeks: number
  outlier_threshold: number | null
  zero_stock_units_threshold: number | null
  low_stock_cover_weeks_threshold: number | null
  constrained_weeks_handling: string
  min_sparse_history_weeks: number
  enable_stock_classification: boolean
  enable_launch_routing: boolean
  best_model_tie_break_order: string[] | null
}

interface ForecastRun {
  id: number
  run_uuid: string
  run_status: string
  run_type: string
  inference_date: string
  horizon_weeks: number
  source_config_id: number | null
  runtime_config_id: number | null
  error_message: string | null
  created_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

interface RunModel {
  id: number
  run_id: number
  model_code: string
  model_family: string
  strategy: string | null
  series_variant: string
  run_status: string
  products_attempted: number
  products_succeeded: number
  products_failed: number
  mape: number | null
  mae: number | null
}

interface Diagnostic {
  id: number
  run_id: number
  product_code: string | null
  warehouse_code: string | null
  diagnostic_type: string
  diagnostic_level: string
  message: string
}

interface ResultRow {
  id: number
  product_code: string
  product_name: string | null
  forecast_week: string
  model_name: string
  model_details: string
  forecast_units: number | null
  actual_units: number | null
  interpolated_units: number | null
  is_best_model: boolean | null
  predicted_best_model_bool: boolean | null
  mape: number | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const activeSection = ref<'configs' | 'runs' | 'debug'>('configs')

const legacyDbStatus = ref<{ can_connect: boolean; errors?: string[] } | null>(null)

// Source configs
const allSourceConfigs = ref<SourceConfig[]>([])
const sourceLoading = ref(false)
const showAllSourceConfigs = ref(false)
const sourceFormOpen = ref(false)
const sourceFormMode = ref<'create' | 'edit'>('create')
const editingSourceId = ref<number | null>(null)
const sourceFormSaving = ref(false)
const sourceFormError = ref('')
const sourceForm = ref({
  source_name: '', mysql_database: '', mysql_host: '', mysql_port: null as number | null,
  mysql_schema_name: 'aymes_reports', mysql_sales_table: 'adhl_data_daily',
  soh_source_mode: 'external_current_source', is_active: true,
})

// Runtime configs
const allRuntimeConfigs = ref<RuntimeConfig[]>([])
const runtimeLoading = ref(false)
const showAllRuntimeConfigs = ref(false)
const runtimeFormOpen = ref(false)
const runtimeFormMode = ref<'create' | 'edit'>('create')
const runtimeFormSaving = ref(false)
const runtimeFormError = ref('')
const editingRuntimeId = ref<number | null>(null)
const runtimeForm = ref({
  config_name: '', is_active: false,
  forecast_horizon_weeks: 52, min_history_weeks: 60,
  outlier_threshold: 0.5, zero_stock_units_threshold: 5.0,
  low_stock_cover_weeks_threshold: 2.0, constrained_weeks_handling: 'flag_only',
  min_sparse_history_weeks: 12, enable_stock_classification: true, enable_launch_routing: true,
})

// Runs
const allRuns = ref<ForecastRun[]>([])
const runsLoading = ref(false)
const runsStatusFilter = ref('')
/** Client-side only after status filter; does not change API requests. */
const hideFailedRuns = ref(false)
const createRunFormOpen = ref(false)
const createRunSaving = ref(false)
const createRunError = ref('')
const createRunForm = ref({
  inference_date: '', horizon_weeks: 52, run_type: 'manual',
  source_config_id: null as number | null, runtime_config_id: null as number | null,
})

// Run detail
const selectedRunId = ref<number | null>(null)
const detailTab = ref<'meta' | 'models' | 'results' | 'diag' | 'actions' | 'supply'>('meta')
const runModels = ref<RunModel[]>([])
const runDiagnostics = ref<Diagnostic[]>([])
const modelsLoading = ref(false)
const diagLoading = ref(false)
const diagLevelFilter = ref('')

// Results tab
const allResults = ref<ResultRow[]>([])
const resultsLoading = ref(false)
const resultsProductFilter = ref('')
const resultsModelFilter = ref('')
const resultsBestOnly = ref(false)
const resultsChartSku = ref('')
const horizonChartCanvas = ref<HTMLCanvasElement | null>(null)
const skuChartCanvas = ref<HTMLCanvasElement | null>(null)
let horizonChart: Chart | null = null
let skuChart: Chart | null = null

// Execute
const executeForm = ref({ source_config_name: '', from_date: '', to_date: '' })
const executeOperation = useOperation('Execute forecast run')
const executeLoading = executeOperation.isRunning

// Actions
const exportLegacySafeReplace = ref(false)
const paritySampleSize = ref(100)
const actionOperation = useOperation('Forecast run action')
const actionLoading = computed(() => actionOperation.isRunning.value ? actionOperation.operation.id || '' : '')
const actionResults = ref<Record<string, unknown>>({})

// Status override
const statusOverrideValue = ref('')
const statusOverrideErrorMessage = ref('')
const statusOverrideOperation = useOperation('Override forecast run status')
const statusOverrideLoading = statusOverrideOperation.isRunning

watch(statusOverrideValue, (v) => {
  if (v !== 'failed') statusOverrideErrorMessage.value = ''
})

// Supply-aware forecast
interface SupplyRow {
  id: number
  run_id: number
  product_code: string
  warehouse_code: string | null
  forecast_week: string
  base_forecast: number
  stock_on_hand: number | null
  inbound_orders: number | null
  available_stock: number | null
  adjusted_forecast: number | null
  stockout_flag: boolean
  excess_stock_flag: boolean
  stock_source: string
}
const supplyRows = ref<SupplyRow[]>([])
const supplyLoading = ref(false)
const supplyComputeOperation = useOperation('Compute supply-adjusted forecast')
const supplyComputeLoading = supplyComputeOperation.isRunning
const supplyUseMock = ref(false)
const supplyProductFilter = ref('')
const supplyStockoutFilter = ref(false)
const supplyExcessFilter = ref(false)
const supplyMeta = ref<Record<string, unknown> | null>(null)

// Debug panel
const debugSalesData = ref<unknown>(null)
const debugSalesLoading = ref(false)
const debugSalesError = ref('')
const debugTrainingData = ref<unknown>(null)
const debugTrainingLoading = ref(false)
const debugTrainingError = ref('')

// ─── Run status helpers (API may vary casing) ────────────────────────────────

function runStatusCssKey(status: string | null | undefined): string {
  return String(status ?? '').trim().toLowerCase()
}

function isFailedRunStatus(status: string | null | undefined): boolean {
  return runStatusCssKey(status) === 'failed'
}

// ─── Computed ────────────────────────────────────────────────────────────────

const filteredSourceConfigs = computed(() =>
  showAllSourceConfigs.value ? allSourceConfigs.value : allSourceConfigs.value.filter(sc => sc.is_active)
)

const filteredRuntimeConfigs = computed(() =>
  showAllRuntimeConfigs.value ? allRuntimeConfigs.value : allRuntimeConfigs.value.filter(rc => rc.is_active)
)

const filteredRuns = computed(() => {
  const f = runsStatusFilter.value?.trim().toLowerCase()
  if (!f) return allRuns.value
  return allRuns.value.filter((r) => runStatusCssKey(r.run_status) === f)
})

const runsTableRows = computed(() => {
  const rows = filteredRuns.value
  if (!hideFailedRuns.value) return rows
  return rows.filter((r) => !isFailedRunStatus(r.run_status))
})

const filteredResults = computed(() => {
  let rows = allResults.value
  const pf = resultsProductFilter.value.trim().toLowerCase()
  const mf = resultsModelFilter.value.trim().toLowerCase()
  if (pf) rows = rows.filter(r => r.product_code.toLowerCase().includes(pf) || (r.product_name ?? '').toLowerCase().includes(pf))
  if (mf) rows = rows.filter(r => r.model_details.toLowerCase().includes(mf) || r.model_name.toLowerCase().includes(mf))
  if (resultsBestOnly.value) rows = rows.filter(r => r.is_best_model === true)
  return rows
})

const resultsStats = computed(() => {
  const rows = filteredResults.value
  const rowCount = rows.length
  const skuCount = new Set(rows.map((r) => r.product_code)).size
  const weeks = [...new Set(rows.map((r) => r.forecast_week))].filter(Boolean).sort()
  const weekMin = weeks[0] ?? '—'
  const weekMax = weeks.length ? weeks[weeks.length - 1] : '—'
  const totalForecast = rows.reduce((s, r) => s + (r.forecast_units ?? 0), 0)
  return { rowCount, skuCount, weekMin, weekMax, totalForecast }
})

/** Top products by sum of forecast in current filter (for chart SKU picker). */
const resultsChartSkuOptions = computed(() => {
  const m = new Map<string, { code: string; total: number }>()
  for (const r of filteredResults.value) {
    const t = (m.get(r.product_code)?.total ?? 0) + (r.forecast_units ?? 0)
    m.set(r.product_code, { code: r.product_code, total: t })
  }
  return [...m.values()].sort((a, b) => b.total - a.total).slice(0, 120)
})

watch(
  resultsChartSkuOptions,
  (opts) => {
    if (resultsChartSku.value && !opts.some((o) => o.code === resultsChartSku.value)) {
      resultsChartSku.value = ''
    }
  },
  { deep: true },
)

watch(runsTableRows, (rows) => {
  const id = selectedRunId.value
  if (id != null && !rows.some((r) => r.id === id)) selectedRunId.value = null
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtDatetime(dt: string | null): string {
  if (!dt) return '—'
  return dt.replace('T', ' ').slice(0, 16)
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function sourceConfigName(id: number | null): string {
  if (id === null) return '—'
  return allSourceConfigs.value.find(sc => sc.id === id)?.source_name ?? `id:${id}`
}

function runtimeConfigName(id: number | null): string {
  if (id === null) return '—'
  return allRuntimeConfigs.value.find(rc => rc.id === id)?.config_name ?? `id:${id}`
}

function apiError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return String(err)
}

// ─── Load functions ───────────────────────────────────────────────────────────

async function loadLegacyHealth() {
  try {
    const { data } = await api.get('/v1/forecast/legacy-output/health')
    legacyDbStatus.value = data
  } catch {
    legacyDbStatus.value = { can_connect: false, errors: ['Health check request failed'] }
  }
}

async function loadSourceConfigs() {
  sourceLoading.value = true
  try {
    const { data } = await api.get<SourceConfig[]>('/v1/forecast/source-configs?active_only=false')
    allSourceConfigs.value = data
  } catch (err) {
    console.error('Failed to load source configs', err)
  } finally {
    sourceLoading.value = false
  }
}

async function loadRuntimeConfigs() {
  runtimeLoading.value = true
  try {
    const { data } = await api.get<RuntimeConfig[]>('/v1/forecast/runtime-configs?active_only=false')
    allRuntimeConfigs.value = data
  } catch (err) {
    console.error('Failed to load runtime configs', err)
  } finally {
    runtimeLoading.value = false
  }
}

async function loadRuns() {
  runsLoading.value = true
  try {
    const { data } = await api.get<ForecastRun[]>('/v1/forecast/runs?limit=100')
    allRuns.value = data
  } catch (err) {
    console.error('Failed to load runs', err)
  } finally {
    runsLoading.value = false
  }
}

async function loadModels(runId: number) {
  modelsLoading.value = true
  try {
    const { data } = await api.get<RunModel[]>(`/v1/forecast/runs/${runId}/run-models`)
    runModels.value = data
  } catch (err) {
    console.error('Failed to load run models', err)
  } finally {
    modelsLoading.value = false
  }
}

async function loadDiagnostics(runId: number) {
  diagLoading.value = true
  try {
    const params = diagLevelFilter.value ? `?level=${diagLevelFilter.value}&limit=200` : '?limit=200'
    const { data } = await api.get<Diagnostic[]>(`/v1/forecast/runs/${runId}/diagnostics${params}`)
    runDiagnostics.value = data
  } catch (err) {
    console.error('Failed to load diagnostics', err)
  } finally {
    diagLoading.value = false
  }
}

// ─── Runtime Config Form ──────────────────────────────────────────────────────

function openRuntimeForm(rc: RuntimeConfig | null) {
  runtimeFormError.value = ''
  if (rc === null) {
    runtimeFormMode.value = 'create'
    editingRuntimeId.value = null
    Object.assign(runtimeForm.value, {
      config_name: '', is_active: false, forecast_horizon_weeks: 52, min_history_weeks: 60,
      outlier_threshold: 0.5, zero_stock_units_threshold: 5.0, low_stock_cover_weeks_threshold: 2.0,
      constrained_weeks_handling: 'flag_only', min_sparse_history_weeks: 12,
      enable_stock_classification: true, enable_launch_routing: true,
    })
  } else {
    runtimeFormMode.value = 'edit'
    editingRuntimeId.value = rc.id
    Object.assign(runtimeForm.value, {
      config_name: rc.config_name,
      is_active: rc.is_active,
      forecast_horizon_weeks: rc.forecast_horizon_weeks,
      min_history_weeks: rc.min_history_weeks,
      outlier_threshold: rc.outlier_threshold ?? 0.5,
      zero_stock_units_threshold: rc.zero_stock_units_threshold ?? 5.0,
      low_stock_cover_weeks_threshold: rc.low_stock_cover_weeks_threshold ?? 2.0,
      constrained_weeks_handling: rc.constrained_weeks_handling,
      min_sparse_history_weeks: rc.min_sparse_history_weeks,
      enable_stock_classification: rc.enable_stock_classification,
      enable_launch_routing: rc.enable_launch_routing,
    })
  }
  runtimeFormOpen.value = true
}

function closeRuntimeForm() {
  runtimeFormOpen.value = false
  runtimeFormError.value = ''
}

async function submitRuntimeForm() {
  runtimeFormSaving.value = true
  runtimeFormError.value = ''
  try {
    if (runtimeFormMode.value === 'create') {
      await api.post('/v1/forecast/runtime-configs', runtimeForm.value)
    } else {
      const { config_name: _, ...updates } = runtimeForm.value
      await api.patch(`/v1/forecast/runtime-configs/${editingRuntimeId.value}`, updates)
    }
    closeRuntimeForm()
    await loadRuntimeConfigs()
  } catch (err) {
    runtimeFormError.value = apiError(err)
  } finally {
    runtimeFormSaving.value = false
  }
}

// ─── Source Config Form ───────────────────────────────────────────────────────

function openSourceForm(sc: SourceConfig | null) {
  sourceFormError.value = ''
  if (sc === null) {
    sourceFormMode.value = 'create'
    editingSourceId.value = null
    Object.assign(sourceForm.value, {
      source_name: '', mysql_database: '', mysql_host: '', mysql_port: null,
      mysql_schema_name: 'aymes_reports', mysql_sales_table: 'adhl_data_daily',
      soh_source_mode: 'external_current_source', is_active: true,
    })
  } else {
    sourceFormMode.value = 'edit'
    editingSourceId.value = sc.id
    Object.assign(sourceForm.value, {
      source_name: sc.source_name,
      mysql_database: sc.mysql_database,
      mysql_host: sc.mysql_host ?? '',
      mysql_port: sc.mysql_port ?? null,
      mysql_schema_name: sc.mysql_schema_name,
      mysql_sales_table: sc.mysql_sales_table,
      soh_source_mode: sc.soh_source_mode,
      is_active: sc.is_active,
    })
  }
  sourceFormOpen.value = true
}

function closeSourceForm() {
  sourceFormOpen.value = false
  sourceFormError.value = ''
}

async function submitSourceForm() {
  sourceFormSaving.value = true
  sourceFormError.value = ''
  try {
    if (sourceFormMode.value === 'create') {
      const h = String(sourceForm.value.mysql_host ?? '').trim()
      const body: Record<string, unknown> = {
        ...sourceForm.value,
        mysql_host: h || null,
        mysql_port:
          sourceForm.value.mysql_port === null || sourceForm.value.mysql_port === undefined
            ? null
            : sourceForm.value.mysql_port,
      }
      await api.post('/v1/forecast/source-configs', body)
    } else {
      const { source_name: _, ...rest } = sourceForm.value
      const h = String(rest.mysql_host ?? '').trim()
      const updates: Record<string, unknown> = { ...rest, mysql_host: h || null }
      if (rest.mysql_port === null || rest.mysql_port === undefined || rest.mysql_port === ('' as unknown)) {
        updates.mysql_port = null
      }
      await api.patch(`/v1/forecast/source-configs/${editingSourceId.value}`, updates)
    }
    closeSourceForm()
    await loadSourceConfigs()
  } catch (err) {
    sourceFormError.value = apiError(err)
  } finally {
    sourceFormSaving.value = false
  }
}

async function toggleSourceActive(sc: SourceConfig) {
  try {
    await api.patch(`/v1/forecast/source-configs/${sc.id}`, { is_active: !sc.is_active })
    await loadSourceConfigs()
  } catch (err) {
    console.error('Toggle source active failed', err)
  }
}

// ─── Run create ───────────────────────────────────────────────────────────────

async function submitCreateRun() {
  createRunSaving.value = true
  createRunError.value = ''
  try {
    const { data } = await api.post<ForecastRun>('/v1/forecast/runs', createRunForm.value)
    createRunFormOpen.value = false
    Object.assign(createRunForm.value, {
      inference_date: '', horizon_weeks: 52, run_type: 'manual',
      source_config_id: null, runtime_config_id: null,
    })
    allRuns.value.unshift(data)
    // Auto-select the new run's detail
    toggleRunDetail(data)
  } catch (err) {
    createRunError.value = apiError(err)
  } finally {
    createRunSaving.value = false
  }
}

// ─── Run detail ───────────────────────────────────────────────────────────────

/** Default sales-ingest window for Execute: 2 years up to inference_date (W-TUE training window is usually longer in config). */
function defaultExecuteDates(inferenceDateStr: string | undefined): { from_date: string; to_date: string } {
  if (!inferenceDateStr || typeof inferenceDateStr !== 'string') return { from_date: '', to_date: '' }
  const inf = new Date(inferenceDateStr.includes('T') ? inferenceDateStr : `${inferenceDateStr}T12:00:00`)
  if (Number.isNaN(inf.getTime())) return { from_date: '', to_date: '' }
  const from = new Date(inf)
  from.setFullYear(from.getFullYear() - 2)
  const pad = (n: number) => String(n).padStart(2, '0')
  const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return { from_date: iso(from), to_date: iso(inf) }
}

async function toggleRunDetail(run: ForecastRun) {
  if (selectedRunId.value === run.id) {
    selectedRunId.value = null
    return
  }
  selectedRunId.value = run.id
  detailTab.value = 'meta'
  runModels.value = []
  runDiagnostics.value = []
  allResults.value = []
  executeOperation.resetOperation('Execute forecast run')
  actionResults.value = {}
  actionOperation.resetOperation('Forecast run action')
  supplyRows.value = []
  supplyMeta.value = null
  supplyComputeOperation.resetOperation('Compute supply-adjusted forecast')
  supplyProductFilter.value = ''
  supplyStockoutFilter.value = false
  supplyExcessFilter.value = false
  resultsProductFilter.value = ''
  resultsModelFilter.value = ''
  resultsBestOnly.value = false
  resultsChartSku.value = ''
  destroyResultCharts()
  statusOverrideValue.value = ''
  statusOverrideErrorMessage.value = ''
  statusOverrideOperation.resetOperation('Override forecast run status')
  let srcName = allSourceConfigs.value.find(sc => sc.id === run.source_config_id)?.source_name ?? ''
  if (!srcName) {
    const active = allSourceConfigs.value.filter((sc) => sc.is_active)
    if (active.length === 1) srcName = active[0].source_name
    else if (active.length > 1) srcName = active[0].source_name
  }
  const { from_date, to_date } = defaultExecuteDates(run.inference_date)
  executeForm.value = { source_config_name: srcName, from_date, to_date }
}

async function switchDetailTab(tab: typeof detailTab.value, runId: number) {
  detailTab.value = tab
  if (tab === 'models' && !runModels.value.length) await loadModels(runId)
  if (tab === 'diag' && !runDiagnostics.value.length) await loadDiagnostics(runId)
  if (tab === 'supply' && !supplyRows.value.length) await loadSupplyRows(runId)
  if (tab === 'results' && !allResults.value.length) await loadResults(runId)
}

// ─── Execute ─────────────────────────────────────────────────────────────────

async function executeRun(runId: number) {
  const data = await executeOperation.runWithOperation(
    'Execute forecast run',
    async () => {
      try {
        const response = await api.post<Record<string, unknown>>(`/v1/forecast/runs/${runId}/execute`, executeForm.value)
        return response.data
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      runningMessage: `Executing forecast run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh forecast runs before retrying.',
      nextActions: ['Refresh forecast runs before retrying.', 'Check run status before executing again.'],
    },
  )
  if (!data) return
  await loadRuns()
  // Refresh the selected run
  const updated = allRuns.value.find(r => r.id === runId)
  if (updated) Object.assign(allRuns.value.find(r => r.id === runId)!, updated)
  executeOperation.completeOperation({
    message: `Done - ${String(data.rows_results ?? '0')} result rows, ${String(data.skus_forecast ?? '0')} SKUs.`,
    technicalDetails: data,
  })
}

// ─── Actions ──────────────────────────────────────────────────────────────────

async function doExportLegacy(runId: number) {
  const data = await actionOperation.runWithOperation(
    'Export legacy forecast',
    async () => {
      try {
        const response = await api.post(`/v1/forecast/runs/${runId}/export-legacy?safe_replace=${exportLegacySafeReplace.value}`)
        return response.data as Record<string, unknown>
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      id: 'export-legacy',
      runningMessage: `Exporting legacy tables for run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh run status before retrying.',
      nextActions: ['Refresh run status before retrying.', 'Check legacy output before exporting again.'],
    },
  )
  if (!data) return
  actionResults.value['export-legacy'] = data
  actionOperation.completeOperation({ id: 'export-legacy', message: 'Legacy export completed.', technicalDetails: data })
}

async function doExportFiles(runId: number) {
  const data = await actionOperation.runWithOperation(
    'Export forecast files',
    async () => {
      try {
        const response = await api.post(`/v1/forecast/runs/${runId}/export-files`)
        return response.data as Record<string, unknown>
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      id: 'export-files',
      runningMessage: `Generating forecast files for run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh run status before retrying.',
      nextActions: ['Refresh run status before retrying.', 'Check the forecast output folder before exporting again.'],
    },
  )
  if (!data) return
  actionResults.value['export-files'] = data
  actionOperation.completeOperation({ id: 'export-files', message: 'Forecast files exported.', technicalDetails: data })
}

async function doValidateParity(runId: number) {
  const data = await actionOperation.runWithOperation(
    'Validate forecast parity',
    async () => {
      try {
        const response = await api.post(`/v1/forecast/runs/${runId}/validate-parity?sample_size=${paritySampleSize.value}`)
        return response.data as Record<string, unknown>
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      id: 'validate-parity',
      runningMessage: `Validating parity for run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh run status before retrying.',
      nextActions: ['Refresh run status before retrying.', 'Check diagnostics before validating again.'],
    },
  )
  if (!data) return
  actionResults.value['validate-parity'] = data
  actionOperation.completeOperation({ id: 'validate-parity', message: 'Parity validation completed.', technicalDetails: data })
}

// ─── Supply-aware forecast ────────────────────────────────────────────────────

async function loadSupplyRows(runId: number) {
  supplyLoading.value = true
  try {
    const params = new URLSearchParams({ limit: '2000' })
    if (supplyProductFilter.value) params.set('product_code', supplyProductFilter.value)
    if (supplyStockoutFilter.value) params.set('stockout_only', 'true')
    if (supplyExcessFilter.value) params.set('excess_only', 'true')
    const { data } = await api.get<SupplyRow[]>(`/v1/forecast/runs/${runId}/supply-adjusted?${params}`)
    supplyRows.value = data
  } catch (err) {
    console.error('Failed to load supply-adjusted rows', err)
  } finally {
    supplyLoading.value = false
  }
}

async function doComputeSupply(runId: number) {
  const data = await supplyComputeOperation.runWithOperation(
    'Compute supply-adjusted forecast',
    async () => {
      try {
        const response = await api.post<Record<string, unknown>>(`/v1/forecast/runs/${runId}/compute-supply-adjusted?use_mock_data=${supplyUseMock.value}`)
        return response.data
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      runningMessage: `Computing supply-adjusted forecast for run #${runId}...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh supply-adjusted rows before retrying.',
      nextActions: ['Refresh supply-adjusted rows before retrying.', 'Check diagnostics before computing again.'],
    },
  )
  if (!data) return
  supplyMeta.value = data
  await loadSupplyRows(runId)
  supplyComputeOperation.completeOperation({
    message: 'Supply-adjusted forecast computed.',
    technicalDetails: data,
  })
}

// ─── Results ──────────────────────────────────────────────────────────────────

function destroyResultCharts() {
  horizonChart?.destroy()
  horizonChart = null
  skuChart?.destroy()
  skuChart = null
}

function buildHorizonSeries(rows: ResultRow[]) {
  const m = new Map<string, number>()
  for (const r of rows) {
    m.set(r.forecast_week, (m.get(r.forecast_week) ?? 0) + (r.forecast_units ?? 0))
  }
  const labels = [...m.keys()].sort()
  return { labels, data: labels.map((l) => m.get(l) ?? 0) }
}

function buildSkuSeries(rows: ResultRow[], sku: string) {
  const sub = rows.filter((r) => r.product_code === sku)
  const wk = new Map<string, { fc: number; act: number | null }>()
  for (const r of sub) {
    const w = r.forecast_week
    const cur = wk.get(w) ?? { fc: 0, act: null as number | null }
    cur.fc += r.forecast_units ?? 0
    if (r.actual_units != null && cur.act === null) cur.act = r.actual_units
    wk.set(w, cur)
  }
  const labels = [...wk.keys()].sort()
  return {
    labels,
    forecast: labels.map((l) => wk.get(l)!.fc),
    actual: labels.map((l) => wk.get(l)!.act),
  }
}

function updateResultCharts() {
  const rows = filteredResults.value
  if (!rows.length) {
    destroyResultCharts()
    return
  }
  if (!horizonChartCanvas.value) return
  const { labels, data: horizonData } = buildHorizonSeries(rows)
  horizonChart?.destroy()
  horizonChart = new Chart(horizonChartCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Σ forecast units (filtered)',
          data: horizonData,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37, 99, 235, 0.12)',
          fill: true,
          tension: 0.15,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: true } },
      scales: {
        x: { ticks: { maxRotation: 50, minRotation: 0, autoSkip: true, maxTicksLimit: 20 } },
        y: { beginAtZero: true },
      },
    },
  })

  skuChart?.destroy()
  skuChart = null
  const pick = resultsChartSku.value
  if (!pick || !skuChartCanvas.value) return
  const { labels: sl, forecast, actual } = buildSkuSeries(rows, pick)
  const hasActual = actual.some((v) => v != null)
  const ds: Array<{
    label: string
    data: (number | null)[]
    borderColor: string
    backgroundColor: string
    fill: boolean
    tension: number
    spanGaps?: boolean
  }> = [
    {
      label: 'Forecast',
      data: forecast,
      borderColor: '#1d4ed8',
      backgroundColor: 'rgba(29, 78, 216, 0.08)',
      fill: false,
      tension: 0.15,
    },
  ]
  if (hasActual) {
    ds.push({
      label: 'Actual',
      data: actual,
      borderColor: '#059669',
      backgroundColor: 'transparent',
      fill: false,
      tension: 0.15,
      spanGaps: true,
    })
  }
  skuChart = new Chart(skuChartCanvas.value, {
    type: 'line',
    data: { labels: sl, datasets: ds },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: true } },
      scales: {
        x: { ticks: { maxRotation: 50, minRotation: 0, autoSkip: true, maxTicksLimit: 24 } },
        y: { beginAtZero: true },
      },
    },
  })
}

async function loadResults(runId: number) {
  resultsLoading.value = true
  try {
    const { data } = await api.get<ResultRow[]>(`/v1/forecast/runs/${runId}/results?limit=5000`)
    allResults.value = data
  } catch (err) {
    console.error('Failed to load results', err)
  } finally {
    resultsLoading.value = false
  }
}

watch([filteredResults, resultsChartSku, resultsLoading], async () => {
  if (resultsLoading.value) return
  await nextTick()
  await nextTick()
  updateResultCharts()
}, { deep: true })

onUnmounted(() => {
  destroyResultCharts()
})

// ─── Status override ──────────────────────────────────────────────────────────

async function doStatusOverride(runId: number) {
  if (!statusOverrideValue.value) return
  const confirmed = window.confirm(
    `Set run #${runId} status to "${statusOverrideValue.value}"?\n\nThis bypasses normal lifecycle transitions.`
  )
  if (!confirmed) return
  const data = await statusOverrideOperation.runWithOperation(
    'Override forecast run status',
    async () => {
      try {
        const params: Record<string, string> = { new_status: statusOverrideValue.value }
        if (statusOverrideValue.value === 'failed') {
          const msg = statusOverrideErrorMessage.value.trim()
          if (msg) params.error_message = msg
        }
        const response = await api.patch<ForecastRun>(
          `/v1/forecast/runs/${runId}/status`,
          {},
          { params },
        )
        return response.data
      } catch (err: unknown) {
        throw new Error(apiError(err))
      }
    },
    {
      runningMessage: `Updating run #${runId} status...`,
      timeoutMessage: 'The request did not return in time. The server may still be processing. Refresh run status before retrying.',
      nextActions: ['Refresh run status before retrying.', 'Check the run table before updating again.'],
    },
  )
  if (!data) return
  const errNote = data.error_message ? ` Message: ${data.error_message}` : ''
  statusOverrideOperation.completeOperation({
    message: `Status updated to "${data.run_status}".${errNote}`,
    technicalDetails: data,
  })
  await loadRuns()
}

// ─── Debug panel ──────────────────────────────────────────────────────────────

async function loadDebugSales() {
  debugSalesLoading.value = true
  debugSalesError.value = ''
  try {
    const { data } = await api.get('/v1/forecast/views/sales-source-weekly')
    debugSalesData.value = data
  } catch (err) {
    debugSalesError.value = apiError(err)
  } finally {
    debugSalesLoading.value = false
  }
}

async function loadDebugTraining() {
  debugTrainingLoading.value = true
  debugTrainingError.value = ''
  try {
    const { data } = await api.get('/v1/forecast/views/training-base')
    debugTrainingData.value = data
  } catch (err) {
    debugTrainingError.value = apiError(err)
  } finally {
    debugTrainingLoading.value = false
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

watch(activeSection, (s) => {
  if (s === 'runs') loadRuns()
})

onMounted(async () => {
  await Promise.all([loadSourceConfigs(), loadRuntimeConfigs(), loadLegacyHealth()])
})
</script>

<style scoped>
/* ── Section tabs ─────────────────────────────────────────────────────────── */
.section-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
}
.section-tab {
  padding: 0.5rem 1.1rem;
  font-size: 0.875rem;
  color: var(--muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
}
.section-tab:hover { color: var(--text); }
.section-tab.active {
  color: var(--accent);
  font-weight: 500;
  border-bottom-color: var(--accent);
}

/* ── Legacy banner ────────────────────────────────────────────────────────── */
.legacy-banner {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.6rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}
.legacy-banner--ok   { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.legacy-banner--warn { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.legacy-banner__icon { font-size: 1rem; flex-shrink: 0; }
.legacy-banner__detail { display: block; font-size: 0.75rem; opacity: 0.75; margin-top: 2px; word-break: break-all; }

/* ── Card header with actions ─────────────────────────────────────────────── */
.card-section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

/* ── Tables ───────────────────────────────────────────────────────────────── */
.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
.admin-table th {
  text-align: left;
  padding: 0.45rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.admin-table td {
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.admin-table tbody tr:last-child td { border-bottom: none; }

/* ── Badges ───────────────────────────────────────────────────────────────── */
.status-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}
.status-badge--active   { background: #dcfce7; color: #166534; }
.status-badge--inactive { background: #f1f5f9; color: #64748b; }

.bool-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}
.bool-badge--yes { background: #dcfce7; color: #166534; }
.bool-badge--no  { background: #f1f5f9; color: #94a3b8; }

.run-status-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}
.run-status--queued   { background: #f1f5f9; color: #475569; }
.run-status--running  { background: #dbeafe; color: #1d4ed8; }
.run-status--success  { background: #dcfce7; color: #166534; }
.run-status--partial  { background: #fef9c3; color: #854d0e; }
.run-status--failed   { background: #fee2e2; color: #991b1b; }

.fail-note-pill {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: default;
}
.fail-note-pill--ok {
  background: #e0f2fe;
  color: #0369a1;
}
.fail-note-pill--warn {
  background: #ffedd5;
  color: #c2410c;
}

/* ── Form pieces ──────────────────────────────────────────────────────────── */
.form-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
}
.form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.form-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
@media (max-width: 640px) {
  .form-grid-2, .form-grid-3 { grid-template-columns: 1fr; }
}
.input-sm { padding: 0.3rem 0.5rem; font-size: 0.8rem; }

.code-pill {
  display: inline-block;
  padding: 1px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: ui-monospace, monospace;
}
.required { color: #dc2626; }
.link-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0;
  text-decoration: underline;
}
.link-btn:hover { opacity: 0.75; }
.btn-sm {
  padding: 0.3rem 0.7rem;
  font-size: 0.8rem;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid transparent;
}
.btn-disabled {
  background: #e2e8f0; color: #94a3b8;
  border-color: #cbd5e1; cursor: not-allowed;
}
.error-msg { color: #dc2626; font-size: 0.8rem; margin-top: 0.25rem; }
.error-msg-inline { color: #dc2626; font-size: 0.8rem; font-family: ui-monospace, monospace; word-break: break-all; }

/* ── Run detail panel ─────────────────────────────────────────────────────── */
.run-detail-cell { padding: 0 !important; }
.run-detail-panel {
  border-top: 2px solid var(--accent);
  background: #f8fafc;
  padding: 1rem 1.25rem;
}
.detail-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1rem;
}
.detail-tab {
  padding: 0.35rem 0.85rem;
  font-size: 0.8rem;
  color: var(--muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.detail-tab:hover { color: var(--text); }
.detail-tab.active { color: var(--accent); font-weight: 600; border-bottom-color: var(--accent); }
.detail-tab-count {
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  padding: 0 5px;
  font-size: 0.65rem;
  line-height: 1.4;
}
.detail-content { padding: 0.5rem 0; }

/* ── Metadata grid ────────────────────────────────────────────────────────── */
.meta-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 0.3rem 1rem;
  font-size: 0.875rem;
}
.meta-grid dt { color: var(--muted); font-size: 0.75rem; }
.meta-grid dd { font-weight: 500; }

/* ── Diagnostics list ─────────────────────────────────────────────────────── */
.diag-list { max-height: 400px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.diag-row {
  display: grid;
  grid-template-columns: 60px 130px 100px 1fr;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.8rem;
  align-items: start;
}
.diag-row:last-child { border-bottom: none; }
.diag-row--info    { background: #fff; }
.diag-row--warning { background: #fffbeb; }
.diag-row--error   { background: #fff5f5; }
.diag-level { font-weight: 700; font-size: 0.7rem; text-transform: uppercase; }
.diag-row--info .diag-level    { color: #3b82f6; }
.diag-row--warning .diag-level { color: #f59e0b; }
.diag-row--error .diag-level   { color: #dc2626; }
.diag-type { color: var(--muted); font-size: 0.7rem; }
.diag-sku  { color: #7c3aed; font-size: 0.7rem; font-family: monospace; }
.diag-msg  { color: var(--text); word-break: break-word; }

/* ── Action cards ─────────────────────────────────────────────────────────── */
.action-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.85rem 1rem;
  background: #fff;
}
.action-card--disabled { background: #f8fafc; opacity: 0.75; }
.action-card__header strong { font-size: 0.875rem; color: var(--text); }
.result-json {
  font-size: 0.7rem;
  font-family: ui-monospace, monospace;
  background: #f1f5f9;
  border-radius: 4px;
  padding: 0.5rem;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── Supply-aware forecast ────────────────────────────────────────────────── */
.supply-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.supply-table-wrap {
  overflow-x: auto;
  max-height: 480px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.supply-row--stockout { background: #fff5f5; }
.supply-row--excess   { background: #fffbeb; }
.flag-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
}
.flag-badge--red   { background: #fee2e2; color: #991b1b; }
.flag-badge--amber { background: #fef9c3; color: #854d0e; }

/* ── Engine header ────────────────────────────────────────────────────────── */
.engine-header {
  padding: 1rem 1.25rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.engine-header__title h2 { margin: 0; }
.engine-header__note {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  max-width: 420px;
  flex-shrink: 0;
}
.engine-note-icon { color: #3b82f6; font-size: 0.9rem; flex-shrink: 0; margin-top: 1px; }

/* ── Results + evidence charts ─────────────────────────────────────────────── */
.results-evidence__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}
@media (min-width: 768px) {
  .results-evidence__stats {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
.evidence-stat {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.5rem 0.65rem;
  background: #f8fafc;
}
.evidence-stat__label {
  display: block;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  margin-bottom: 0.2rem;
}
.evidence-stat__val {
  font-weight: 600;
  font-size: 1rem;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}
.results-chart-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  background: #fff;
}
.results-chart-canvas {
  position: relative;
  height: 14rem;
  width: 100%;
}

/* ── Results table ────────────────────────────────────────────────────────── */
.results-table-wrap {
  overflow-x: auto;
  max-height: 520px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.results-row--best { background: #f0fdf4; }

/* ── Debug panel ──────────────────────────────────────────────────────────── */
.debug-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.85rem 1rem;
  background: #fff;
}
.debug-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.debug-health-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  font-size: 0.875rem;
}
.debug-health-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--ok  { background: #22c55e; }
.dot--err { background: #ef4444; }
.tabular-nums { font-variant-numeric: tabular-nums; }
</style>
