import LoadingDots from './LoadingDots';

/**
 * The agent's progress.
 *
 * Worth showing rather than a spinner: the agent genuinely takes 15-30 seconds,
 * and watching it search, reject weak sources, and search again is the most
 * interesting thing it does. A spinner would just look broken.
 *
 * Shown live while it works, and again -- collapsed, with `bare` -- inside the
 * finished message, so the reasoning behind an answer stays inspectable.
 */
export default function AgentSteps({ steps, done, bare = false }) {
  if (steps.length === 0) return null;

  const frame = bare
    ? ''
    : 'animate-fade-up rounded-xl border border-line bg-surface px-3.5 py-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]';

  return (
    <div className={frame}>
      <ol className="space-y-2">
        {steps.map((step, index) => {
          const isCurrent = !done && index === steps.length - 1;

          return (
            <li key={index} className="flex items-start gap-2.5 text-sm">
              {/* A filled dot for finished steps, a ring for the one running. */}
              <span
                className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${
                  isCurrent
                    ? 'bg-accent ring-4 ring-accent/15'
                    : 'bg-line-strong'
                }`}
              />
              <span className="min-w-0 flex-1">
                <span
                  className={
                    isCurrent ? 'font-medium text-ink' : 'text-muted'
                  }
                >
                  {step.label}
                </span>
                {step.detail && (
                  <span className="ml-2 break-all font-mono text-[11px] text-faint">
                    {step.detail}
                  </span>
                )}
              </span>
              {isCurrent && (
                <span className="mt-1.5 shrink-0">
                  <LoadingDots />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
