import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AnimatedConnector } from './components/AnimatedConnector';
import { Scan, Brain, Activity } from 'lucide-react';

const medicalImageSources = [
  { 
    name: 'CT Scan', 
    type: 'Tomografia Computadorizada',
    modality: 'CT',
    icon: Scan,
    color: 'from-blue-500 to-cyan-500'
  },
  { 
    name: 'MRI Scan', 
    type: 'Ressonância Magnética',
    modality: 'MRI',
    icon: Activity,
    color: 'from-cyan-500 to-blue-500'
  }
];

const segmentationResults = [
  // CT Results
  {
    source: 'CT',
    region: 'Cabeça',
    items: ['Câncer'],
    color: 'from-blue-500 to-cyan-600',
    icon: '🧠'
  },
  {
    source: 'CT',
    region: 'Tórax',
    items: ['Lesões pulmonares', 'COVID-19'],
    color: 'from-cyan-500 to-blue-600',
    icon: '🫁'
  },
  {
    source: 'CT',
    region: 'Abdômen',
    items: [
      'Carcinoma adrenocortical',
      'Lesões/cistos renais L/R',
      'Tumores hepáticos',
      'Tumores pancreáticos',
      'Cólon',
      'Primários de câncer de cólon',
      'Pâncreas'
    ],
    color: 'from-teal-500 to-cyan-600',
    icon: '🫀'
  },
  {
    source: 'CT',
    region: 'Corpo inteiro',
    items: ['Lesão em corpo inteiro', 'Linfonodos'],
    color: 'from-sky-500 to-blue-600',
    icon: '👤'
  },
  // MRI Results
  {
    source: 'MRI',
    region: 'Cabeça',
    items: [
      'Visualização do núcleo tumoral não realçado em RM T1 pós-contraste',
      'Segmentação de hiperintensidade FLAIR não realçante em RM T1 pós-contraste',
      'Segmentação de tecido realçante em RM T1 pós-contraste',
      'Segmentação de cavidade de ressecção em RM T1 pós-contraste'
    ],
    color: 'from-cyan-500 to-blue-600',
    icon: '🧠'
  },
  {
    source: 'MRI',
    region: 'GU',
    items: ['Lesão prostática'],
    color: 'from-blue-500 to-cyan-600',
    icon: '🔬'
  }
];

interface FlowStep {
  id: string;
  phase: 'image-input' | 'ai-processing' | 'segmentation';
  active: boolean;
}

