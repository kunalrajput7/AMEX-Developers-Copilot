import ReactMarkdown from 'react-markdown';
import CitationCard from './CitationCard';

/**
 * One message in the conversation.
 *
 * Questions render as plain text on the right. Answers render as markdown on
 * the left, followed by the sources they cite.
 */
export default function MessageBubble({ message }) {
  if (message.role === 'user') {
    return (
      <div className="animate-fade-up flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-sky-600 px-4 py-2.5 text-white">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-3">
      <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-700 bg-slate-800/60 px-4 py-3">
        <div className="markdown text-slate-200">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>

        {/* The agent reports when it could not trace every claim to a source.
            Surfacing that is more useful than hiding it -- the answer may
            still be right, but the reader deserves to know it is unverified. */}
        {message.isGrounded === false && (
          <p className="mt-3 rounded border border-amber-700/40 bg-amber-900/20 px-2.5 py-1.5 text-xs text-amber-300">
            Some claims in this answer could not be traced back to a source.
            Check the citations before relying on it.
          </p>
        )}
      </div>

      {message.citations?.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Sources
          </h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {message.citations.map((citation, index) => (
              <CitationCard
                key={`${citation.source_url}-${index}`}
                citation={citation}
                index={index + 1}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
