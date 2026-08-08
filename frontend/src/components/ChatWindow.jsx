import { useEffect, useRef, useState } from 'react';
import { askQuestion } from '../api/client';
import AgentSteps from './AgentSteps';
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

  const bottomRef = useRef(null);

  // Follow the conversation as it grows, including while steps stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, steps]);

  async function send(question) {
    const trimmed = question.trim();
    if (!trimmed || isBusy) return;

    setMessages((current) => [...current, { role: 'user', content: trimmed }]);
    setInput('');
    setSteps([]);
    setError(null);
    setIsBusy(true);

    try {
      const result = await askQuestion(trimmed, (step) =>
        setSteps((current) => [...current, step])
      );

      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: result.answer,
          citations: result.citations,
          isGrounded: result.is_grounded,
        },
      ]);
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
      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-2xl pt-12 text-center">
            <h2 className="text-xl font-semibold text-slate-200">
              Ask about American Express open-source projects
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Answers come only from the indexed repositories, and every claim
              links back to the file it came from.
            </p>

            <div className="mt-8 grid gap-2 text-left sm:grid-cols-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => send(example)}
                  className="rounded-lg border border-slate-700 bg-slate-800/40 p-3 text-sm text-slate-300 transition-colors hover:border-sky-600 hover:bg-slate-800"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((message, index) => (
            <MessageBubble key={index} message={message} />
          ))}

          {isBusy && <AgentSteps steps={steps} done={false} />}

          {error && (
            <div className="animate-fade-up rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-slate-800 bg-slate-900/80 px-4 py-4">
        <div className="mx-auto flex max-w-3xl gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Ask a question..."
            disabled={isBusy}
            className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-slate-200 placeholder-slate-500 outline-none focus:border-sky-600 disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={isBusy || !input.trim()}
            className="rounded-lg bg-sky-600 px-5 py-2.5 font-medium text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isBusy ? 'Thinking' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  );
}
