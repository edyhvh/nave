type SectionCardProps = {
  id: string;
  title: string;
  summary: string;
  children?: unknown;
};

export default function SectionCard({
  id,
  title,
  summary,
  children,
}: SectionCardProps) {
  return (
    <details
      id={id}
      className="group rounded-3xl border border-border bg-white p-6 shadow-card transition hover:shadow-lg"
      open
    >
      <summary className="flex cursor-pointer items-center justify-between gap-6">
        <div>
          <h3 className="text-xl font-semibold text-ink">{title}</h3>
          <p className="mt-1 text-sm text-ink/70">{summary}</p>
        </div>
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-border text-sm font-semibold text-ink">
          +
        </span>
      </summary>
      <div className="mt-6 rounded-2xl border border-border bg-canvas p-4">
        {children}
      </div>
      <p className="mt-4 text-sm text-ink/70">
        Contenido en desarrollo. Se refinara con ejemplos y reglas detalladas.
      </p>
    </details>
  );
}
