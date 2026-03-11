import React from 'react';
import { motion } from 'motion/react';

interface AIBrainProps {
  isActive: boolean;
  isProcessing: boolean;
}

export const AIBrain: React.FC<AIBrainProps> = ({ isActive, isProcessing }) => {
  return (
    <div className="relative">
      {/* Main brain container - Clean and minimal */}
      <motion.div
        className="relative z-10 w-40 h-40 bg-gradient-to-br from-slate-900 to-black rounded-full border-2 flex flex-col items-center justify-center shadow-2xl"
        animate={{
          borderColor: isActive ? 'rgb(34, 211, 238)' : 'rgb(71, 85, 105)',
          boxShadow: isActive 
            ? '0 0 60px rgba(34, 211, 238, 0.4), inset 0 0 30px rgba(34, 211, 238, 0.1)' 
            : '0 0 30px rgba(0, 0, 0, 0.8)',
        }}
        transition={{ duration: 0.8 }}
      >
        {/* Minimal neural network - just a few key elements */}
        <div className="absolute inset-0 rounded-full overflow-hidden">
          <svg className="w-full h-full" viewBox="0 0 160 160">
            <defs>
              <filter id="cleanGlow">
                <feGaussianBlur stdDeviation="1.5" result="coloredBlur"/>
                <feMerge> 
                  <feMergeNode in="coloredBlur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>
            
            {/* Simple outer ring */}
            {[...Array(6)].map((_, i) => {
              const angle = (i * 60) * Math.PI / 180;
              const radius = 55;
              const x = 80 + Math.cos(angle) * radius;
              const y = 80 + Math.sin(angle) * radius;
              
              return (
                <motion.circle
                  key={`outer-${i}`}
                  cx={x}
                  cy={y}
                  r="2.5"
                  fill={isActive ? "rgb(34, 211, 238)" : "rgb(71, 85, 105)"}
                  filter="url(#cleanGlow)"
                  animate={{
                    scale: isProcessing ? [1, 1.4, 1] : 1,
                    opacity: isActive ? [0.7, 1, 0.7] : 0.4,
                  }}
                  transition={{
                    duration: 2,
                    delay: i * 0.2,
                    repeat: isProcessing ? Infinity : 0,
                    ease: "easeInOut"
                  }}
                />
              );
            })}
            
            {/* Center core */}
            <motion.circle
              cx={80}
              cy={80}
              r="6"
              fill={isActive ? "rgb(34, 211, 238)" : "rgb(71, 85, 105)"}
              filter="url(#cleanGlow)"
              animate={{
                scale: isProcessing ? [1, 1.2, 1] : 1,
                opacity: [0.8, 1, 0.8],
              }}
              transition={{
                duration: 2.5,
                repeat: Infinity,
                ease: "easeInOut"
              }}
            />
            
            {/* Minimal connecting lines */}
            {[...Array(6)].map((_, i) => {
              const angle = (i * 60) * Math.PI / 180;
              const outerRadius = 55;
              const innerRadius = 15;
              const x1 = 80 + Math.cos(angle) * innerRadius;
              const y1 = 80 + Math.sin(angle) * innerRadius;
              const x2 = 80 + Math.cos(angle) * outerRadius;
              const y2 = 80 + Math.sin(angle) * outerRadius;
              
              return (
                <motion.line
                  key={`connection-${i}`}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={isActive ? "rgb(34, 211, 238)" : "rgb(71, 85, 105)"}
                  strokeWidth="1.5"
                  opacity={isActive ? 0.6 : 0.3}
                  filter="url(#cleanGlow)"
                  initial={{ pathLength: 0 }}
                  animate={{ 
                    pathLength: isProcessing ? [0, 1, 0] : 1,
                  }}
                  transition={{
                    duration: 2.5,
                    delay: i * 0.15,
                    repeat: isProcessing ? Infinity : 0,
                    ease: "easeInOut"
                  }}
                />
              );
            })}
          </svg>
        </div>

        {/* Clean central content */}
        <motion.div
          className="relative z-20 flex flex-col items-center"
          animate={{
            scale: isActive ? 1.05 : 1,
          }}
          transition={{ duration: 0.5 }}
        >
          {/* Simple brain icon */}
          <motion.svg
            width="36"
            height="36"
            viewBox="0 0 24 24"
            className={`mb-3 transition-colors duration-500 ${
              isActive ? 'text-cyan-400' : 'text-slate-400'
            }`}
            animate={{
              filter: isActive ? 'drop-shadow(0 0 10px rgba(34, 211, 238, 0.8))' : 'none',
            }}
          >
            <path
              fill="currentColor"
              d="M21.33 12.91c.09-.69.07-1.4-.07-2.08c-.11-.59-.29-1.16-.54-1.69c-.2-.44-.46-.85-.77-1.2c-.32-.35-.69-.65-1.1-.88c-.4-.22-.84-.4-1.3-.52c-.58-.15-1.18-.18-1.77-.09c-.25-.58-.6-1.11-1.03-1.56c-.44-.47-.97-.85-1.57-1.13c-.58-.26-1.22-.41-1.85-.44c-.66-.03-1.32.07-1.94.28c-.65.22-1.24.58-1.73 1.06c-.48.47-.87 1.04-1.13 1.67c-.24.57-.37 1.18-.4 1.79c-.08-.01-.17-.02-.25-.02c-.72.03-1.42.22-2.05.55c-.64.34-1.2.81-1.64 1.39c-.45.58-.77 1.26-.94 1.98c-.18.73-.21 1.49-.1 2.23c.12.85.42 1.66.87 2.38c.45.71 1.06 1.31 1.78 1.75c.71.44 1.52.71 2.35.8c.85.09 1.71-.01 2.51-.28c.28.36.62.67 1.01.91c.4.25.85.43 1.31.54c.45.1.92.12 1.38.06c.46-.06.9-.2 1.31-.41c.42-.22.8-.51 1.13-.85c.32-.34.58-.73.77-1.15c.21-.45.35-.92.41-1.4c.07-.56.04-1.13-.08-1.68c.61-.34 1.15-.81 1.58-1.37c.44-.57.76-1.23.94-1.93c.18-.69.21-1.41.1-2.11zm-2.87 1.54c-.2.46-.5.87-.87 1.19c-.36.32-.8.55-1.26.67c-.46.12-.94.13-1.41.03c-.38-.08-.75-.23-1.07-.44c-.32-.21-.59-.48-.8-.8l-.52-.78l-.77.52c-.32.21-.68.36-1.06.43c-.37.07-.76.06-1.13-.04c-.37-.1-.72-.26-1.03-.48c-.31-.22-.58-.5-.8-.82c-.21-.31-.37-.67-.46-1.04c-.09-.37-.11-.76-.06-1.14c.06-.38.18-.75.36-1.08c.18-.33.42-.63.71-.87c.29-.24.62-.42.98-.53c.35-.11.73-.15 1.1-.12c.38.03.75.12 1.09.27l.87.4l.4-.87c.15-.34.37-.65.64-.91c.27-.26.59-.47.94-.61c.34-.14.71-.21 1.08-.21c.37 0 .74.07 1.08.21c.35.14.67.35.94.61c.27.26.49.57.64.91c.16.34.25.71.27 1.08c.02.37-.03.74-.14 1.09c-.11.35-.28.68-.51.97c-.22.28-.5.52-.82.7c-.31.18-.66.29-1.02.32c-.36.03-.72-.01-1.06-.12l-.87-.4l-.4.87c-.18.4-.44.75-.77 1.03z"
            />
          </motion.svg>
          
          {/* Clean text styling */}
          <motion.div
            className="text-center"
            animate={{
              textShadow: isActive ? '0 0 15px rgba(34, 211, 238, 0.8)' : 'none',
            }}
          >
            <h3 className={`text-base mb-1 transition-colors duration-500 ${
              isActive ? 'text-cyan-400' : 'text-slate-300'
            }`}>
              Torvalds
            </h3>
            <p className="text-slate-400 text-sm">ENTERPRISE GPT</p>
          </motion.div>
        </motion.div>

        {/* Minimal processing indicator */}
        {isProcessing && (
          <motion.div
            className="absolute bottom-4 left-1/2 transform -translate-x-1/2"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5 }}
          >
            <div className="flex space-x-1">
              {[...Array(3)].map((_, i) => (
                <motion.div
                  key={i}
                  className="w-2 h-2 bg-cyan-400 rounded-full"
                  animate={{
                    scale: [1, 1.6, 1],
                    opacity: [0.5, 1, 0.5],
                  }}
                  transition={{
                    duration: 1.2,
                    delay: i * 0.2,
                    repeat: Infinity,
                    ease: "easeInOut"
                  }}
                />
              ))}
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* Subtle outer glow when active */}
      {isActive && (
        <motion.div
          className="absolute inset-0 w-44 h-44 -top-2 -left-2 rounded-full border border-cyan-400/20"
          animate={{
            scale: [1, 1.05, 1],
            opacity: [0.3, 0.6, 0.3],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
      )}
    </div>
  );
};