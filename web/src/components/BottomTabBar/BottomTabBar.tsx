import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { NAV_ITEMS, SETTINGS_ITEM } from '../nav/navItems';
import { useNavActive } from '../nav/useNavActive';
import { useAuth } from '@/contexts/AuthContext';
import './BottomTabBar.css';

export default function BottomTabBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const isActive = useNavActive();
  const { member } = useAuth();
  const menuItems = member?.role === 'student'
    ? NAV_ITEMS.filter((item) => item.key !== '/automations')
    : [...NAV_ITEMS, SETTINGS_ITEM];
  const handleItemClick = (path: string) => {
    if (location.pathname === path) return;
    navigate(path);
  };

  return (
    <div className="bottom-tab-bar">
      <div className="bottom-tab-bar-pill">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item);

          return (
            <button
              key={item.key}
              className={`bottom-tab-item ${active ? 'active' : ''}`}
              onClick={() => handleItemClick(item.key)}
              aria-label={t(item.labelKey)}
              aria-current={active ? 'page' : undefined}
            >
              <Icon className="bottom-tab-item-icon" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
