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

export function Mascot({
  mood = "neutral",
  size = 80,
  className,
  animate = true,
  palette = "soft",
}: {
  mood?: MascotMood;
  size?: number;
  className?: string;
  animate?: boolean;
  palette?: keyof typeof palettes;
}) {
  const ey = eyeY[mood];
  const fills = palettes[palette];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      aria-hidden="true"
      className={cn(
        animate && "motion-safe:animate-breathe",
        className,
      )}
    >
      <ellipse cx="48" cy="52" rx="36" ry="32" fill={fills.outer} />
      <ellipse cx="48" cy="48" rx="34" ry="30" fill={fills.inner} />
      <circle cx="36" cy={ey} r="3.5" fill="#1B1B1E" className="motion-safe:animate-blink" style={{ transformOrigin: "36px 42px" }} />
      <circle cx="60" cy={ey} r="3.5" fill="#1B1B1E" className="motion-safe:animate-blink" style={{ transformOrigin: "60px 42px" }} />
      {mood === "thinking" && (
        <path d="M62 36 Q68 30 72 34" stroke="#E8B44A" strokeWidth="2" fill="none" strokeLinecap="round" />
      )}
      {mood === "sleepy" && (
        <>
          <path d="M30 40 Q36 36 42 40" stroke="#1B1B1E" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          <path d="M54 40 Q60 36 66 40" stroke="#1B1B1E" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </>
      )}
      {mood !== "sleepy" && (
        <path
          d={mouthPaths[mood]}
          stroke="#1B1B1E"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
        />
      )}
      {mood === "surprised" && (
        <ellipse cx="48" cy="58" rx="4" ry="5" fill="none" stroke="#1B1B1E" strokeWidth="1.6" />
      )}
    </svg>
  );
}

export function MeuxeMark({ size = 48 }: { size?: number }) {
  return <Mascot mood="happy" size={size} animate={false} palette="mark" />;
}
