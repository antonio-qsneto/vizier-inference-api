import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Brain } from "lucide-react";
import { AnimatedConnector } from "@/components/site/AnimatedConnector";

const medicalImageSources = [
  {
    name: "CT Scan",
    type: "Tomografia Computadorizada",
    modality: "CT",
    imageSrc: "/site/brain_ct.png",
    imageAlt: "Prévia de exame CT cerebral",
  },
  {
    name: "MRI Scan",
    type: "Ressonância Magnética",
    modality: "MRI",
    imageSrc: "/site/lung_mri.png",
    imageAlt: "Prévia de exame MRI pulmonar",
  },
] as const;

const segmentationResults = [
  {
    source: "CT",
    region: "Cabeça",
    items: ["Câncer"],
    color: "from-blue-500 to-cyan-600",
    icon: "🧠",
  },
  {
    source: "CT",
    region: "Tórax",
    items: ["Lesões pulmonares", "COVID-19"],
    color: "from-cyan-500 to-blue-600",
    icon: "🫁",
  },
  {
    source: "CT",
    region: "Abdômen",
    items: [
      "Carcinoma adrenocortical",
      "Lesões/cistos renais L/R",
      "Tumores hepáticos",
      "Tumores pancreáticos",
      "Cólon",
      "Primários de câncer de cólon",
      "Pâncreas",
    ],
    color: "from-teal-500 to-cyan-600",
    icon: "🫀",
  },
  {
    source: "CT",
    region: "Corpo inteiro",
    items: ["Lesão em corpo inteiro", "Linfonodos"],
    color: "from-sky-500 to-blue-600",
    icon: "👤",
  },
  {
    source: "MRI",
    region: "Cabeça",
    items: [
      "Visualização do núcleo tumoral não realçado em RM T1 pós-contraste",
      "Segmentação de hiperintensidade FLAIR não realçante em RM T1 pós-contraste",
      "Segmentação de tecido realçante em RM T1 pós-contraste",
      "Segmentação de cavidade de ressecção em RM T1 pós-contraste",
    ],
    color: "from-cyan-500 to-blue-600",
    icon: "🧠",
  },
  {
    source: "MRI",
    region: "GU",
    items: ["Lesão prostática"],
    color: "from-blue-500 to-cyan-600",
    icon: "🔬",
  },
] as const;

interface FlowStep {
  id: string;
  phase: "image-input" | "ai-processing" | "segmentation";
  active: boolean;
}

function MedicalImageCard({
  source,
  index,
  isActive,
}: {
  source: (typeof medicalImageSources)[number];
  index: number;
  isActive: boolean;
}) {
  return (
    <motion.div
      className="group relative"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.1 }}
    >
      <motion.div
        className={`relative rounded-xl border border-slate-700/50 bg-slate-900/50 p-6 backdrop-blur-sm transition-all duration-300 ${
          isActive ? "border-cyan-400/50 bg-cyan-400/5" : ""
        }`}
        animate={{
          scale: isActive ? 1.02 : 1,
          boxShadow: isActive
            ? "0 0 20px rgba(34, 211, 238, 0.3)"
            : "0 2px 8px rgba(0, 0, 0, 0.2)",
        }}
        transition={{ duration: 0.3 }}
      >
        <div className="flex flex-col items-center space-y-4 text-center">
          <motion.div
            className="h-20 w-20 overflow-hidden rounded-2xl border border-white/20 bg-slate-800/60"
            animate={{
              rotate: isActive ? [0, 5, -5, 0] : 0,
            }}
            transition={{
              duration: 2,
              repeat: isActive ? Infinity : 0,
              ease: "easeInOut",
            }}
          >
            <img
              src={source.imageSrc}
              alt={source.imageAlt}
              className="h-full w-full rounded-2xl object-cover"
              loading="lazy"
            />
          </motion.div>

          <div>
            <h4 className="mb-1 text-lg text-white">{source.name}</h4>
            <p className="text-sm text-slate-400">{source.type}</p>
            <div className="mt-2 rounded-full bg-white/10 px-3 py-1">
              <span className="text-xs font-mono text-cyan-400">{source.modality}</span>
            </div>
          </div>
        </div>

        {isActive ? (
          <motion.div
            className="absolute right-3 top-3 flex items-center space-x-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <motion.div
              className="h-2 w-2 rounded-full bg-cyan-400"
              animate={{
                scale: [1, 1.5, 1],
                opacity: [0.8, 1, 0.8],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
            <span className="text-xs text-cyan-400">Processando</span>
          </motion.div>
        ) : null}
      </motion.div>
    </motion.div>
  );
}

