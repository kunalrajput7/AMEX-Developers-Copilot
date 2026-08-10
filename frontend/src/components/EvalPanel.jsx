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

function SummaryCard({ value, label, tone = 'text-ink' }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className={`truncate text-xl font-semibold tracking-tight ${tone}`}>
        {value}
      </div>
      <div className="mt-0.5 text-xs text-faint">{label}</div>
    </div>
  );
}

function MetricRow({ metric }) {
  const percent = Math.round(metric.score * 100);
  const floor = metric.threshold;

  return (
    <div className="border-t border-line px-4 py-3.5 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[13px] font-medium text-ink">
          {metric.name}
        </span>
        <span
          className={`font-mono text-[13px] tabular-nums ${
            metric.passing ? 'text-good' : 'text-bad'
          }`}
        >
          {metric.score.toFixed(3)}
        </span>
      </div>

      <p className="mt-1 text-xs leading-relaxed text-muted">{metric.help}</p>

      {/* The bar shows the score; the notch shows the floor that gates CI. */}
      <div className="relative mt-2.5 h-1.5 w-full overflow-visible rounded-full bg-sunken">
        <div
          className={`h-1.5 rounded-full ${
            metric.passing ? 'bg-good/70' : 'bg-bad/70'
          }`}
          style={{ width: `${percent}%` }}
        />
        {floor != null && (
          <div
            className="absolute -top-1 h-3.5 w-px bg-ink/40"
            style={{ left: `${Math.round(floor * 100)}%` }}
            title={`Build fails below ${floor}`}
          />
        )}
      </div>

      <div className="mt-1.5 flex justify-between text-[11px] text-faint">
        <span>
          {metric.judged ? 'judged by model' : 'exact, URL comparison'}
        </span>
        {floor != null && <span>floor {floor}</span>}
      </div>
    </div>
  );
}

export default function EvalPanel() {
  const [data, setData] = useState(undefined);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchEvaluation()
      .then(setData)
      .catch((failure) => setError(failure.message));
  }, []);

  if (error) {
    return (
      <p className="mx-auto max-w-3xl px-5 py-10 text-sm text-bad">{error}</p>
    );
  }

  if (data === undefined) {
    return (
      <p className="mx-auto max-w-3xl px-5 py-10 text-sm text-faint">
        Loading evaluation results...
      </p>
    );
  }

  if (data === null) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-10 text-sm text-muted">
        <p className="font-medium text-ink">No evaluation has been run yet.</p>
        <p className="mt-2 leading-relaxed">
          Run it with{' '}
          <code className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink">
            python eval/run_eval.py
          </code>{' '}
          in the backend folder. It takes about 20 minutes and makes real model
          calls.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-5 py-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-ink">
          How well does it actually work?
        </h2>
        <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
          Every answer below was scored against a hand-written reference set. An
          independent model does the grading, and if any metric falls under its
          floor the build fails.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryCard
          value={
            <>
              {data.passed}
              <span className="text-base font-normal text-faint">
                /{data.total}
              </span>
            </>
          }
          label="questions passed"
        />
        <SummaryCard
          value={data.gate_passing ? 'Passing' : 'Failing'}
          label="CI threshold gate"
          tone={data.gate_passing ? 'text-good' : 'text-bad'}
        />
        <SummaryCard
          value={
            <span className="text-sm font-medium">
              {data.judge || 'not recorded'}
            </span>
          }
          label="grading model"
        />
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
        {data.metrics.map((metric) => (
          <MetricRow key={metric.name} metric={metric} />
        ))}
      </div>

      {data.failures.length > 0 && (
        <div>
          <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-faint">
            Failing questions
          </h3>
          <ul className="space-y-2">
            {data.failures.map((failure) => (
              <li
                key={failure.question}
                className="rounded-lg border border-warn/25 bg-warn/5 px-3.5 py-2.5 text-sm text-ink"
              >
                <span className="mr-2 font-mono text-xs text-warn">
                  {failure.failure}
                </span>
                {failure.question}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t border-line pt-4 text-xs leading-relaxed text-faint">
        Measured {formatRunTime(data.run_at)}. Read the spread, not the single
        number: identical code re-run varies by 0.04&ndash;0.08 on every metric,
        because the agent writes its own search queries and model inference is
        not bit-deterministic. The floors sit about two questions below the
        measured scores for that reason.
      </p>
    </div>
  );
}
