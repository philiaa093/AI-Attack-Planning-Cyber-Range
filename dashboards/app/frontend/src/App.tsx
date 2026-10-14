import React, { useState, useEffect, useCallback } from 'react';
import { ControlCenter } from './pages/ControlCenter';
import { RunHistoryPage } from './pages/RunHistoryPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { RunComparisonPage } from './pages/RunComparisonPage';
import { ResearchPage } from './pages/ResearchPage';
import { Header } from './components/layout/Header';
import { useSystemStatus } from './hooks/useSystemStatus';
import { useEventStream } from './hooks/useEventStream';
import { LanguageProvider } from './i18n/LanguageContext';
import type { AgentEvent } from './api/types';

export const AppContent: React.FC = () => {
  const { status, updateFromEvent } = useSystemStatus();

  const handleIncomingEvent = useCallback(
    (ev: AgentEvent) => {
      updateFromEvent(ev);
    },
    [updateFromEvent]
  );

  const { connectionStatus } = useEventStream({
    runId: status?.run.run_id ?? undefined,
    onEvent: handleIncomingEvent,
  });

  const [activeTab, setActiveTab] = useState<'overview' | 'runs' | 'run-detail' | 'compare' | 'research'>('overview');
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [compareRunA, setCompareRunA] = useState<string>('');
  const [compareRunB, setCompareRunB] = useState<string>('');

  // Hash-based routing synchronization
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace(/^#/, '');
      if (hash.startsWith('runs/') || hash.startsWith('run/')) {
        const id = hash.replace(/^(runs|run)\//, '');
        setSelectedRunId(id);
        setActiveTab('run-detail');
      } else if (hash.startsWith('compare')) {
        const queryParams = new URLSearchParams(hash.split('?')[1] || '');
        setCompareRunA(queryParams.get('run_a') || '');
        setCompareRunB(queryParams.get('run_b') || '');
        setActiveTab('compare');
      } else if (hash === 'research') {
        setActiveTab('research');
      } else if (hash === 'runs') {
        setActiveTab('runs');
      } else {
        setActiveTab('overview');
      }
    };

    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateTo = (tab: 'overview' | 'runs' | 'compare' | 'research') => {
    setActiveTab(tab);
    if (tab === 'overview') window.location.hash = '#overview';
    else if (tab === 'runs') window.location.hash = '#runs';
    else if (tab === 'research') window.location.hash = '#research';
    else if (tab === 'compare') {
      const q = compareRunA && compareRunB ? `?run_a=${compareRunA}&run_b=${compareRunB}` : '';
      window.location.hash = `#compare${q}`;
    }
  };

  const navigateToRun = (runId: string) => {
    setSelectedRunId(runId);
    setActiveTab('run-detail');
    window.location.hash = `#runs/${encodeURIComponent(runId)}`;
  };

  const navigateToCompare = (runA: string, runB: string) => {
    setCompareRunA(runA);
    setCompareRunB(runB);
    setActiveTab('compare');
    window.location.hash = `#compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`;
  };

  return (
    <div className="workspace-theme min-h-screen flex flex-col font-sans">
      {activeTab === 'research' && <>
        <Header system={status} sseStatus={connectionStatus} activeTab="research" onNavigate={navigateTo} />
        <ResearchPage onViewRuns={() => navigateTo('runs')} />
      </>}
      {activeTab === 'overview' && (
        <ControlCenter activeTab="overview" onNavigateTab={navigateTo} />
      )}

      {activeTab === 'runs' && (
        <div className="min-h-screen bg-[#0b0f17] flex flex-col">
          <Header
            system={status}
            sseStatus={connectionStatus}
            activeTab="runs"
            onNavigate={navigateTo}
          />
          <RunHistoryPage
            onSelectRun={navigateToRun}
            onCompareRuns={navigateToCompare}
          />
        </div>
      )}

      {activeTab === 'run-detail' && (
        <div className="min-h-screen bg-[#0b0f17] flex flex-col">
          <Header
            system={status}
            sseStatus={connectionStatus}
            activeTab="run-detail"
            onNavigate={navigateTo}
          />
          <RunDetailPage
            runId={selectedRunId}
            onBack={() => navigateTo('runs')}
            onCompareWith={(runId) => {
              setCompareRunA(runId);
              navigateTo('compare');
            }}
          />
        </div>
      )}

      {activeTab === 'compare' && (
        <div className="min-h-screen bg-[#0b0f17] flex flex-col">
          <Header
            system={status}
            sseStatus={connectionStatus}
            activeTab="compare"
            onNavigate={navigateTo}
          />
          <RunComparisonPage
            initialRunA={compareRunA}
            initialRunB={compareRunB}
            onSelectRunDetail={navigateToRun}
          />
        </div>
      )}
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <LanguageProvider>
      <AppContent />
    </LanguageProvider>
  );
};

export default App;
