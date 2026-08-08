import { useEffect, useState } from 'react';
import { checkHealth } from './api/client';
import ChatWindow from './components/ChatWindow';

/** Page shell: a header with backend status, and the conversation below it. */
export default function App() {
  const [isBackendUp, setIsBackendUp] = useState(null);

  // Checked once on load. A dead backend looks identical to a slow agent
  // otherwise, and the first thing anyone asks is "is it even running".
  useEffect(() => {
    checkHealth().then(setIsBackendUp);
  }, []);

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-200">
      <header className="border-b border-slate-800 px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div>
            <h1 className="font-semibold text-slate-100">
              Amex Developer Copilot
            </h1>
            <p className="text-xs text-slate-500">
              Grounded answers over American Express open-source repositories
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${
                isBackendUp === null
                  ? 'bg-slate-600'
                  : isBackendUp
                    ? 'bg-emerald-500'
                    : 'bg-red-500'
              }`}
            />
            <span className="text-slate-500">
              {isBackendUp === null
                ? 'Checking'
                : isBackendUp
                  ? 'Connected'
                  : 'Backend unreachable'}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <ChatWindow />
      </main>
    </div>
  );
}
