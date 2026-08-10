import { useEffect, useState } from 'react';
import { checkHealth } from './api/client';
import ChatWindow from './components/ChatWindow';
import EvalPanel from './components/EvalPanel';

const TABS = [
  ['chat', 'Chat'],
  ['eval', 'Evaluation'],
];

/** Page shell: a header with backend status, and the active view below it. */
export default function App() {
  const [isBackendUp, setIsBackendUp] = useState(null);
  const [tab, setTab] = useState('chat');

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

          <div className="flex items-center gap-4">
            {/* The evaluation is the substance of this project, so it is one
                click away rather than something you read about in a README. */}
            <nav className="flex gap-1 rounded-lg bg-slate-800/60 p-0.5">
              {TABS.map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`rounded-md px-3 py-1 text-xs transition-colors ${
                    tab === id
                      ? 'bg-slate-700 text-slate-100'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>

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
        </div>
      </header>

      {/* The chat keeps its own scroll region; the evaluation panel scrolls
          normally, so overflow is set per view rather than on the shell. */}
      <main className="flex-1 overflow-hidden">
        {tab === 'chat' ? (
          <ChatWindow />
        ) : (
          <div className="h-full overflow-y-auto">
            <EvalPanel />
          </div>
        )}
      </main>
    </div>
  );
}
