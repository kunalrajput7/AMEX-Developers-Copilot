import ReactMarkdown from 'react-markdown';
import CitationCard from './CitationCard';
import AgentSteps from './AgentSteps';
import useTypewriter from '../hooks/useTypewriter';

/**
 * One message in the conversation.
 *
 * Questions render as plain text on the right. Answers render as markdown on
 * the left, preceded by what the agent did to get there and followed by the
 * sources they cite.
 */
export default function MessageBubble({ message, animate = false }) {
  const { visible, isTyping, finish } = useTypewriter(
    message.content ?? '',
    animate
  );

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
      {/* The reasoning stays available after the answer arrives. Watching it
          live is the interesting part, but "why did it say that" is asked
          afterwards -- so it collapses rather than disappearing. */}
      {message.steps?.length > 0 && (
        <details className="group rounded-lg border border-slate-700/70 bg-slate-800/30">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-slate-400 hover:text-slate-200">
            <span className="transition-transform group-open:rotate-90">
              &rsaquo;
            </span>
            <span>Thought</span>
            <span className="text-slate-600">
              {message.steps.length} steps
              {message.searchCount > 0 &&
                ` · ${message.searchCount} ${
                  message.searchCount === 1 ? 'search' : 'searches'
                }`}
            </span>
          </summary>
          <div className="border-t border-slate-700/70 p-3 pt-2">
            <AgentSteps steps={message.steps} done bare />
          </div>
        </details>
      )}

      <div
        className="max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-700 bg-slate-800/60 px-4 py-3"
        onClick={isTyping ? finish : undefined}
        title={isTyping ? 'Click to show the whole answer' : undefined}
      >
        <div className="markdown text-slate-200">
          <ReactMarkdown>{visible}</ReactMarkdown>
        </div>

        {/* The agent reports when it could not trace every claim to a source.
            Surfacing that is more useful than hiding it -- the answer may
            still be right, but the reader deserves to know it is unverified.
            Held back until the text finishes so it cannot flash mid-reveal. */}
        {message.isGrounded === false && !isTyping && (
          <p className="mt-3 rounded border border-amber-700/40 bg-amber-900/20 px-2.5 py-1.5 text-xs text-amber-300">
            Some claims in this answer could not be traced back to a source.
            Check the citations before relying on it.
          </p>
        )}
      </div>

      {message.citations?.length > 0 && !isTyping && (
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
