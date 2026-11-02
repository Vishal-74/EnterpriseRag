export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-white/60 px-6 py-16 text-center text-mist">
      <div className="mx-auto mb-3 h-2 w-24 animate-pulse rounded-full bg-line" />
      {label}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-6 py-14 text-center">
      <h2 className="font-display text-2xl text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-mist">{body}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 px-6 py-8 text-red-900">
      <p>{message}</p>
      {onRetry ? (
        <button className="mt-4 underline" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}
