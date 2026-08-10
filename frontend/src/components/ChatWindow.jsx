import { useEffect, useRef, useState } from 'react';
import { askQuestion } from '../api/client';
import AgentSteps from './AgentSteps';
import LoadingDots from './LoadingDots';
import MessageBubble from './MessageBubble';

const EXAMPLES = [
  'How do I authenticate with the Amex API using the Java client?',
  'What does failureThreshold control in jest-image-snapshot?',
  'How do I make EarlyBird scan only files staged in git?',
  'How do I fetch data in a React component using fetchye?',
];

/** The conversation: message list, live agent progress, and the input box. */
export default function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [steps, setSteps] = useState([]);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState(null);

  // Only the newest answer animates in. Appending the next message flips this,
  // which completes the previous one instantly instead of replaying it.
  const [animatingIndex, setAnimatingIndex] = useState(-1);

  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Follow the conversation as it grows, including while steps stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, steps]);

  // Put the cursor back in the box once an answer lands, so a follow-up is
  // just typing rather than typing after a click.
  useEffect(() => {
    if (!isBusy) inputRef.current?.focus();
  }, [isBusy]);

  async function send(question) {
    const trimmed = question.trim();
    if (!trimmed || isBusy) return;

    // Captured before the new question is appended: the agent needs what came
    // *before* this turn. Only role and content go over the wire — citations
    // and grounding flags are for rendering, not for the model to re-read.
    const history = messages.map(({ role, content }) => ({ role, content }));

    setMessages((current) => [...current, { role: 'user', content: trimmed }]);
    setInput('');
    setSteps([]);
    setError(null);
    setIsBusy(true);

    try {
      const collected = [];
      const result = await askQuestion(trimmed, history, (step) => {
        collected.push(step);
        setSteps([...collected]);
      });

      setMessages((current) => {
        setAnimatingIndex(current.length);
        return [
          ...current,
          {
            role: 'assistant',
            content: result.answer,
            citations: result.citations,
            isGrounded: result.is_grounded,
            // Kept with the message so the reasoning survives the next
            // question, instead of being wiped with the live step list.
            steps: collected,
            searchCount: result.searches?.length ?? 0,
          },
        ];
      });
    } catch (failure) {
      setError(failure.message);
    } finally {
      setIsBusy(false);
      setSteps([]);
    }
  }

  function handleKeyDown(event) {
    // Enter sends; Shift+Enter starts a new line, as in most chat apps.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send(input);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-5 py-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-2xl pt-10 pb-2 sm:pt-16">
            <h2 className="text-center text-2xl font-semibold tracking-tight text-ink">
              Ask about American Express open-source projects
            </h2>
            <p className="mx-auto mt-2 max-w-md text-center text-sm leading-relaxed text-muted">
              Answers come only from the indexed repositories, and every claim
              links back to the file it came from.
            </p>

            <div className="mt-9 grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => send(example)}
                  className="group rounded-xl border border-line bg-surface p-3.5 text-left text-sm leading-snug text-muted transition-all hover:border-line-strong hover:text-ink hover:shadow-[0_2px_8px_rgba(0,0,0,0.06)]"
                >
                  {example}
                  <span className="mt-1.5 block text-xs text-faint opacity-0 transition-opacity group-hover:opacity-100">
                    Ask this &rarr;
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((message, index) => (
            <MessageBubble
              key={index}
              message={message}
              animate={index === animatingIndex}
            />
          ))}

          {/* The first step takes a couple of seconds to arrive, and an empty
              screen in that gap reads as a hang. Something moves immediately. */}
          {isBusy && steps.length === 0 && (
            <div className="animate-fade-up flex items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-3 text-sm text-muted shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
              <LoadingDots />
              <span>Thinking</span>
            </div>
          )}

          {isBusy && steps.length > 0 && (
            <AgentSteps steps={steps} done={false} />
          )}

          {error && (
            <div className="animate-fade-up rounded-xl border border-bad/25 bg-bad/5 px-3.5 py-3 text-sm text-bad">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-line bg-surface/80 px-5 py-4 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-xl border border-line bg-surface p-1.5 shadow-[0_1px_3px_rgba(0,0,0,0.05)] transition-colors focus-within:border-line-strong">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder="Ask a question..."
              disabled={isBusy}
              className="max-h-40 flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-ink placeholder-faint outline-none disabled:opacity-50"
            />
            <button
              onClick={() => send(input)}
              disabled={isBusy || !input.trim()}
              className="shrink-0 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-25"
            >
              {isBusy ? 'Thinking' : 'Ask'}
            </button>
          </div>

          <p className="mt-2 text-center text-[11px] text-faint">
            Answers are grounded in indexed repositories. Every claim cites its
            source.
          </p>
        </div>
      </div>
    </div>
  );
}
