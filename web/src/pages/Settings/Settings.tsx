import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useScrollMemory } from '@/lib/scrollMemory';
import { useUser } from '@/hooks/useUser';
import { usePreferences } from '@/hooks/usePreferences';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/contexts/AuthContext';
import { UserInfoTab } from './panels/UserInfoTab';
import { PreferencesTab } from './panels/PreferencesTab';
import { ModelTab } from './panels/ModelTab';
import { ExperimentsTab } from './panels/ExperimentsTab';
import { FamilyAccountsTab } from './panels/FamilyAccountsTab';
import { FamilyChildConversations } from './panels/FamilyChildConversations';
import { useFamilyChildren } from './queries';
import './Settings.css';

function Settings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { isLoading: isUserLoading } = useUser();
  const { isLoading: isPrefsLoading } = usePreferences();
  const { member } = useAuth();
  const { t } = useTranslation();

  const tabParam = searchParams.get('tab') || 'userInfo';
  const studentUserId = searchParams.get('student');
  const [activeTab, setActiveTab] = useState(tabParam);
  const pageRef = useRef<HTMLDivElement>(null);
  useScrollMemory(pageRef, 'page:settings');
  const isLoading = isUserLoading || isPrefsLoading;
  const isParent = member?.role === 'parent';
  const isStudent = member?.role === 'student';
  const familyChildren = useFamilyChildren(
    activeTab === 'family' && Boolean(studentUserId) && isParent,
  );
  const selectedChild = familyChildren.data?.find((child) => child.user_id === studentUserId);

  // Sync tab with URL search params
  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    setSearchParams({ tab }, { replace: true });
  };

  const openChild = (studentId: string) => {
    setSearchParams({ tab: 'family', student: studentId }, { replace: false });
    setActiveTab('family');
  };

  const closeChild = () => {
    setSearchParams({ tab: 'family' }, { replace: false });
    setActiveTab('family');
  };

  // Sync from URL on mount / back-forward navigation
  useEffect(() => {
    const urlTab = searchParams.get('tab');
    if (urlTab && urlTab !== activeTab) {
      setActiveTab(urlTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div ref={pageRef} className="settings-page">
      <div className="settings-container">
        <h2 className="text-xl font-semibold mb-6" style={{ color: 'var(--color-text-primary)' }}>{t('settings.title')}</h2>
        <div className="flex gap-2 mb-6 border-b overflow-x-auto settings-tab-bar" style={{ borderColor: 'var(--color-border-muted)' }}>
          <button
            type="button"
            onClick={() => handleTabChange('userInfo')}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap flex-shrink-0"
            style={{
              color: activeTab === 'userInfo' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
              borderBottom: activeTab === 'userInfo' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
            }}
          >
            {t('settings.userInfo')}
          </button>
          <button
            type="button"
            onClick={() => handleTabChange('preferences')}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap flex-shrink-0"
            style={{
              color: activeTab === 'preferences' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
              borderBottom: activeTab === 'preferences' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
            }}
          >
            {t('settings.preferences')}
          </button>
          {!isStudent && <button
            type="button"
            onClick={() => handleTabChange('model')}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap flex-shrink-0"
            style={{
              color: activeTab === 'model' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
              borderBottom: activeTab === 'model' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
            }}
          >
            {t('settings.model')}
          </button>}
          <button
            type="button"
            onClick={() => handleTabChange('experiments')}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap flex-shrink-0"
            style={{
              color: activeTab === 'experiments' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
              borderBottom: activeTab === 'experiments' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
            }}
          >
            {t('settings.experiments', 'Experiments')}
          </button>
          {isParent && <button
            type="button"
            onClick={() => handleTabChange('family')}
            className="px-4 py-2 text-sm font-medium whitespace-nowrap flex-shrink-0"
            style={{
              color: activeTab === 'family' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
              borderBottom: activeTab === 'family' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
            }}
          >
            家庭账户
          </button>}
        </div>

        <div className="settings-content">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm" style={{ color: 'var(--color-text-primary)', opacity: 0.7 }}>{t('common.loading')}</p>
            </div>
          )}

          {!isLoading && activeTab === 'userInfo' && <UserInfoTab />}

          {!isLoading && activeTab === 'preferences' && <PreferencesTab />}

          {!isLoading && activeTab === 'model' && !isStudent && <ModelTab />}

          {/* Text-heavy tab: cap the measure so descriptions stay readable
              instead of spanning the full settings container. */}
          {!isLoading && activeTab === 'experiments' && <ExperimentsTab />}

          {!isLoading && activeTab === 'family' && !isParent && <FamilyAccountsTab onOpenChild={openChild} />}

          {!isLoading && activeTab === 'family' && isParent && !studentUserId && <FamilyAccountsTab onOpenChild={openChild} />}

          {!isLoading && activeTab === 'family' && isParent && studentUserId && <FamilyChildConversations
            student={{ user_id: studentUserId, name: selectedChild?.name ?? '子女' }}
            onBack={closeChild}
          />}

        </div>
      </div>
    </div>
  );
}

export default Settings;
