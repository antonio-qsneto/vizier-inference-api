import { Link } from "wouter";
import { Panel } from "@/components/primitives";

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.14),transparent_28%),linear-gradient(180deg,#04070d,#060b14_34%,#08111a)] px-4 py-10 text-white md:px-8">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <img
          src="/site/vizier_white.svg"
          alt="Vizier"
          className="h-10 w-auto"
          loading="eager"
        />

        <Panel className="space-y-5">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-200">
            Termos de uso
          </p>
          <h1 className="text-3xl font-semibold text-white md:text-4xl">
            Uso assistivo da plataforma
          </h1>
          <p className="text-sm leading-7 text-slate-200 md:text-base">
            A Vizier Med é um software de apoio para análise de imagens médicas
            (incluindo identificação assistiva de lesões, tumores e outras alterações).
            O sistema <strong>não realiza diagnóstico médico</strong>.
          </p>

          <div className="space-y-2 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm leading-7 text-slate-300">
            <p>
              1. O sistema é exclusivamente assistivo e não substitui médico,
              radiologista, laudo, avaliação clínica, histórico do paciente, segunda
              opinião ou protocolos institucionais.
            </p>
            <p>
              2. As respostas podem conter erros, incluindo falso-positivo,
              falso-negativo e segmentações imperfeitas.
            </p>
            <p>
              3. A decisão clínica, diagnóstica e terapêutica deve ser tomada
              apenas por profissional de saúde habilitado.
            </p>
            <p>
              4. É proibido usar a plataforma como única base para diagnóstico,
              conduta médica ou definição de tratamento.
            </p>
            <p>
              5. Ao utilizar a plataforma, você concorda que o uso é de suporte e
              que a responsabilidade final pela decisão clínica é sempre humana.
            </p>
          </div>

          <div className="rounded-2xl border border-amber-300/30 bg-amber-500/10 p-4 text-sm leading-7 text-amber-50">
            <p className="font-semibold uppercase tracking-[0.14em]">
              Isenção de responsabilidade
            </p>
            <p className="mt-2">
              O provedor da plataforma não se responsabiliza por decisões
              equivocadas, diagnósticos incorretos, condutas inadequadas ou danos
              decorrentes do uso das saídas do sistema como decisão final.
            </p>
          </div>

          <div className="flex flex-wrap gap-3 pt-1">
            <Link href="/">
              <a className="rounded-full border border-white/15 bg-white/6 px-5 py-2.5 text-sm font-semibold text-slate-100 transition hover:bg-white/10">
                Voltar ao início
              </a>
            </Link>
          </div>
        </Panel>
      </div>
    </main>
  );
}