const MedicalImageCard: React.FC<{
  source: typeof medicalImageSources[0];
  index: number;
  isActive: boolean;
}> = ({ source, index, isActive }) => {
  const IconComponent = source.icon;
  
  return (
    <motion.div
      className="group relative"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.1 }}
    >
      <motion.div
        className={`
          relative bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 
          rounded-xl p-6 transition-all duration-300
          ${isActive ? 'border-cyan-400/50 bg-cyan-400/5' : ''}
        `}
        animate={{
          scale: isActive ? 1.02 : 1,
          boxShadow: isActive 
            ? '0 0 20px rgba(34, 211, 238, 0.3)' 
            : '0 2px 8px rgba(0, 0, 0, 0.2)',
        }}
        transition={{ duration: 0.3 }}
      >
        <div className="flex flex-col items-center text-center space-y-4">
          <motion.div
            className={`
              w-20 h-20 rounded-2xl flex items-center justify-center
              bg-gradient-to-br ${source.color}
            `}
            animate={{
              rotate: isActive ? [0, 5, -5, 0] : 0,
            }}
            transition={{
              duration: 2,
              repeat: isActive ? Infinity : 0,
              ease: "easeInOut"
            }}
          >
            <IconComponent className="w-10 h-10 text-white" strokeWidth={1.5} />
          </motion.div>
          
          <div>
            <h4 className="text-white text-lg mb-1">{source.name}</h4>
            <p className="text-slate-400 text-sm">{source.type}</p>
            <div className="mt-2 px-3 py-1 bg-white/10 rounded-full">
              <span className="text-cyan-400 text-xs font-mono">{source.modality}</span>
            </div>
          </div>
        </div>
        
        {isActive && (
          <motion.div
            className="absolute top-3 right-3 flex items-center space-x-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <motion.div
              className="w-2 h-2 bg-cyan-400 rounded-full"
              animate={{
                scale: [1, 1.5, 1],
                opacity: [0.8, 1, 0.8],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: "easeInOut"
              }}
            />
            <span className="text-cyan-400 text-xs">Processando</span>
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
};

const AIModelComponent: React.FC<{
  isActive: boolean;
  isProcessing: boolean;
}> = ({ isActive, isProcessing }) => {
  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.8 }}
    >
      <motion.div
        className={`
          relative bg-gradient-to-br from-slate-900 via-blue-900/30 to-slate-900
          border-2 rounded-3xl p-8
          ${isActive ? 'border-blue-400/50' : 'border-slate-700/50'}
        `}
        animate={{
          boxShadow: isActive 
            ? ['0 0 30px rgba(59, 130, 246, 0.3)', '0 0 60px rgba(59, 130, 246, 0.5)', '0 0 30px rgba(59, 130, 246, 0.3)']
            : '0 0 20px rgba(0, 0, 0, 0.3)',
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut"
        }}
      >
        {/* Brain Icon */}
        <motion.div
          className="w-32 h-32 mx-auto mb-4 relative"
          animate={{
            rotate: isProcessing ? 360 : 0,
          }}
          transition={{
            duration: 20,
            repeat: isProcessing ? Infinity : 0,
            ease: "linear"
          }}
        >
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-full opacity-20 blur-xl" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Brain className="w-20 h-20 text-blue-400" strokeWidth={1.5} />
          </div>
          
          {/* Pulsing rings */}
          {isActive && (
            <>
              <motion.div
                className="absolute inset-0 border-2 border-blue-400/50 rounded-full"
                animate={{
                  scale: [1, 1.3, 1],
                  opacity: [0.5, 0, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut"
                }}
              />
              <motion.div
                className="absolute inset-0 border-2 border-cyan-400/50 rounded-full"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.5, 0, 0.5],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeOut",
                  delay: 0.5
                }}
              />
            </>
          )}
        </motion.div>

        {/* Model Name */}
        <div className="text-center">
          <h3 className="text-white text-xl mb-1">Vizier Model IA</h3>
          <p className="text-blue-400 text-sm mb-3">Segmentação Deep Learning</p>
          
          {isProcessing && (
            <motion.div
              className="flex items-center justify-center space-x-2 text-cyan-400 text-xs"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              >
                <Activity className="w-4 h-4" />
              </motion.div>
              <span>Analisando Imagens Médicas...</span>
            </motion.div>
          )}
          
          {!isProcessing && isActive && (
            <motion.div
              className="text-green-400 text-xs"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              ✓ Segmentação Completa
            </motion.div>
          )}
        </div>

        {/* Processing indicators */}
        {isProcessing && (
          <div className="mt-4 space-y-2">
            {[...Array(3)].map((_, i) => (
              <motion.div
                key={i}
                className="h-1 bg-slate-700/50 rounded-full overflow-hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.1 }}
              >
                <motion.div
                  className="h-full bg-gradient-to-r from-blue-500 to-cyan-500"
                  initial={{ x: '-100%' }}
                  animate={{ x: '100%' }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: i * 0.2
                  }}
                />
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
};

const SegmentationResultCard: React.FC<{
  result: typeof segmentationResults[0];
  index: number;
  isDetected: boolean;
  detectionDelay: number;
}> = ({ result, index, isDetected, detectionDelay }) => {
  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, delay: index * 0.05 }}
    >
      <motion.div
        className={`
          relative bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 
          rounded-lg p-3 transition-all duration-500
          ${isDetected ? 'border-green-400/50 bg-green-400/5' : ''}
        `}
        animate={{
          scale: isDetected ? 1.01 : 1,
          boxShadow: isDetected 
            ? '0 0 15px rgba(34, 197, 94, 0.2)' 
            : '0 2px 4px rgba(0, 0, 0, 0.1)',
        }}
        transition={{ duration: 0.5, delay: detectionDelay }}
      >
        <div className="flex items-start space-x-3">
          <motion.div
            className={`
              flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center
              bg-gradient-to-br ${result.color}
            `}
            animate={{
              rotate: isDetected ? [0, 10, -10, 0] : 0,
            }}
            transition={{ duration: 0.8, delay: detectionDelay }}
          >
            <span className="text-lg">{result.icon}</span>
          </motion.div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <span className={`
                  px-2 py-0.5 rounded text-xs font-mono
                  ${result.source === 'CT' ? 'bg-blue-400/20 text-blue-400' : 'bg-cyan-400/20 text-cyan-400'}
                `}>
                  {result.source}
                </span>
                <h4 className="text-white text-sm font-medium">{result.region}</h4>
              </div>
              
              {isDetected && (
                <motion.div
                  className="w-2 h-2 bg-green-400 rounded-full"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: detectionDelay + 0.2 }}
                />
              )}
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
                  <div className="w-1 h-1 bg-slate-400 rounded-full mt-1.5 flex-shrink-0" />
                  <p className="text-slate-300 text-xs leading-relaxed">{item}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

