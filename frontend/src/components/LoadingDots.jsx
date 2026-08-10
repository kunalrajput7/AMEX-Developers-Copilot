/** Three dots rising in sequence, shown while the agent is working. */
export default function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-[3px]">
      {[0, 160, 320].map((delay) => (
        <span
          key={delay}
          className="h-1 w-1 rounded-full bg-faint"
          style={{
            animation: 'caret-blink 1.2s ease-in-out infinite',
            animationDelay: `${delay}ms`,
          }}
        />
      ))}
    </span>
  );
}
