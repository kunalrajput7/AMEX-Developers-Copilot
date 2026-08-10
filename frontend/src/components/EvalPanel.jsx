import { useEffect, useState } from 'react';
import { fetchEvaluation } from '../api/client';

/**
 * How well the agent actually performs, from the last recorded evaluation run.
 *
 * Read from the same JSON file CI reads, not typed in here — a panel that can
 * disagree with the build gate is worse than no panel.
 */

/** Format a run stamp of "20260809-025440" as "9 Aug 2026, 02:54 UTC". */
function formatRunTime(stamp) {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(stamp ?? '');
  if (!match) return stamp || 'unknown';

  const [, year, month, day, hour, minute] = match;
  const date = new Date(Date.UTC(+year, +month - 1, +day));
  const label = date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
  return `${label}, ${hour}:${minute} UTC`;
}

function MetricRow({ metric }) {
  const percent = Math.round(metric.score * 100);
  const floor = metric.threshold;

  return (
    <div className="border-t border-slate-800 py-3 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-sm text-slate-200">{metric.name}</span>
        <span
          className={`font-mono text-sm ${
            metric.passing ? 'text-emerald-400' : 'text-red-400'
          }`}
        >
          {metric.score.toFixed(3)}
        </span>
      </div>

      <p className="mt-0.5 text-xs text-slate-500">{metric.help}</p>

      {/* The bar shows the score; the notch shows the floor that gates CI. */}
      <div className="relative mt-2 h-1.5 w-full rounded-full bg-slate-800">
        <div
          className={`h-1.5 rounded-full ${
            metric.passing ? 'bg-emerald-500/70' : 'bg-red-500/70'
          }`}
          style={{ width: `${percent}%` }}
        />
        {floor != null && (
          <div
            className="absolute -top-0.5 h-2.5 w-0.5 bg-slate-400"
            style={{ left: `${Math.round(floor * 100)}%` }}
            title={`Build fails below ${floor}`}
          />
        )}
      </div>

      <div className="mt-1 flex justify-between text-[11px] text-slate-600">
        <span>{metric.judged ? 'judged by model' : 'exact, URL comparison'}</span>
        {floor != null && <span>floor {floor}</span>}
      </div>
    </div>
  );
}

export default function EvalPanel() {
  const [data, setData] = useState(undefined);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchEvaluation().then(setData).catch((failure) => setError(failure.message));
  }, []);

  if (error) {
    return (
      <p className="mx-auto max-w-3xl px-4 py-8 text-sm text-red-400">{error}</p>
    );
  }

  if (data === undefined) {
    return (
      <p className="mx-auto max-w-3xl px-4 py-8 text-sm text-slate-500">
        Loading evaluation results...
      </p>
    );
  }

  if (data === null) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 text-sm text-slate-400">
        <p>No evaluation has been run yet.</p>
        <p className="mt-2 text-slate-500">
          Run it with{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs">
            python eval/run_eval.py
          </code>{' '}
          in the backend folder. It takes about 20 minutes and makes real model
          calls.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          How well does it actually work?
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Every answer below was scored against a hand-written reference set. An
          independent model does the grading, and if any metric falls under its
          floor the build fails.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
          <div className="text-2xl font-semibold text-slate-100">
            {data.passed}
            <span className="text-base text-slate-500">/{data.total}</span>
          </div>
          <div className="text-xs text-slate-500">questions passed</div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
          <div
            className={`text-2xl font-semibold ${
              data.gate_passing ? 'text-emerald-400' : 'text-red-400'
            }`}
          >
            {data.gate_passing ? 'Passing' : 'Failing'}
          </div>
          <div className="text-xs text-slate-500">CI threshold gate</div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
          <div className="truncate text-sm font-medium text-slate-200">
            {data.judge || 'not recorded'}
          </div>
          <div className="text-xs text-slate-500">grading model</div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-800/20 px-4">
        {data.metrics.map((metric) => (
          <MetricRow key={metric.name} metric={metric} />
        ))}
      </div>

      {data.failures.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Failing questions
          </h3>
          <ul className="space-y-1.5">
            {data.failures.map((failure) => (
              <li
                key={failure.question}
                className="rounded border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-sm text-slate-300"
              >
                <span className="mr-2 font-mono text-xs text-amber-400">
                  {failure.failure}
                </span>
                {failure.question}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs leading-relaxed text-slate-600">
        Measured {formatRunTime(data.run_at)}. Read the spread, not the single
        number: identical code re-run varies by 0.04&ndash;0.08 on every metric,
        because the agent writes its own search queries and model inference is
        not bit-deterministic. The floors sit about two questions below the
        measured scores for that reason.
      </p>
    </div>
  );
}
