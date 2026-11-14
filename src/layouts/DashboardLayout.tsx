import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  BarChart3,
  Boxes,
  Camera,
  CheckSquare,
  History,
  Image as ImageIcon,
  Inbox,
  LayoutDashboard,
  LogIn,
  Menu,
  PackageSearch,
  RefreshCw,
  Settings,
  Tag,
  TrendingUp,
  X,
} from 'lucide-react';
import { useStoreContext } from '../hooks/useStoreContext';
import { PWAInstallButton } from '../components/PWAInstallButton';
import { OfflineIndicator } from '../components/OfflineIndicator';
import { cn } from '../lib/formatters';

interface NavGroup {
  label: string;
  items: Array<{
    to: string;
    key: string;
    icon: React.ComponentType<{ className?: string }>;
  }>;
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Store Overview',
    items: [{ to: '/', key: 'nav.dashboard', icon: LayoutDashboard }],
  },
  {
    label: 'O1 · Inventory Agent',
    items: [
      { to: '/catalogue', key: 'nav.catalogue', icon: PackageSearch },
      { to: '/inventory', key: 'nav.inventory', icon: Boxes },
      { to: '/upload-photo', key: 'nav.uploadPhoto', icon: Camera },
      { to: '/detection-review', key: 'nav.detectionReview', icon: CheckSquare },
      { to: '/reference-images', key: 'nav.referenceImages', icon: ImageIcon },
    ],
  },
  {
    label: 'O1 · Demand & Reorder',
    items: [
      { to: '/forecasting', key: 'nav.forecasting', icon: TrendingUp },
      { to: '/reorders', key: 'nav.reorders', icon: RefreshCw },
    ],
  },
  {
    label: 'O2 · Smart Pricing Agent',
    items: [
      { to: '/pricing', key: 'nav.pricing', icon: Tag },
      { to: '/pricing-inbox', key: 'nav.pricingInbox', icon: Inbox },
      { to: '/analytics', key: 'nav.analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'Governance & Store',
    items: [
      { to: '/agent-runs', key: 'nav.agentRuns', icon: History },
      { to: '/settings', key: 'nav.settings', icon: Settings },
      { to: '/login', key: 'nav.login', icon: LogIn },
    ],
  },
];

export const DashboardLayout: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { stores, activeStoreId, setActiveStoreId, activeStore, session, setSession } = useStoreContext();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const currentNavItem = NAV_GROUPS.flatMap((g) => g.items).find((item) => item.to === location.pathname);
  const pageTitle = currentNavItem ? t(currentNavItem.key) : 'Store Dashboard';

  const handleLanguageChange = (lang: string) => {
    i18n.changeLanguage(lang);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex lg:w-[260px] lg:flex-col lg:fixed lg:inset-y-0 border-r border-slate-200 bg-white">
        <div className="h-16 flex items-center px-5 border-b border-slate-200">
          <span className="font-display text-base font-bold tracking-tight text-slate-900 whitespace-nowrap">
            AI Powered Retail Connect
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="px-3 mb-2 text-xs font-medium text-slate-500">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap',
                          isActive
                            ? 'bg-teal-50 text-teal-800'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                        )
                      }
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{t(item.key)}</span>
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-4 text-xs text-slate-500 space-y-1">
          <div className="font-medium text-slate-700 truncate">
            {session ? session.user.full_name : 'Demo Store Owner View'}
          </div>
          <div className="truncate">
            {activeStore ? `${activeStore.store_code} · ${activeStore.city}` : 'Loading store...'}
          </div>
        </div>
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-slate-900/40"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative z-10 w-72 max-w-full bg-white h-full border-r border-slate-200 flex flex-col">
            <div className="h-16 flex items-center justify-between px-4 border-b border-slate-200">
              <span className="font-display text-base font-bold text-slate-900">
                Retail Connect
              </span>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="p-2 text-slate-600 hover:text-slate-900"
                aria-label="Close navigation"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
              {NAV_GROUPS.map((group) => (
                <div key={group.label}>
                  <div className="px-3 mb-1.5 text-xs font-medium text-slate-500">
                    {group.label}
                  </div>
                  <div className="space-y-0.5">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <NavLink
                          key={item.to}
                          to={item.to}
                          end={item.to === '/'}
                          onClick={() => setMobileOpen(false)}
                          className={({ isActive }) =>
                            cn(
                              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium',
                              isActive
                                ? 'bg-teal-50 text-teal-800'
                                : 'text-slate-600 hover:bg-slate-100',
                            )
                          }
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          <span>{t(item.key)}</span>
                        </NavLink>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 lg:pl-[260px] flex flex-col min-w-0">
        {/* Top Bar Contract */}
        <header className="sticky top-0 z-30 h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="lg:hidden p-2 -ml-2 rounded-lg text-slate-600 hover:bg-slate-100"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 text-sm min-w-0">
              <span className="hidden sm:inline text-slate-400">Kirana Operations</span>
              <span className="hidden sm:inline text-slate-300">/</span>
              <h1 className="font-display font-semibold text-slate-900 truncate">{pageTitle}</h1>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <select
              aria-label="Select Kirana Store"
              value={activeStoreId}
              onChange={(e) => setActiveStoreId(e.target.value)}
              className="h-9 max-w-[210px] rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-600"
            >
              {stores.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.store_code} · {s.name}
                </option>
              ))}
            </select>

            <select
              aria-label="Language"
              value={i18n.language}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="hidden sm:block h-9 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-600"
            >
              <option value="en">EN</option>
              <option value="hi">हिं</option>
              <option value="kn">ಕನ್ನಡ</option>
            </select>

            <PWAInstallButton />

            {session ? (
              <button
                type="button"
                onClick={() => {
                  setSession(null);
                  navigate('/login');
                }}
                className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 whitespace-nowrap shrink-0"
              >
                Sign Out
              </button>
            ) : (
              <button
                type="button"
                onClick={() => navigate('/login')}
                className="h-9 rounded-lg bg-teal-700 px-3 text-xs font-medium text-white hover:bg-teal-800 whitespace-nowrap shrink-0"
              >
                Owner Sign In
              </button>
            )}
          </div>
        </header>

        {/* Honest Synthetic Data Disclosure */}
        <div className="border-b border-slate-200 bg-slate-100/80 px-4 sm:px-6 py-2 text-xs text-slate-600 flex flex-wrap items-center justify-between gap-2">
          <span>{t('syntheticNotice')}</span>
          <span className="font-mono-num text-slate-500">Stage 1 · Foundation Active</span>
        </div>

        <main className="flex-1 p-4 sm:p-6 max-w-[1440px] w-full mx-auto">
          <Outlet />
        </main>
      </div>

      <OfflineIndicator />
    </div>
  );
};
