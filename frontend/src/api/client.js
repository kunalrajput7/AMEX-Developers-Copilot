/**
 * Talking to the backend.
 *
 * The agent takes 15-30 seconds and makes several model calls, so the useful
 * thing to stream is its progress -- "searching code", "checking citations" --
 * rather than tokens. The backend sends those as server-sent events.
 *
 * EventSource cannot send a POST body, so this reads the response stream by
 * hand. That is the only reason this file is more than a fetch call.
 */

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Ask a question, calling onStep as the agent works and returning the answer.
 *
 * History travels with every request rather than living on the server. That
 * keeps the backend stateless — no sessions to expire, no chance of one
 * conversation reaching another — and lets any surface hold a conversation.
 *
 * @param {string} question
 * @param {{role: 'user'|'assistant', content: string}[]} history earlier turns, oldest first
 * @param {(step: {step: string, label: string, detail: string}) => void} onStep
 * @param {AbortSignal} [signal]
 * @returns {Promise<{answer: string, citations: object[], is_grounded: boolean, searches: string[]}>}
 */
export async function askQuestion(question, history, onStep, signal) {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  // Events arrive as "data: {...}\n\n", but a network chunk can split one in
  // half, so completed events are taken off the front and the remainder is
  // carried into the next read.
  let buffer = '';
  let result = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split('\n\n');
    buffer = parts.pop();

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;

      const event = JSON.parse(line.slice(5).trim());

      if (event.type === 'step') {
        onStep(event);
      } else if (event.type === 'answer') {
        result = event;
      } else if (event.type === 'error') {
        throw new Error(event.message);
      }
    }
  }

  if (!result) {
    throw new Error('The agent finished without producing an answer.');
  }

  return result;
}

/** Return true if the backend is up and its database is ready. */
export async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/health/db`);
    const data = await response.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}