const StatusIndicator: React.FC<{ 
  phase: string; 
  isActive: boolean; 
  isComplete: boolean; 
}> = ({ phase, isActive, isComplete }) => {
  return (
    <motion.div
      className="flex items-center space-x-2 text-sm"
      animate={{
        opacity: isActive || isComplete ? 1 : 0.5,
      }}
    >
      <motion.div
        className={`
          w-3 h-3 rounded-full border-2
          ${isComplete ? 'bg-green-400 border-green-400' : 
            isActive ? 'bg-blue-400 border-blue-400' : 'border-slate-500'}
        `}
        animate={{
          scale: isActive && !isComplete ? [1, 1.2, 1] : 1,
        }}
        transition={{
          duration: 1.5,
          repeat: isActive && !isComplete ? Infinity : 0,
        }}
      />
      <span className={`
        ${isComplete ? 'text-green-400' : 
          isActive ? 'text-blue-400' : 'text-slate-400'}
      `}>
        {phase}
      </span>
    </motion.div>
  );
};

export default function App() {
  const [flowSteps, setFlowSteps] = useState<FlowStep[]>([
    { id: 'image-input', phase: 'image-input', active: false },
    { id: 'ai-processing', phase: 'ai-processing', active: false },
    { id: 'segmentation', phase: 'segmentation', active: false }
  ]);
  
  const [activeImages, setActiveImages] = useState<number[]>([]);
  const [modelActive, setModelActive] = useState(false);
  const [modelProcessing, setModelProcessing] = useState(false);
  const [detectedResults, setDetectedResults] = useState<number[]>([]);

  const startAnimation = () => {
    // Reset states
    setActiveImages([]);
    setModelActive(false);
    setModelProcessing(false);
    setDetectedResults([]);
    setFlowSteps(prev => prev.map(step => ({ ...step, active: false })));

    // Phase 1: Image Input (0-2s)
    setTimeout(() => {
      setFlowSteps(prev => prev.map(step => 
        step.phase === 'image-input' ? { ...step, active: true } : step
      ));
      
      // Activate medical images progressively
      medicalImageSources.forEach((_, index) => {
        setTimeout(() => {
          setActiveImages(prev => [...prev, index]);
        }, index * 500);
      });
    }, 500);

    // Phase 2: AI Processing (2-5s)
    setTimeout(() => {
      setFlowSteps(prev => prev.map(step => ({
        ...step,
        active: step.phase === 'ai-processing'
      })));
      setModelActive(true);
      setModelProcessing(true);
    }, 2500);

    // Phase 3: Segmentation Results (5-9s)
    setTimeout(() => {
      setFlowSteps(prev => prev.map(step => ({
        ...step,
        active: step.phase === 'segmentation'
      })));
      setModelProcessing(false);
      
      // Show segmentation results progressively
      segmentationResults.forEach((_, index) => {
        setTimeout(() => {
          setDetectedResults(prev => [...prev, index]);
        }, index * 250);
      });
    }, 5500);

    // Complete animation (9s)
    setTimeout(() => {
      setFlowSteps(prev => prev.map(step => ({ ...step, active: false })));
    }, 9000);
  };

  useEffect(() => {
    startAnimation();
    const interval = setInterval(startAnimation, 13000);
    return () => clearInterval(interval);
  }, []);

  const currentPhase = flowSteps.find(step => step.active)?.phase || 'idle';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <div className="relative z-10 max-w-7xl mx-auto px-6 pt-8 mb-6">
        <div className="text-center mb-6">
          <h1 className="text-4xl text-white mb-2">IA de Análise de Imagens Médicas</h1>
          <p className="text-slate-400 text-lg">Detecção e Segmentação Automatizada de Anomalias</p>
        </div>

        {/* Status Bar */}
        <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-4">
          <div className="flex justify-center space-x-8">
            <StatusIndicator 
              phase="Entrada de Imagens" 
              isActive={currentPhase === 'image-input'} 
              isComplete={['ai-processing', 'segmentation'].includes(currentPhase)}
            />
            <StatusIndicator 
              phase="Processamento IA" 
              isActive={currentPhase === 'ai-processing'} 
              isComplete={currentPhase === 'segmentation'}
            />
            <StatusIndicator 
              phase="Resultados de Segmentação" 
              isActive={currentPhase === 'segmentation'} 
              isComplete={false}
            />
          </div>
        </div>
      </div>

      {/* Main Flow */}
      <div className="relative max-w-7xl mx-auto px-6 pb-12">
        <div className="relative flex items-center justify-between gap-8">
          
          {/* Left Panel - Medical Image Sources */}
          <div className="w-72 relative z-20">
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8 }}
            >
              <div className="text-center mb-4">
                <h3 className="text-white text-lg mb-1">Entrada de Imagens Médicas</h3>
                <p className="text-slate-400 text-xs">Exames diagnósticos de alta resolução</p>
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

          {/* Center - AI Model */}
          <div className="flex-shrink-0 relative z-20">
            <AIModelComponent 
              isActive={modelActive} 
              isProcessing={modelProcessing} 
            />
          </div>

          {/* Right Panel - Segmentation Results */}
          <div className="w-96 relative z-20">
            <motion.div
              className="bg-slate-900/30 backdrop-blur-sm border border-slate-700/50 rounded-xl p-4 max-h-[600px] overflow-y-auto"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              <div className="text-center mb-4 sticky top-0 bg-slate-900/80 backdrop-blur-sm pb-3 -mt-1 pt-1 z-10">
                <h3 className="text-white text-lg mb-1">Resultados de Segmentação</h3>
                <p className="text-slate-400 text-xs">Anomalias detectadas e classificações</p>
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

          {/* Animated Connectors */}
          <div className="absolute inset-0 z-10 pointer-events-none">
            <AnimatedConnector
              startX={288}
              startY={300}
              endX={450}
              endY={300}
              isActive={currentPhase === 'image-input' || currentPhase === 'ai-processing'}
              delay={0.8}
            />
            
            <AnimatedConnector
              startX={650}
              startY={300}
              endX={812}
              endY={300}
              isActive={currentPhase === 'ai-processing' || currentPhase === 'segmentation'}
              delay={3.5}
            />
          </div>
        </div>
      </div>
    </div>
  );
}