/** Central copy for the in-app page help panel. Keys match Vue Router route `name` where possible. */

/** End-to-end journey; only set on Dashboard so new users see the full flow in one place. */
export interface PlanningWorkflowHelp {
  intro?: string
  steps: string[]
  stock_aware: string
  demand_only: string
}

export interface PageHelpContent {
  title: string
  purpose: string
  when_to_use: string
  key_actions: string[]
  next_steps: string[]
  important_notes?: string
  planning_workflow?: PlanningWorkflowHelp
}

export const PAGE_HELP_BY_ROUTE: Record<string, PageHelpContent> = {
  Dashboard: {
    title: 'Dashboard',
    planning_workflow: {
      intro: 'Typical path from first login to exports:',
      steps: [
        'Start on the Supply Dashboard (this page): check readiness and create or pick a scenario.',
        'Choose planning mode (stock-aware or demand-only) so results match how you will read them.',
        'Choose warehouse scope, then run planning to generate a new plan run.',
        'Review the SKU × week picture in Weekly Planning Grid.',
        'Inspect weeks or drill into a SKU in Inventory Projection or SKU Detail.',
        'Freeze, recalculate, or compare runs in Scenario Manager when you need to operate on scenarios.',
        'Pull CSVs from Exports for offline analysis or sharing.',
      ],
      stock_aware:
        'Uses SOH snapshots with demand and policies so stockout and cover views reflect physical-style inventory where data exists.',
      demand_only:
        'Runs from demand and policies without requiring SOH; projections are modeled for planning, not a picture of warehouse on-hand.',
    },
    purpose:
      'Planning launchpad: set mode and warehouse scope, run a plan, then jump to the grid, projections, scenarios, or exports. Readiness tiles and coverage show if stock-aware is realistic.',
    when_to_use:
      'Start every planning session here: answer “can I run?”, pick mode/scope, run, then open the next tool from the focused run.',
    key_actions: [
      'Planning mode: stock-aware uses SOH snapshots for physical-style risk; demand-only uses modeled position (no SOH required).',
      'Warehouse scope: limits which warehouses the new run includes.',
      'Run plan: creates a scenario you can open in grids, projections, and exports.',
      'Select an existing run to refresh the at-a-glance risk lists.',
    ],
    next_steps: [
      'If something is blocked, open Data Health or complete setup/imports.',
      'Open Inventory Projection for week-by-week numbers or Weekly Planning Grid for the SKU × week heatmap.',
      'Use Scenario Manager to freeze periods, recalculate demand, or compare runs in more detail.',
    ],
    important_notes:
      'Readiness banners distinguish stock-aware (needs SOH) from demand-only (policies + demand). Pick the mode that matches how you will interpret results.',
  },

  WeeklyPlanningGrid: {
    title: 'Weekly Planning Grid',
    purpose:
      'Scan many SKUs across weeks in one table. Cell colours summarise projected health; click a cell to open the explanation panel for that SKU and week.',
    when_to_use:
      'When you need a visual sweep for stockouts, low cover, or healthy weeks without exporting spreadsheets.',
    key_actions: [
      'Scenario: choose which plan run drives the grid.',
      'Warehouse / SKU filters: narrow the matrix.',
      'Click a cell: opens context, policy targets, and related metrics where available.',
    ],
    next_steps: [
      'Drill into SKU Detail or Stock Position for a fuller breakdown.',
      'Use Inventory Projection if you need exact week-by-week quantities or two-run comparison.',
      'Export CSVs from the Exports page when you need files.',
    ],
    important_notes:
      'Amber uses a fixed low-cover threshold for the whole grid; each row’s policy target weeks may differ (see the explain panel). For demand-only runs, colours reflect a modeled ledger—not a guarantee of physical warehouse stock.',
  },

  InventoryProjection: {
    title: 'Inventory Projection',
    purpose:
      'View projected inventory by week for one plan run, and optionally compare a second run side by side. Filter by SKU, warehouse, or stockout-only rows.',
    when_to_use:
      'When you need numeric week-by-week projections after a plan run, or to compare two scenarios.',
    key_actions: [
      'Plan run 1: primary scenario (required). Plan run 2: optional comparison.',
      'Search and filters: focus on a SKU, warehouse, or only rows at or below zero.',
      'Export CSV: downloads data for the primary run (scenario 1).',
    ],
    next_steps: [
      'Create or pick runs on the Dashboard if nothing appears here.',
      'Use Weekly Planning Grid for a heatmap view of the same underlying planning output.',
      'Use Exports for other CSV types (planned orders, exceptions).',
    ],
    important_notes:
      'For demand-only runs, projections are modeled from policies and demand—not net of physical SOH unless the engine was run stock-aware.',
  },

  ScenarioManager: {
    title: 'Scenario Manager',
    purpose:
      'Operate on existing plan runs: freeze demand or orders, recalculate non-frozen demand, pin a forecast training week, compare scenarios, and check forecast health (e.g. WAPE).',
    when_to_use:
      'After you have plan runs, when you need to lock a period, refresh demand outside the freeze, or compare two scenarios formally.',
    key_actions: [
      'Select a scenario, then Freeze or Recalculate as needed.',
      'Forecast run dropdown: applies when demand is baseline/blended and you want a specific training end week.',
      'Use the compare and health sections on this page for side-by-side and accuracy views.',
    ],
    next_steps: [
      'Return to the Dashboard to run a new scenario with different scope or mode.',
      'Open Inventory Projection or Weekly Planning Grid to see how changes look in the planning views.',
    ],
    important_notes:
      'For demand-only runs, treat coverage-style exception lists with care: they are not a substitute for stock-aware physical checks.',
  },

  Exports: {
    title: 'Exports',
    purpose:
      'Download CSV files: projected inventory, planned orders, exception lists, and SKU-level explanation reports, each tied to a selected scenario.',
    when_to_use:
      'When you need to share numbers in Excel, archive an output, or analyse offline.',
    key_actions: [
      'Choose the plan run per export block (some blocks share or repeat scenario pickers).',
      'Use the download links; files are generated for the selected scenario.',
    ],
    next_steps: [
      'Ensure the right scenario exists—create it on the Dashboard first.',
      'Validate numbers in Inventory Projection or Stock Position if something looks unexpected.',
    ],
    important_notes:
      'Demand-only runs may include demand_only in filenames. Treat those columns as modeled planning outputs, not warehouse on-hand truth.',
  },

  StockPosition: {
    title: 'Stock Position Breakdown',
    purpose:
      'See per SKU and warehouse how position, targets, reorder points, and breach flags line up for a chosen plan run. Expand rows for more week-level detail where available.',
    when_to_use:
      'When you need to explain why a SKU is flagged or how policy compares to projected position.',
    key_actions: [
      'Plan run: selects which scenario’s outputs you are viewing.',
      'Warehouse and family filters, breach-only: narrow to problem areas.',
      'Open a row or detail panel for deeper breakdowns.',
    ],
    next_steps: [
      'Cross-check with Weekly Planning Grid for the same scenario.',
      'Use Inventory Projection for raw week-by-week projection columns or two-run compare.',
    ],
    important_notes:
      'Stock-aware runs align with SOH-backed planning. Demand-only runs still show modeled projection and may mix snapshot “on hand” where loaded—read the on-page mode banner so you do not mix physical and modeled interpretations.',
  },
}

export function getPageHelp(routeName: string | symbol | undefined | null): PageHelpContent | null {
  if (routeName == null || typeof routeName !== 'string') return null
  return PAGE_HELP_BY_ROUTE[routeName] ?? null
}
