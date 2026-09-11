// Registry side-effect barrel.
//
// Importing this module populates the widget registry. Upstream imports thirty
// definitions here, including every TradingView embed; this branch carries only
// the finance-free set. Definitions are appended by later tasks.

export { listWidgets, listWidgetsByCategory, getWidget } from './framework/WidgetRegistry';
