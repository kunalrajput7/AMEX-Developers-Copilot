import ReactMarkdown from 'react-markdown';
import CitationCard from './CitationCard';
import AgentSteps from './AgentSteps';
import useTypewriter from '../hooks/useTypewriter';

/**
 * One message in the conversation.
 *
 * Questions render as a solid bubble on the right. Answers render as markdown
 * on a plain card, preceded by what the agent did to get there and followed by
 * the sources they cite.
 */
export default function MessageBubble({ message, animate = false }) {
  const { visible, isTyping, finish } = useTypewriter(
    message.content ?? '',
    animate
  );

  if (message.role === 'user') {
    return (
      <div className="animate-fade-up flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-2.5">
      {/* The reasoning stays available after the answer arrives. Watching it
          live is the interesting part, but "why did it say that" is asked
          afterwards -- so it collapses rather than disappearing. */}
      {message.steps?.length > 0 && (
        <details className="group w-fit max-w-full overflow-hidden rounded-lg border border-line bg-surface">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-1.5 text-xs text-muted transition-colors hover:bg-sunken">
            <span className="text-faint transition-transform group-open:rotate-90">
              &rsaquo;
            </span>
            <span className="font-medium">Thought</span>
            <span className="text-faint">
              {message.steps.length} steps
              {message.searchCount > 0 &&
                ` · ${message.searchCount} ${
                  message.searchCount === 1 ? 'search' : 'searches'
                }`}
            </span>
          </summary>
          <div className="border-t border-line bg-sunken/50 px-3 py-2.5">
            <AgentSteps steps={message.steps} done bare />
          </div>
        </details>
      )}

      <div
        className="rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
        onClick={isTyping ? finish : undefined}
        title={isTyping ? 'Click to show the whole answer' : undefined}
      >
        <div className={`markdown ${isTyping ? 'caret' : ''}`}>
          <ReactMarkdown>{visible}</ReactMarkdown>
        </div>

        {/* The agent reports when it could not trace every claim to a source.
            Surfacing that is more useful than hiding it -- the answer may
            still be right, but the reader deserves to know it is unverified.
            Held back until the text finishes so it cannot flash mid-reveal. */}
        {message.isGrounded === false && !isTyping && (
          <p className="mt-3 rounded-md border border-warn/25 bg-warn/5 px-3 py-2 text-xs leading-relaxed text-warn">
            Some claims in this answer could not be traced back to a source.
            Check the citations before relying on it.
          </p>
        )}
      </div>

      {message.citations?.length > 0 && !isTyping && (
        <div className="pt-1">
          <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-faint">
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
