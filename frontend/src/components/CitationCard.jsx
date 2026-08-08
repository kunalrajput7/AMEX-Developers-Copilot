/** Colour per source type, so docs, code, and issues are distinguishable. */
const TYPE_STYLES = {
  doc: 'bg-sky-500/15 text-sky-300',
  code: 'bg-violet-500/15 text-violet-300',
  issue: 'bg-amber-500/15 text-amber-300',
};

/**
 * One source behind an answer, linking to the exact file on GitHub.
 *
 * The number matches the [n] marker in the answer text, and the backend only
 * returns sources the answer actually cited -- so every card here backs
 * something that was said.
 */
export default function CitationCard({ citation, index }) {
  const badge = TYPE_STYLES[citation.chunk_type] || 'bg-slate-600 text-slate-200';

  return (
    <a
      href={citation.source_url}
      target="_blank"
      rel="noreferrer"
      className="block rounded-lg border border-slate-700 bg-slate-800/50 p-3 transition-colors hover:border-sky-600 hover:bg-slate-800"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs text-slate-500">[{index}]</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${badge}`}>
          {citation.chunk_type}
        </span>
        <span className="truncate font-mono text-xs text-slate-300">
          {citation.file_path}
        </span>
      </div>

      <div className="mt-1 truncate text-xs text-slate-500">{citation.repo}</div>

      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-400">
        {citation.snippet}
      </p>
    </a>
  );
}
