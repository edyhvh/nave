/// <reference path="../types/shims.d.ts" />

function ArrowUpIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true">
      <path d="M12 5l6 6h-4v8h-4v-8H6l6-6z" fill="currentColor" />
    </svg>
  );
}

function ArrowDownIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true">
      <path d="M12 19l-6-6h4V5h4v8h4l-6 6z" fill="currentColor" />
    </svg>
  );
}

export default function HeaderCards() {
  return (
    <section className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-3xl border border-border bg-sage p-8 shadow-card">
        <div className="flex items-center gap-4 text-sageDeep">
          <span className="rounded-full bg-white/70 p-3">
            <ArrowUpIcon />
          </span>
          <span className="text-sm font-semibold uppercase tracking-wide">
            Long
          </span>
        </div>
        <h1 className="mt-6 text-3xl font-semibold text-ink">
          Sesgo comprador y continuidad.
        </h1>
        <p className="mt-2 text-sm text-ink/70">
          Buscar estructuras de maximos y minimos ascendentes.
        </p>
      </div>
      <div className="rounded-3xl border border-border bg-orange p-8 shadow-card">
        <div className="flex items-center gap-4 text-orangeDeep">
          <span className="rounded-full bg-white/70 p-3">
            <ArrowDownIcon />
          </span>
          <span className="text-sm font-semibold uppercase tracking-wide">
            Short
          </span>
        </div>
        <h2 className="mt-6 text-3xl font-semibold text-ink">
          Sesgo vendedor y retroceso.
        </h2>
        <p className="mt-2 text-sm text-ink/70">
          Priorizar quiebres y fallos de estructura.
        </p>
      </div>
    </section>
  );
}
