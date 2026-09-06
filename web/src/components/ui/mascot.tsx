"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

type MascotMood = "neutral" | "happy" | "thinking" | "sleepy" | "surprised";

const eyeY: Record<MascotMood, number> = {
  neutral: 42,
  happy: 43,
  thinking: 40,
  sleepy: 44,
  surprised: 38,
};

const mouthPaths: Record<MascotMood, string> = {
  neutral: "M38 54 Q48 58 58 54",
  happy: "M36 54 Q48 62 60 54",
  thinking: "M40 56 Q48 52 56 56",
  sleepy: "M38 56 Q48 54 58 56",
  surprised: "M44 54 Q48 60 52 54",
};

const palettes = {
  soft: { outer: "#F8EDD4", inner: "#FBF6EA" },
  /** Slightly deeper cream for the nav mark so it reads on light rails */
  mark: { outer: "#E2C78A", inner: "#EDD9A4" },
} as const;

const TALK_RY = [2.4, 5.4, 1.8, 4.6];

function useTalkingMouth(active: boolean) {
  const [frame, setFrame] = useState(1);
  useEffect(() => {
    if (!active) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      setFrame((current) => (current + 1) % TALK_RY.length);
    }, 115);
    return () => window.clearInterval(id);
  }, [active]);
  return TALK_RY[frame];
}

export function Mascot({
  mood = "neutral",
  size = 80,
  className,
  animate = true,
  talking = false,
  searching = false,
  palette = "soft",
}: {
  mood?: MascotMood;
  size?: number;
  className?: string;
  animate?: boolean;
  talking?: boolean;
  searching?: boolean;
  palette?: keyof typeof palettes;
}) {
  const face = talking ? "happy" : mood;
  const ey = eyeY[face];
  const fills = palettes[palette];
  const talkRy = useTalkingMouth(talking);

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      overflow="visible"
      aria-hidden="true"
      className={cn(
        animate &&
          (talking || searching
            ? "motion-safe:animate-breathe-talk"
            : "motion-safe:animate-breathe"),
        className,
      )}
    >
      <ellipse cx="48" cy="52" rx="36" ry="32" fill={fills.outer} />
      <ellipse cx="48" cy="48" rx="34" ry="30" fill={fills.inner} />
      <g
        className={searching ? "motion-safe:animate-glance" : undefined}
        style={
          searching
            ? { transformBox: "fill-box", transformOrigin: "center" }
            : undefined
        }
      >
        <circle
          cx="36"
          cy={ey}
          r="3.5"
          fill="#1B1B1E"
          className={searching ? undefined : "motion-safe:animate-blink"}
          style={{ transformOrigin: "36px 42px" }}
        />
        <circle
          cx="60"
          cy={ey}
          r="3.5"
          fill="#1B1B1E"
          className={searching ? undefined : "motion-safe:animate-blink"}
          style={{ transformOrigin: "60px 42px" }}
        />
      </g>
      {face === "thinking" && !talking && (
        <path d="M62 36 Q68 30 72 34" stroke="#E8B44A" strokeWidth="2" fill="none" strokeLinecap="round" />
      )}
      {face === "sleepy" && !talking && (
        <>
          <path d="M30 40 Q36 36 42 40" stroke="#1B1B1E" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          <path d="M54 40 Q60 36 66 40" stroke="#1B1B1E" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </>
      )}
      {talking ? (
        <ellipse cx="48" cy="58.5" rx="6" ry={talkRy} fill="#1B1B1E" />
      ) : face !== "sleepy" ? (
        <path
          d={mouthPaths[face]}
          stroke="#1B1B1E"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
        />
      ) : null}
      {face === "surprised" && !talking && (
        <ellipse cx="48" cy="58" rx="4" ry="5" fill="none" stroke="#1B1B1E" strokeWidth="1.6" />
      )}
    </svg>
  );
}

export function MeuxeMark({ size = 48 }: { size?: number }) {
  return <Mascot mood="happy" size={size} animate={false} palette="mark" />;
}