function AIModelComponent({
  isActive,
  isProcessing,
}: {
  isActive: boolean;
  isProcessing: boolean;
}) {
  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.8 }}
    >
      <motion.div
        className={`relative rounded-3xl border-2 bg-gradient-to-br from-slate-900 via-blue-900/30 to-slate-900 p-8 ${
          isActive ? "border-blue-400/50" : "border-slate-700/50"
        }`}
        animate={{
          boxShadow: isActive
            ? [
                "0 0 30px rgba(59, 130, 246, 0.3)",
                "0 0 60px rgba(59, 130, 246, 0.5)",
                "0 0 30px rgba(59, 130, 246, 0.3)",
              ]
            : "0 0 20px rgba(0, 0, 0, 0.3)",
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      >
        <motion.div
          className="relative mx-auto mb-4 h-32 w-32"
          animate={{
            rotate: isProcessing ? 360 : 0,
          }}
          transition={{
            duration: 20,
            repeat: isProcessing ? Infinity : 0,
            ease: "linear",
          }}
        >
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 opacity-20 blur-xl" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Brain className="h-20 w-20 text-blue-400" strokeWidth={1.5} />
          </div>

          {isActive ? (
            <>
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-blue-400/50"
                animate={{
                  scale: [1, 1.3, 1],
                  opacity: [0.5, 0, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut",
                }}
              />
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-cyan-400/50"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.5, 0, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut",
                  delay: 0.5,
                }}
              />
            </>
          ) : null}
        </motion.div>

        <div className="text-center">
          <h3 className="mb-1 text-xl text-white">Vizier Model IA</h3>

          {isProcessing ? (
            <motion.div
              className="flex items-center justify-center space-x-2 text-xs text-cyan-400"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              >
                <Activity className="h-4 w-4" />
              </motion.div>
              <span>Analisando Imagens Médicas...</span>
            </motion.div>
          ) : null}

          {!isProcessing && isActive ? (
            <motion.div
              className="text-xs text-green-400"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              ✓ Segmentação Completa
            </motion.div>
          ) : null}
        </div>

        {isProcessing ? (
          <div className="mt-4 space-y-2">
            {[...Array(3)].map((_, i) => (
              <motion.div
                key={i}
                className="h-1 overflow-hidden rounded-full bg-slate-700/50"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.1 }}
              >
                <motion.div
                  className="h-full bg-gradient-to-r from-blue-500 to-cyan-500"
                  initial={{ x: "-100%" }}
                  animate={{ x: "100%" }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: i * 0.2,
                  }}
                />
              </motion.div>
            ))}
          </div>
        ) : null}
      </motion.div>
    </motion.div>
  );
}

