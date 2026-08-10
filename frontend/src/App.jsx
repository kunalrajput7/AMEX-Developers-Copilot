import { useEffect, useState } from 'react';
import { checkHealth } from './api/client';
import ChatWindow from './components/ChatWindow';
import EvalPanel from './components/EvalPanel';

const TABS = [
  ['chat', 'Chat'],
  ['eval', 'Evaluation'],
];

const STATUS = {
  null: ['bg-faint', 'Checking'],
  true: ['bg-good', 'Connected'],
  false: ['bg-bad', 'Backend unreachable'],
};

/** Page shell: a header with backend status, and the active view below it. */
export default function App() {
  const [isBackendUp, setIsBackendUp] = useState(null);
  const [tab, setTab] = useState('chat');

  // Checked once on load. A dead backend looks identical to a slow agent
  // otherwise, and the first thing anyone asks is "is it even running".
  useEffect(() => {
    checkHealth().then(setIsBackendUp);
  }, []);

  const [dot, label] = STATUS[String(isBackendUp)];

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <header className="border-b border-line bg-surface/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-3">
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-semibold tracking-tight">
              Amex Developer Copilot
            </h1>
            <p className="truncate text-xs text-faint">
              Grounded answers over American Express open-source repositories
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {/* The evaluation is the substance of this project, so it is one
                click away rather than something you read about in a README. */}
            <nav className="flex gap-0.5 rounded-lg bg-sunken p-0.5">
              {TABS.map(([id, text]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`rounded-[6px] px-3 py-1.5 text-xs font-medium transition-all ${
                    tab === id
                      ? 'bg-surface text-ink shadow-sm ring-1 ring-line'
                      : 'text-muted hover:text-ink'
                  }`}
                >
                  {text}
                </button>
              ))}
            </nav>

            <div
              className="flex items-center gap-1.5 text-xs text-muted"
              title={label}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              <span className="hidden sm:inline">{label}</span>
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
