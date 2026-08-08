/** Three pulsing dots, shown while the agent is working. */
export default function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}
