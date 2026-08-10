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
    : 'animate-fade-up rounded-lg border border-slate-700 bg-slate-800/40 p-3';

  return (
    <div className={`${frame} text-sm`}>
      <ol className="space-y-1.5">
        {steps.map((step, index) => {
          const isCurrent = !done && index === steps.length - 1;

          return (
            <li key={index} className="flex items-start gap-2">
              <span
                className={
                  isCurrent ? 'mt-0.5 text-sky-400' : 'mt-0.5 text-emerald-500'
                }
              >
                {isCurrent ? '>' : 'v'}
              </span>
              <span className="flex-1">
                <span
                  className={isCurrent ? 'text-slate-200' : 'text-slate-400'}
                >
                  {step.label}
                </span>
                {step.detail && (
                  <span className="ml-2 break-all font-mono text-xs text-slate-500">
                    {step.detail}
                  </span>
                )}
              </span>
              {isCurrent && <LoadingDots />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