function SegmentationResultCard({
  result,
  index,
  isDetected,
  detectionDelay,
}: {
  result: (typeof segmentationResults)[number];
  index: number;
  isDetected: boolean;
  detectionDelay: number;
}) {
  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, delay: index * 0.05 }}
    >
      <motion.div
        className={`relative rounded-lg border border-slate-700/50 bg-slate-900/50 p-3 backdrop-blur-sm transition-all duration-500 ${
          isDetected ? "border-green-400/50 bg-green-400/5" : ""
        }`}
        animate={{
          scale: isDetected ? 1.01 : 1,
          boxShadow: isDetected
            ? "0 0 15px rgba(34, 197, 94, 0.2)"
            : "0 2px 4px rgba(0, 0, 0, 0.1)",
        }}
        transition={{ duration: 0.5, delay: detectionDelay }}
      >
        <div className="flex items-start space-x-3">
          <motion.div
            className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${result.color}`}
            animate={{
              rotate: isDetected ? [0, 10, -10, 0] : 0,
            }}
            transition={{ duration: 0.8, delay: detectionDelay }}
          >
            <span className="text-lg">{result.icon}</span>
          </motion.div>

          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-mono ${
                    result.source === "CT"
                      ? "bg-blue-400/20 text-blue-400"
                      : "bg-cyan-400/20 text-cyan-400"
                  }`}
                >
                  {result.source}
                </span>
                <h4 className="text-sm font-medium text-white">{result.region}</h4>
              </div>

              {isDetected ? (
                <motion.div
                  className="h-2 w-2 rounded-full bg-green-400"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: detectionDelay + 0.2 }}
                />
              ) : null}
            </div>

            <div className="space-y-1">
              {result.items.map((item, itemIndex) => (
                <motion.div
                  key={itemIndex}
                  className="flex items-start space-x-2"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: isDetected ? 1 : 0.6, x: 0 }}
                  transition={{ delay: detectionDelay + 0.1 * itemIndex }}
                >
                  <div className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-slate-400" />
                  <p className="text-xs leading-relaxed text-slate-300">{item}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function StatusIndicator({
  phase,
  isActive,
  isComplete,
}: {
  phase: string;
  isActive: boolean;
  isComplete: boolean;
}) {
  return (
    <motion.div
      className="flex items-center space-x-2 text-sm"
      animate={{
        opacity: isActive || isComplete ? 1 : 0.5,
      }}
    >
      <motion.div
        className={`h-3 w-3 rounded-full border-2 ${
          isComplete
            ? "border-green-400 bg-green-400"
            : isActive
              ? "border-blue-400 bg-blue-400"
              : "border-slate-500"
        }`}
        animate={{
          scale: isActive && !isComplete ? [1, 1.2, 1] : 1,
        }}
        transition={{
          duration: 1.5,
          repeat: isActive && !isComplete ? Infinity : 0,
        }}
      />
      <span
        className={`${
          isComplete
            ? "text-green-400"
            : isActive
              ? "text-blue-400"
              : "text-slate-400"
        }`}
      >
        {phase}
      </span>
    </motion.div>
  );
}

export default function DataFlowVisualization() {
  const [flowSteps, setFlowSteps] = useState<FlowStep[]>([
    { id: "image-input", phase: "image-input", active: false },
    { id: "ai-processing", phase: "ai-processing", active: false },
    { id: "segmentation", phase: "segmentation", active: false },
  ]);

  const [activeImages, setActiveImages] = useState<number[]>([]);
  const [modelActive, setModelActive] = useState(false);
  const [modelProcessing, setModelProcessing] = useState(false);
  const [detectedResults, setDetectedResults] = useState<number[]>([]);

  const startAnimation = () => {
    setActiveImages([]);
    setModelActive(false);
    setModelProcessing(false);
    setDetectedResults([]);
    setFlowSteps((prev) => prev.map((step) => ({ ...step, active: false })));

    setTimeout(() => {
      setFlowSteps((prev) =>
        prev.map((step) =>
          step.phase === "image-input" ? { ...step, active: true } : step,
        ),
      );

      medicalImageSources.forEach((_, index) => {
        setTimeout(() => {
          setActiveImages((prev) => [...prev, index]);
        }, index * 500);
      });
    }, 500);

    setTimeout(() => {
      setFlowSteps((prev) =>
        prev.map((step) => ({
          ...step,
          active: step.phase === "ai-processing",
        })),
      );
      setModelActive(true);
      setModelProcessing(true);
    }, 2500);

    setTimeout(() => {
      setFlowSteps((prev) =>
        prev.map((step) => ({
          ...step,
          active: step.phase === "segmentation",
        })),
      );
      setModelProcessing(false);

      segmentationResults.forEach((_, index) => {
        setTimeout(() => {
          setDetectedResults((prev) => [...prev, index]);
        }, index * 250);
      });
    }, 5500);

    setTimeout(() => {
      setFlowSteps((prev) => prev.map((step) => ({ ...step, active: false })));
    }, 9000);
  };

  useEffect(() => {
    startAnimation();
    const interval = setInterval(startAnimation, 13000);
    return () => clearInterval(interval);
  }, []);

  const currentPhase = flowSteps.find((step) => step.active)?.phase || "idle";

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="relative z-10 mx-auto mb-6 max-w-7xl px-6 pt-8">
        <div className="mb-6 text-center">
          <h1 className="mb-2 text-4xl text-white">IA de Análise de Imagens Médicas</h1>
          <p className="text-lg text-slate-400">
            Detecção e Segmentação Automatizada
          </p>
        </div>

        <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4 backdrop-blur-sm">
          <div className="flex justify-center space-x-8">
            <StatusIndicator
              phase="Entrada de Imagens"
              isActive={currentPhase === "image-input"}
              isComplete={["ai-processing", "segmentation"].includes(currentPhase)}
            />
            <StatusIndicator
              phase="Processamento IA"
              isActive={currentPhase === "ai-processing"}
              isComplete={currentPhase === "segmentation"}
            />
            <StatusIndicator
              phase="Resultados de Segmentação"
              isActive={currentPhase === "segmentation"}
              isComplete={false}
            />
          </div>
        </div>
      </div>

      <div className="relative mx-auto max-w-7xl px-6 pb-12">
        <div className="relative flex items-center justify-between gap-8">
          <div className="relative z-20 w-72">
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8 }}
            >
              <div className="mb-4 text-center">
                <h3 className="mb-1 text-lg text-white">Entrada de Imagens Médicas</h3>
                <p className="text-xs text-slate-400">
                  Exames diagnósticos de alta resolução
                </p>
              </div>

              {medicalImageSources.map((source, index) => (
                <MedicalImageCard
                  key={source.name}
                  source={source}
                  index={index}
                  isActive={activeImages.includes(index)}
                />
              ))}
            </motion.div>
          </div>

          <div className="relative z-20 flex-shrink-0">
            <AIModelComponent isActive={modelActive} isProcessing={modelProcessing} />
          </div>

          <div className="relative z-20 w-96">
            <motion.div
              className="max-h-[600px] overflow-y-auto rounded-xl border border-slate-700/50 bg-slate-900/30 p-4 backdrop-blur-sm"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              <div className="sticky top-0 z-10 -mt-1 mb-4 bg-slate-900/80 pb-3 pt-1 text-center backdrop-blur-sm">
                <h3 className="mb-1 text-lg text-white">Resultados de Segmentação</h3>
                <p className="text-xs text-slate-400">
                  Anomalias detectadas e classificações
                </p>
              </div>

              <div className="space-y-3">
                {segmentationResults.map((result, index) => (
                  <SegmentationResultCard
                    key={`${result.source}-${result.region}`}
                    result={result}
                    index={index}
                    isDetected={detectedResults.includes(index)}
                    detectionDelay={detectedResults.includes(index) ? 0.3 : 0}
                  />
                ))}
              </div>
            </motion.div>
          </div>

          <div className="pointer-events-none absolute inset-0 z-10">
            <AnimatedConnector
              startX={288}
              startY={300}
              endX={450}
              endY={300}
              isActive={currentPhase === "image-input" || currentPhase === "ai-processing"}
              delay={0.8}
            />

            <AnimatedConnector
              startX={650}
              startY={300}
              endX={812}
              endY={300}
              isActive={currentPhase === "ai-processing" || currentPhase === "segmentation"}
              delay={3.5}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
