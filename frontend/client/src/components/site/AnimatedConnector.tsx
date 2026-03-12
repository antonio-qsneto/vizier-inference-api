import { motion } from "framer-motion";

interface AnimatedConnectorProps {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  isActive: boolean;
  delay?: number;
}

export function AnimatedConnector({
  startX,
  startY,
  endX,
  endY,
  isActive,
  delay = 0,
}: AnimatedConnectorProps) {
  return (
    <div className="absolute inset-0 pointer-events-none">
      <svg className="absolute inset-0 h-full w-full" style={{ overflow: "visible" }}>
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
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

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

      {isActive ? (
        <>
          {[...Array(5)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute h-3 w-3 rounded-full bg-cyan-400 shadow-lg"
              style={{
                boxShadow: "0 0 12px rgb(34, 211, 238), 0 0 24px rgb(34, 211, 238)",
              }}
              initial={{
                x: startX - 6,
                y: startY - 6,
                opacity: 0,
                scale: 0.3,
              }}
              animate={{
                x: endX - 6,
                y: endY - 6,
                opacity: [0, 1, 1, 0],
                scale: [0.3, 1.5, 1, 0.3],
              }}
              transition={{
                duration: 2.5,
                delay: delay + i * 0.4,
                repeat: Infinity,
                repeatDelay: 2,
                ease: "easeInOut",
              }}
            />
          ))}

          {[...Array(8)].map((_, i) => (
            <motion.div
              key={`small-${i}`}
              className="absolute h-1.5 w-1.5 rounded-full bg-cyan-300"
              style={{
                boxShadow: "0 0 6px rgb(34, 211, 238)",
              }}
              initial={{
                x: startX - 3,
                y: startY - 3,
                opacity: 0,
                scale: 0.2,
              }}
              animate={{
                x: endX - 3,
                y: endY - 3,
                opacity: [0, 0.8, 0.8, 0],
                scale: [0.2, 1, 1, 0.2],
              }}
              transition={{
                duration: 3,
                delay: delay + 0.2 + i * 0.2,
                repeat: Infinity,
                repeatDelay: 1.5,
                ease: "easeInOut",
              }}
            />
          ))}
        </>
      ) : null}
    </div>
  );
}
