import React from 'react';
import { motion } from 'motion/react';

interface AnimatedConnectorProps {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  isActive: boolean;
  delay?: number;
}

export const AnimatedConnector: React.FC<AnimatedConnectorProps> = ({
  startX,
  startY,
  endX,
  endY,
  isActive,
  delay = 0
}) => {
  return (
    <div className="absolute inset-0 pointer-events-none">
      {/* Connection Line */}
      <svg
        className="absolute inset-0 w-full h-full"
        style={{ overflow: 'visible' }}
      >
        <defs>
          <linearGradient id="connectionGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgb(71, 85, 105)" stopOpacity="0.6" />
            <stop offset="50%" stopColor="rgb(99, 102, 241)" stopOpacity="1" />
            <stop offset="100%" stopColor="rgb(71, 85, 105)" stopOpacity="0.6" />
          </linearGradient>
          
          <linearGradient id="activeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgb(34, 211, 238)" stopOpacity="0.8" />
            <stop offset="50%" stopColor="rgb(34, 211, 238)" stopOpacity="1" />
            <stop offset="100%" stopColor="rgb(34, 211, 238)" stopOpacity="0.8" />
          </linearGradient>

          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge> 
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        {/* Main connection line - always visible */}
        <motion.line
          x1={startX}
          y1={startY}
          x2={endX}
          y2={endY}
          stroke="rgb(71, 85, 105)"
          strokeWidth="3"
          opacity="0.4"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, delay: 0.5, ease: "easeInOut" }}
        />
        
        {/* Active/animated line */}
        <motion.line
          x1={startX}
          y1={startY}
          x2={endX}
          y2={endY}
          stroke={isActive ? "url(#activeGradient)" : "url(#connectionGradient)"}
          strokeWidth={isActive ? "4" : "3"}
          filter={isActive ? "url(#glow)" : "none"}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, delay: delay, ease: "easeInOut" }}
          opacity={isActive ? 1 : 0.6}
        />
      </svg>

      {/* Enhanced Data Flow Particles */}
      {isActive && (
        <>
          {[...Array(5)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute w-3 h-3 bg-cyan-400 rounded-full shadow-lg"
              style={{
                boxShadow: '0 0 12px rgb(34, 211, 238), 0 0 24px rgb(34, 211, 238)',
              }}
              initial={{
                x: startX - 6,
                y: startY - 6,
                opacity: 0,
                scale: 0.3
              }}
              animate={{
                x: endX - 6,
                y: endY - 6,
                opacity: [0, 1, 1, 0],
                scale: [0.3, 1.5, 1, 0.3]
              }}
              transition={{
                duration: 2.5,
                delay: delay + (i * 0.4),
                repeat: Infinity,
                repeatDelay: 2,
                ease: "easeInOut"
              }}
            />
          ))}
          
          {/* Additional smaller particles for richer effect */}
          {[...Array(8)].map((_, i) => (
            <motion.div
              key={`small-${i}`}
              className="absolute w-1.5 h-1.5 bg-cyan-300 rounded-full"
              style={{
                boxShadow: '0 0 6px rgb(34, 211, 238)',
              }}
              initial={{
                x: startX - 3,
                y: startY - 3,
                opacity: 0,
                scale: 0.2
              }}
              animate={{
                x: endX - 3,
                y: endY - 3,
                opacity: [0, 0.8, 0.8, 0],
                scale: [0.2, 1, 1, 0.2]
              }}
              transition={{
                duration: 3,
                delay: delay + 0.2 + (i * 0.2),
                repeat: Infinity,
                repeatDelay: 1.5,
                ease: "easeInOut"
              }}
            />
          ))}
        </>
      )}
    </div>
  );
};

export const DataFlowPath: React.FC<{
  path: string;
  isActive: boolean;
  delay?: number;
}> = ({ path, isActive, delay = 0 }) => {
  return (
    <div className="absolute inset-0 pointer-events-none">
      <svg className="absolute inset-0 w-full h-full" style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="pathGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgb(71, 85, 105)" stopOpacity="0.3" />
            <stop offset="50%" stopColor="rgb(99, 102, 241)" stopOpacity="0.8" />
            <stop offset="100%" stopColor="rgb(71, 85, 105)" stopOpacity="0.3" />
          </linearGradient>
          
          <linearGradient id="activePathGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgb(34, 211, 238)" stopOpacity="0.6" />
            <stop offset="50%" stopColor="rgb(34, 211, 238)" stopOpacity="1" />
            <stop offset="100%" stopColor="rgb(34, 211, 238)" stopOpacity="0.6" />
          </linearGradient>

          <filter id="pathGlow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
            <feMerge> 
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        <motion.path
          d={path}
          fill="none"
          stroke={isActive ? "url(#activePathGradient)" : "url(#pathGradient)"}
          strokeWidth="2"
          filter={isActive ? "url(#pathGlow)" : "none"}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.5, delay: delay, ease: "easeInOut" }}
        />
        
        {/* Animated data points along path */}
        {isActive && (
          <motion.circle
            r="3"
            fill="rgb(34, 211, 238)"
            filter="url(#pathGlow)"
            initial={{ offsetDistance: "0%" }}
            animate={{ offsetDistance: "100%" }}
            transition={{
              duration: 2,
              delay: delay + 0.5,
              repeat: Infinity,
              repeatDelay: 1,
              ease: "easeInOut"
            }}
            style={{ offsetPath: `path('${path}')` }}
          />
        )}
      </svg>
    </div>
  );
};