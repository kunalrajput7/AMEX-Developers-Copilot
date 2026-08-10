import { useEffect, useState } from 'react';

/**
 * Reveal finished text progressively.
 *
 * Worth being precise about what this is: the answer arrives complete, in one
 * event, and this animates its appearance. It is not token streaming.
 *
 * It could not be. The agent writes a draft, then checks every claim against
 * the sources, and throws the draft away and rewrites it if the check fails.
 * Streaming the model's tokens would show text that sometimes vanishes and is
 * replaced — the citation guarantee is worth more than the few seconds saved.
 *
 * Speed adapts to length so a long answer does not crawl.
 */
const TICK_MS = 16;
const TARGET_MS = 2200;
const MIN_CHARS_PER_TICK = 2;

export default function useTypewriter(text, enabled) {
  const [count, setCount] = useState(enabled ? 0 : text.length);

  useEffect(() => {
    if (!enabled) {
      setCount(text.length);
      return undefined;
    }

    setCount(0);
    const step = Math.max(
      MIN_CHARS_PER_TICK,
      Math.ceil(text.length / (TARGET_MS / TICK_MS))
    );

    const timer = setInterval(() => {
      setCount((shown) => {
        if (shown >= text.length) return shown;
        return Math.min(shown + step, text.length);
      });
    }, TICK_MS);

    return () => clearInterval(timer);
  }, [text, enabled]);

  return {
    visible: text.slice(0, count),
    isTyping: count < text.length,
    // Lets a reader who does not want the animation jump to the end.
    finish: () => setCount(text.length),
  };
}
