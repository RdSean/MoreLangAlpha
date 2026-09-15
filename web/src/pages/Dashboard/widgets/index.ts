// Registry side-effect barrel.
//
// Importing this module populates the widget registry. Upstream imports thirty
// definitions here, including every TradingView embed; this branch carries only
// the finance-free set.

import './definitions/HomeworkCalendarWidget';
import './definitions/AutomationsWidget';
import './definitions/ConversationWidget';
import './definitions/WorkspacePickerWidget';
import './definitions/RecentThreadsWidget';

export { listWidgets, listWidgetsByCategory, getWidget } from './framework/WidgetRegistry';
