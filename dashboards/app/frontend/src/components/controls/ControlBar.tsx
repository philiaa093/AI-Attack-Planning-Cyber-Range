import React, { useState } from 'react';
import {
  ClipboardCheck,
  Play,
  Pause,
  PlayCircle,
  Square,
  Power,
  AlertOctagon,
  RefreshCw,
  Server,
} from 'lucide-react';
import type { SystemStatus } from '../../api/types';
import { useLanguage } from '../../i18n/LanguageContext';

interface ControlBarProps {
  system: SystemStatus | null;
  onRunPreflight: () => void;
  onStartLab: () => Promise<void>;
  onStopLab: () => Promise<void>;
  onOpenStartRun: () => void;
  onPauseRun?: () => Promise<void>;
  onResumeRun?: () => Promise<void>;
  onStopRun: () => Promise<void>;
  onEmergencyStop: () => Promise<void>;
  isLabStarting: boolean;
  isLabStopping: boolean;
  isRunPausing?: boolean;
  isRunResuming?: boolean;
  isRunStopping: boolean;
  isEmergencyStopping: boolean;
}

export const ControlBar: React.FC<ControlBarProps> = ({
  system,
  onRunPreflight,
  onStartLab,
  onStopLab,
  onOpenStartRun,
  onPauseRun,
  onResumeRun,
  onStopRun,
  onEmergencyStop,
  isLabStarting,
  isLabStopping,
  isRunPausing = false,
  isRunResuming = false,
  isRunStopping,
  isEmergencyStopping,
}) => {
  const { lang } = useLanguage();
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(false);

  const rangeState = system?.range.status;
  const runState = system?.run.state;
  const isRunRunning = runState === 'RUNNING';
  const isRunPaused = runState === 'PAUSED';
  const isRunActive =
    runState === 'RUNNING' ||
    runState === 'STARTING' ||
    runState === 'WAITING_FOR_APPROVAL' ||
    runState === 'PAUSING' ||
    runState === 'PAUSED' ||
    runState === 'RESUMING';
  const isKillSwitchActive = system?.safety.kill_switch_active;
  const isLabHealthy = rangeState === 'HEALTHY';
  const isLabStartingState = rangeState === 'STARTING' || isLabStarting;

  const handleConfirmEmergency = async () => {
    setShowEmergencyConfirm(false);
    await onEmergencyStop();
  };

  return (
    <>
      <div className="bg-[#111724] border border-slate-800/80 rounded-lg p-3 shadow-sm flex flex-wrap items-center justify-between gap-2.5">
        {/* Left: Environment & Lab Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Preflight */}
          <button
            onClick={onRunPreflight}
            aria-label={lang === 'vi' ? "Kiểm tra điều kiện trước khi chạy" : "Run Preflight Validation"}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors flex items-center space-x-1.5 focus:outline-hidden focus:ring-1 focus:ring-slate-500"
          >
            <ClipboardCheck className="w-3.5 h-3.5 text-blue-400" />
            <span>{lang === 'vi' ? 'Kiểm tra trước khi chạy' : 'Pre-Flight Check'}</span>
          </button>

          {/* Start Lab */}
          <button
            onClick={onStartLab}
            disabled={isLabHealthy || isLabStartingState}
            aria-label={lang === 'vi' ? "Khởi động môi trường thử nghiệm" : "Start Cyber Range Lab"}
            className="px-3 py-1.5 rounded text-xs font-medium bg-emerald-950/60 hover:bg-emerald-900 text-emerald-200 border border-emerald-800/60 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center space-x-1.5 focus:outline-hidden focus:ring-1 focus:ring-emerald-500"
          >
            {isLabStarting ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Server className="w-3.5 h-3.5 text-emerald-400" />
            )}
            <span>{isLabStarting ? (lang === 'vi' ? 'Đang khởi động môi trường...' : 'Starting Lab...') : (lang === 'vi' ? 'Khởi động môi trường' : 'Start Lab')}</span>
          </button>

          {/* Stop Lab */}
          <button
            onClick={onStopLab}
            disabled={rangeState === 'STOPPED' || rangeState === 'UNAVAILABLE' || isLabStopping}
            aria-label={lang === 'vi' ? "Dừng môi trường thử nghiệm" : "Stop Cyber Range Lab"}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-800/60 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center space-x-1.5"
          >
            {isLabStopping ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Power className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span>{isLabStopping ? (lang === 'vi' ? 'Đang dừng môi trường...' : 'Stopping Lab...') : (lang === 'vi' ? 'Dừng môi trường' : 'Stop Lab')}</span>
          </button>
        </div>

        {/* Right: Autonomous Execution & Emergency Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Start Run */}
          <button
            onClick={onOpenStartRun}
            disabled={isRunActive}
            aria-label={lang === 'vi' ? "Bắt đầu lượt chạy tự hành" : "Start Autonomous Run"}
            className="px-4 py-1.5 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center space-x-1.5 shadow-sm focus:outline-hidden focus:ring-2 focus:ring-blue-400"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{lang === 'vi' ? 'Bắt đầu lượt chạy tự hành' : 'Start Autonomous Run'}</span>
          </button>

          {/* Cooperative Pause / Resume */}
          {isRunActive && (
            <>
              {isRunPaused ? (
                <button
                  onClick={onResumeRun}
                  disabled={isRunResuming}
                  aria-label={lang === 'vi' ? "Tiếp tục lượt chạy đã tạm dừng" : "Resume Paused Run"}
                  className="px-3 py-1.5 rounded text-xs font-medium bg-emerald-950/60 hover:bg-emerald-900 text-emerald-200 border border-emerald-800/60 transition-colors disabled:opacity-40 flex items-center space-x-1.5"
                >
                  {isRunResuming ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <PlayCircle className="w-3.5 h-3.5 text-emerald-400" />
                  )}
                  <span>{isRunResuming ? (lang === 'vi' ? 'Đang tiếp tục...' : 'Resuming...') : (lang === 'vi' ? 'Tiếp tục lượt chạy' : 'Resume Run')}</span>
                </button>
              ) : (
                <button
                  onClick={onPauseRun}
                  disabled={!isRunRunning || isRunPausing}
                  aria-label={lang === 'vi' ? "Tạm dừng lượt chạy tại điểm an toàn" : "Cooperative Pause Run"}
                  className="px-3 py-1.5 rounded text-xs font-medium bg-amber-950/60 hover:bg-amber-900 text-amber-200 border border-amber-800/60 transition-colors disabled:opacity-40 flex items-center space-x-1.5"
                >
                  {isRunPausing ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Pause className="w-3.5 h-3.5 text-amber-400" />
                  )}
                  <span>{isRunPausing ? (lang === 'vi' ? 'Đang tạm dừng...' : 'Pausing...') : (lang === 'vi' ? 'Tạm dừng lượt chạy' : 'Pause Run')}</span>
                </button>
              )}
            </>
          )}

          {/* Stop Run */}
          <button
            onClick={onStopRun}
            disabled={!isRunActive || isRunStopping}
            aria-label={lang === 'vi' ? "Dừng lượt chạy hiện tại" : "Stop Active Run"}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center space-x-1.5"
          >
            {isRunStopping ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Square className="w-3.5 h-3.5 text-amber-400 fill-current" />
            )}
            <span>{isRunStopping ? (lang === 'vi' ? 'Đang dừng...' : 'Stopping Run...') : (lang === 'vi' ? 'Dừng lượt chạy' : 'Stop Run')}</span>
          </button>

          {/* Emergency Stop */}
          <button
            onClick={() => setShowEmergencyConfirm(true)}
            disabled={isKillSwitchActive || isEmergencyStopping}
            aria-label={lang === 'vi' ? "Dừng khẩn cấp và kích hoạt công tắc ngắt" : "Emergency Stop and Activate Kill Switch"}
            className={`px-3 py-1.5 rounded text-xs font-semibold transition-all flex items-center space-x-1.5 ${
              isKillSwitchActive
                ? 'bg-rose-950/30 text-rose-400/50 border border-rose-900/40 cursor-not-allowed'
                : 'bg-rose-700 hover:bg-rose-600 text-white shadow-md shadow-rose-950/50 ring-1 ring-rose-500/50'
            }`}
          >
            {isEmergencyStopping ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <AlertOctagon className="w-3.5 h-3.5 text-white" />
            )}
            <span>{isKillSwitchActive ? (lang === 'vi' ? 'Công tắc dừng đang bật' : 'Kill Switch Active') : (lang === 'vi' ? 'DỪNG KHẨN CẤP' : 'Emergency Stop')}</span>
          </button>
        </div>
      </div>

      {/* Emergency Confirmation Modal */}
      {showEmergencyConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-[#151d2e] border border-rose-600/80 rounded-xl p-5 w-full max-w-md shadow-2xl space-y-4">
            <div className="flex items-center space-x-3 text-rose-400">
              <AlertOctagon className="w-6 h-6 shrink-0" />
              <h3 className="text-sm font-bold text-rose-200 uppercase tracking-wider">
                {lang === 'vi' ? 'Kích hoạt công tắc dừng khẩn cấp?' : 'Activate Emergency Kill Switch?'}
              </h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {lang === 'vi'
                ? 'Thao tác này kích hoạt ngay công tắc ngắt khẩn cấp của cổng an toàn trung tâm. Mọi vòng lặp đang chạy sẽ dừng lại và không yêu cầu mạng nào được phép gửi thêm.'
                : 'This triggers the immediate Centralized Safety Gate kill switch. Any active worker loop will be halted and zero subsequent network dispatches will be permitted.'}
            </p>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => setShowEmergencyConfirm(false)}
                className="px-3 py-1.5 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
              >
                {lang === 'vi' ? 'Hủy bỏ' : 'Cancel'}
              </button>
              <button
                onClick={handleConfirmEmergency}
                className="px-4 py-1.5 rounded text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-sm"
              >
                {lang === 'vi' ? 'Xác nhận dừng khẩn cấp' : 'Confirm Emergency Stop'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
