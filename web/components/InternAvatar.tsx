/**
 * The intern: an actual newt, drawn side-on in a thick ink outline, and it grows up as it is onboarded,
 * following the real newt life cycle: egg (orientation) -> larva with gills (shadowing) -> eft with legs
 * (supervised practice) -> adult with a crest and a graduation cap (graduated). Moods show as a small prop
 * floating above its back. At 28 px and below only the head (and cap) is drawn.
 *
 * Product rule: the mood comes from the intern's own situation (its stage, its queue), never from a
 * lesson the mentor just gave. Motion (bob, blink, tail, wave) is CSS in globals.css and is switched off
 * under prefers-reduced-motion.
 */

export const MOODS = [
  "neutral", "hello", "learning", "thinking", "drafting", "handing-back",
  "working", "graduated", "resting", "recertifying", "practising",
] as const;
export type Mood = (typeof MOODS)[number];

export const GROWTH = ["egg", "larva", "eft", "adult"] as const;
export type Growth = (typeof GROWTH)[number];

const LABEL: Record<Mood, string> = {
  neutral: "the intern",
  hello: "waving hello",
  learning: "taking notes",
  thinking: "thinking",
  drafting: "writing a draft",
  "handing-back": "handing a case back",
  working: "working on its own",
  graduated: "celebrating its graduation",
  resting: "all caught up",
  recertifying: "re-certifying",
  practising: "back to practice",
};

export type InternStage = "shadow" | "supervised" | "autonomous" | "demoted";

export const STAGE_MOOD: Readonly<Record<InternStage, Mood>> = {
  shadow: "learning",
  supervised: "drafting",
  autonomous: "working",
  demoted: "practising",
};

/** How grown-up the newt is at each task-type stage. Orientation (no task type yet) is the egg. */
export const STAGE_GROWTH: Readonly<Record<InternStage, Growth>> = {
  shadow: "larva",
  supervised: "eft",
  autonomous: "adult",
  demoted: "eft",
};

