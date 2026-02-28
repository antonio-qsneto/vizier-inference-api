import { Link } from "wouter";
import { Panel } from "@/components/primitives";

export default function BillingResultPage({ status }: { status: "success" | "cancel" }) {
  const isSuccess = status === "success";

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Panel className="w-full max-w-2xl space-y-5 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
          Billing return
        </p>
        <h1 className="text-3xl font-semibold text-white">
          {isSuccess ? "Checkout flow completed" : "Checkout flow canceled"}
        </h1>
        <p className="text-sm leading-7 text-slate-300">
          {isSuccess
            ? "Se o endpoint Stripe real estiver conectado, este retorno deve refletir o estado do checkout."
            : "O plano não foi alterado. Você pode voltar à página de billing e reiniciar a seleção."}
        </p>
        <Link href="/billing">
          <a className="inline-flex rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400">
            Back to billing
          </a>
        </Link>
      </Panel>
    </div>
  );
}
