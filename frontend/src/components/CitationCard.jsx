/** Colour per source type, so docs, code, and issues are distinguishable. */
const TYPE_STYLES = {
  doc: 'bg-sky-50 text-sky-700 ring-sky-200/70',
  code: 'bg-violet-50 text-violet-700 ring-violet-200/70',
  issue: 'bg-amber-50 text-amber-700 ring-amber-200/70',
};

/**
 * One source behind an answer, linking to the exact file on GitHub.
 *
 * The number matches the [n] marker in the answer text, and the backend only
 * returns sources the answer actually cited -- so every card here backs
 * something that was said.
 */
export default function CitationCard({ citation, index }) {
  const badge =
    TYPE_STYLES[citation.chunk_type] || 'bg-sunken text-muted ring-line';

  return (
    <a
      href={citation.source_url}
      target="_blank"
      rel="noreferrer"
      className="group block rounded-lg border border-line bg-surface p-3 transition-all hover:border-line-strong hover:shadow-[0_2px_8px_rgba(0,0,0,0.06)]"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[11px] text-faint">[{index}]</span>
        <span
          className={`rounded px-1.5 py-px text-[10px] font-medium uppercase tracking-wide ring-1 ring-inset ${badge}`}
        >
          {citation.chunk_type}
        </span>
        <span className="truncate font-mono text-xs text-ink group-hover:text-accent">
          {citation.file_path}
        </span>
      </div>

      <div className="mt-1 truncate text-[11px] text-faint">
        {citation.repo}
      </div>

      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted">
        {citation.snippet}
      </p>
    </a>
  );
}