const INK = "var(--color-ink, #1b1714)";
const SKIN = "var(--color-brand-500, #ff7a2f)";
const SPOT = "var(--color-brand-700, #c2410c)";
const GOLD = "#f7b731";
const PAPER = "#fffdf9";
const LARVA = "#ffb084";
const GILL = "#e85d75";
const S = { stroke: INK, strokeWidth: 3, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

const BODY = "M20 84C20 70 40 66 62 68C70 50 98 46 104 66C110 84 92 94 74 94L34 96C26 96 20 92 20 84Z";
const TAIL = "M24 84C10 84 4 74 10 64";

function Tube({ d, color, width = 10 }: { d: string; color: string; width?: number }) {
  return (
    <g className="ia-tail">
      <path d={d} fill="none" stroke={INK} strokeWidth={width} strokeLinecap="round" />
      <path d={d} fill="none" stroke={color} strokeWidth={width - 6} strokeLinecap="round" />
    </g>
  );
}

/** Mood props float above the newt's back (x 18-62, y 28-62), clear of the head and cap. */
function Prop({ mood }: { mood: Mood }) {
  switch (mood) {
    case "learning":
    case "practising":
      return (
        <g>
          <path d="M24 44Q38 39 40 45Q42 39 56 44V58Q42 54 40 60Q38 54 24 58Z" fill={PAPER} {...S} strokeWidth={2.5} />
          <path d="M40 45V60M28 49H35M28 53H35M45 49H52" fill="none" {...S} strokeWidth={1.5} />
        </g>
      );
    case "thinking":
      return <text x="32" y="58" fontSize="26" fontWeight="700" fill={INK} fontFamily="var(--font-hand), cursive">?</text>;
    case "drafting":
      return (
        <g>
          <rect x="24" y="34" width="22" height="26" rx="2" fill={PAPER} {...S} strokeWidth={2.5} />
          <path d="M29 42H41M29 47H41M29 52H36" fill="none" {...S} strokeWidth={1.5} />
          <path d="M44 58L60 38" stroke={INK} strokeWidth={6} strokeLinecap="round" />
          <path d="M44 58L60 38" stroke={GOLD} strokeWidth={2.5} strokeLinecap="round" />
        </g>
      );
    case "handing-back":
      return (
        <g>
          <rect x="34" y="36" width="20" height="24" rx="2" fill={PAPER} {...S} strokeWidth={2.5} transform="rotate(-8 44 48)" />
          <path d="M30 40Q20 36 18 46M18 46L14 41M18 46L23 43" fill="none" {...S} strokeWidth={2.5} />
        </g>
      );
    case "working":
      return (
        <g>
          <circle cx="40" cy="46" r="10" fill="#16a34a" {...S} strokeWidth={2.5} />
          <path d="M35 46L39 50L45 42" fill="none" stroke="#fff" strokeWidth={2.8} strokeLinecap="round" strokeLinejoin="round" />
        </g>
      );
    case "graduated":
      return (
        <g>
          <rect x="22" y="40" width="6" height="6" fill={GOLD} transform="rotate(20 25 43)" />
          <rect x="48" y="30" width="5" height="5" fill={SKIN} transform="rotate(-15 50 32)" />
          <circle cx="36" cy="54" r="3" fill="#16a34a" />
          <circle cx="58" cy="50" r="2.5" fill={GOLD} />
          <rect x="12" y="56" width="4" height="4" fill="#16a34a" />
          <circle cx="40" cy="32" r="2.5" fill={GILL} />
        </g>
      );
    case "resting":
      return (
        <g fill={INK} fontFamily="var(--font-hand), cursive" fontWeight="700">
          <text x="30" y="60" fontSize="18">z</text>
          <text x="44" y="46" fontSize="13">z</text>
        </g>
      );
    case "recertifying":
      return (
        <g>
          <path d="M50 46A10 10 0 1 1 43 36.5" fill="none" {...S} strokeWidth={2.5} />
          <path d="M40 31L44 36.5L38 39" fill="none" {...S} strokeWidth={2.5} />
        </g>
      );
    default:
      return null;
  }
}

function Face({ mood, dy = 0 }: { mood: Mood; dy?: number }) {
  const happy = mood === "hello" || mood === "graduated" || mood === "working";
  const up = mood === "thinking" ? -3 : 0;
  return (
    <g transform={`translate(0 ${dy})`}>
      {mood === "resting" ? (
        <path d="M80 66Q84 69 88 66M94 66Q98 69 102 66" fill="none" {...S} strokeWidth={2.5} />
      ) : (
        <g className="ia-eyes">
          <circle cx="84" cy={66 + up} r="3.3" fill={INK} />
          <circle cx="98" cy={66 + up} r="3.3" fill={INK} />
        </g>
      )}
      {happy ? <path d="M86 75Q92 81 98 75" fill="none" {...S} strokeWidth={2.5} /> : <path d="M88 77L97 77" fill="none" {...S} strokeWidth={2.5} />}
    </g>
  );
}

function Cap({ graduated }: { graduated: boolean }) {
  const tx = graduated ? 30 : 90;
  return (
    <g transform="translate(30 26)">
      <path d="M44 24V33Q60 40 76 33V24" fill={INK} {...S} strokeWidth={2.5} />
      <path d="M60 9L94 21L60 33L26 21Z" fill={INK} {...S} strokeWidth={2.5} />
      <path d={`M60 21L${tx} 23L${tx} 35`} fill="none" stroke={GOLD} strokeWidth={2} strokeLinecap="round" />
      <rect x={tx - 2.5} y="34" width="5" height="8" rx="1.5" fill={GOLD} />
    </g>
  );
}

function Legs({ wave }: { wave: boolean }) {
  return (
    <g>
      <path d="M36 94L32 106M48 95L48 106M27 106H35M44 106H52M78 93L80 106M76 106H84" fill="none" {...S} />
      {wave ? (
        <path className="ia-wave" d="M92 90Q104 90 110 78" fill="none" {...S} />
      ) : (
        <path d="M90 92L94 105M90 105H98" fill="none" {...S} />
      )}
    </g>
  );
}

function Adult({ mood, crest }: { mood: Mood; crest: boolean }) {
  return (
    <g>
      <Tube d={TAIL} color={SKIN} />
      <Legs wave={mood === "hello"} />
      <path d={BODY} fill={SKIN} {...S} />
      {crest && <path d="M26 72Q32 64 38 70Q44 61 50 67Q56 59 62 66" fill="none" {...S} strokeWidth={2.5} />}
      <g fill={SPOT} opacity={0.55}>
        <circle cx="40" cy="83" r="3" />
        <circle cx="55" cy="81" r="2.4" />
        <circle cx="70" cy="85" r="2" />
      </g>
      <Face mood={mood} />
    </g>
  );
}

function Larva({ mood }: { mood: Mood }) {
  return (
    <g>
      <path d="M30 88C18 88 10 82 12 72" fill="none" stroke={INK} strokeWidth={8} strokeLinecap="round" />
      <path d="M30 88C18 88 10 82 12 72" fill="none" stroke={LARVA} strokeWidth={3} strokeLinecap="round" />
      <path d="M72 70Q66 60 70 54M75 69Q74 58 80 54M78 70Q82 60 88 58" fill="none" stroke={GILL} strokeWidth={3.5} strokeLinecap="round" />
      <path d="M28 88C28 80 48 78 64 80C72 68 96 68 98 82C100 94 84 98 70 96L40 97C33 97 28 94 28 88Z" fill={LARVA} {...S} />
      <Face mood={mood} dy={12} />
    </g>
  );
}

function Egg() {
  return (
    <g>
      <ellipse cx="62" cy="80" rx="26" ry="30" fill="#fff4d6" {...S} />
      <path d="M48 88C46 76 60 70 70 74C80 78 78 92 66 92C58 92 56 84 62 82" fill="none" stroke={SKIN} strokeWidth={6} strokeLinecap="round" opacity={0.9} />
      <circle cx="66" cy="76" r="2" fill={INK} />
      <circle cx="72" cy="78" r="2" fill={INK} />
    </g>
  );
}

export function InternAvatar({ mood = "neutral", growth = "adult", size = 48, className = "", title, decorative = false, animated = true }: {
  mood?: Mood;
  growth?: Growth;
  size?: number;
  className?: string;
  title?: string;
  decorative?: boolean;
  animated?: boolean;
}) {
  const icon = size <= 28;
  const grown = growth === "adult" || growth === "eft";
  const label = title ?? (mood === "neutral" ? "The intern, a newt" : `The intern, a newt, ${LABEL[mood]}`);
  // Younger newts are drawn smaller in the same box, standing on the same ground line.
  const scale = { egg: 0.7, larva: 0.8, eft: 0.9, adult: 1 }[growth];
  return (
    <svg
      viewBox={icon ? "60 30 60 60" : "0 0 120 120"}
      width={size}
      height={size}
      className={`${animated && !icon ? "ia-bob" : ""} ${className}`}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative || undefined}
    >
      <g transform={icon ? undefined : `translate(${60 * (1 - scale)} ${108 * (1 - scale)}) scale(${scale})`}>
        {growth === "egg" ? <Egg /> : growth === "larva" ? <Larva mood={mood} /> : <Adult mood={mood} crest={growth === "adult"} />}
        {!icon && grown && <Prop mood={mood} />}
        {growth === "adult" && <Cap graduated />}
      </g>
    </svg>
  );
}

export default InternAvatar;
