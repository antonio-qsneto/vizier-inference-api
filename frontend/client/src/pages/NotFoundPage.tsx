import { Link } from "wouter";
import { Panel } from "@/components/primitives";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Panel className="w-full max-w-2xl space-y-5 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
          404
        </p>
        <h1 className="text-3xl font-semibold text-white">Rota não encontrada</h1>
        <p className="text-sm leading-7 text-slate-300">
          Use o menu lateral para voltar ao espaço de trabalho principal.
        </p>
        <Link href="/dashboard">
          <a className="inline-flex rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400">
            Abrir painel
          </a>
        </Link>
      </Panel>
    </div>
  );
}
