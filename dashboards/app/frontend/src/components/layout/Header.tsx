import React from 'react';
import { Shield, Languages, Tv, LayoutDashboard, History, GitCompare, ListChecks } from 'lucide-react';
import type { SseConnectionStatus, SystemStatus } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';
import { displayValue } from '../../i18n/displayValue';
import { ModelSettingsButton } from '../controls/ModelSettings';

export type MainTab = 'overview' | 'runs' | 'compare' | 'research';
interface HeaderProps {
  system: SystemStatus | null;
  sseStatus: SseConnectionStatus;
  activeTab?: MainTab | 'run-detail';
  onNavigate?: (tab: MainTab) => void;
  presentationMode?: boolean;
  onTogglePresentationMode?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ system, sseStatus, activeTab = 'overview', onNavigate, presentationMode, onTogglePresentationMode }) => {
  const { lang, toggleLang, t } = useLanguage();
  const vi = lang === 'vi';
  const items = [
    { id: 'overview', label: vi ? 'Tổng quan' : 'Overview', Icon: LayoutDashboard },
    { id: 'runs', label: vi ? 'Lịch sử phiên' : 'Runs', Icon: History },
    { id: 'compare', label: vi ? 'So sánh' : 'Compare', Icon: GitCompare },
    { id: 'research', label: vi ? 'Tiến độ đề tài' : 'Research progress', Icon: ListChecks },
  ] as const;
  return <header className="cc-header">
    <div className="cc-header-top">
      <div className="cc-brand"><span className="cc-brand-icon"><Shield size={22} aria-hidden="true" /></span><div>
        <h1>{vi ? 'Trung tâm nghiên cứu' : 'Research Control Center'}</h1>
        <p>{vi ? 'An toàn ứng dụng web · Phòng thực nghiệm' : 'Web application security · Research lab'}</p>
      </div></div>
      <div className="cc-header-tools">
        {system?.safety.kill_switch_active && <span role="status" className="cc-kill-switch">{t.killSwitchActive}</span>}
        <button type="button" className="cc-button" onClick={toggleLang} aria-label={vi ? 'Đổi ngôn ngữ' : 'Toggle language'}><Languages size={16} aria-hidden="true" />{vi ? 'Tiếng Việt' : 'English'}</button>
        {onTogglePresentationMode && <button type="button" className="cc-button" onClick={onTogglePresentationMode} aria-label={vi ? 'Đổi chế độ hiển thị' : 'Toggle Presentation Mode'}><Tv size={16} aria-hidden="true" />{presentationMode ? (vi ? 'Thuyết trình' : 'Presentation') : (vi ? 'Chi tiết' : 'Operator view')}</button>}
        <ModelSettingsButton />
      </div>
    </div>
    <div className="cc-header-bottom">
      {onNavigate && <nav className="cc-nav" aria-label={vi ? 'Điều hướng chính' : 'Main navigation'}>
        {items.map(({id, label, Icon}) => <button key={id} type="button" aria-current={activeTab === id || (id === 'runs' && activeTab === 'run-detail') ? 'page' : undefined} onClick={() => onNavigate(id)}><Icon size={17} aria-hidden="true" />{label}</button>)}
      </nav>}
      <span className="cc-connection" role="status"><i className={sseStatus === 'CONNECTED' ? 'is-connected' : ''} aria-hidden="true" />{vi ? 'Luồng sự kiện' : 'Event stream'}: {displayValue(sseStatus, lang)}</span>
    </div>
  </header>;
};
