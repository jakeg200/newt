"use client";

/**
 * InternAvatar: the intern, our own mascot. A soft, rounded robot with a cream face screen,
 * an intern's ID badge, and a mortarboard whose tassel moves from right to left when it graduates.
 *
 * Self-contained: inline SVG, no dependencies beyond React. Colours come from CSS variables
 * (--ia-shell, --ia-ink, --ia-cap, ...) with hex fallbacks, so the app theme can retint it.
 * Detail adapts to size: <= 28 px is head and cap only, 29-71 px drops fine detail, >= 72 px is full.
 * Animation is subtle, only at full size, and switched off under prefers-reduced-motion.
 *
 * Product rule: the avatar never reacts to the mentor's decisions. Pick the mood from the
 * intern's own situation (its stage, its queue), never from a lesson the mentor just gave.
 */

import type { ReactElement, ReactNode } from "react";

export const MOODS = [
  "neutral",
  "hello",
  "learning",
  "thinking",
  "drafting",
  "handing-back",
  "working",
  "graduated",
  "resting",
  "recertifying",
  "practising",
] as const;

export type Mood = (typeof MOODS)[number];

/** Accessible label (default aria-label) and the product moment each mood belongs to. */
export const MOOD_INFO: Readonly<Record<Mood, { label: string; moment: string }>> = {
  neutral: { label: "The intern", moment: "Default. Header mark, nav, inline mentions." },
  hello: { label: "The intern, waving hello", moment: "Home greeting, first sign-in, start of orientation." },
  learning: { label: "The intern, taking notes", moment: "Shadowing: backtests, sealed predictions, the intern's column on a teaching card." },
  thinking: { label: "The intern, thinking", moment: "Loading, drafting the handbook, working out the evidence, cases it was unsure about." },
  drafting: { label: "The intern, writing a draft", moment: "Supervised practice: drafts waiting for one-tap approval." },
  "handing-back": { label: "The intern, handing a case back", moment: "Hand-backs, each with its reasons." },
  working: { label: "The intern, working on its own", moment: "Autonomous: the digest of what it did alone." },
  graduated: { label: "The intern, celebrating its graduation", moment: "A task type is signed into supervised or autonomous work." },
  resting: { label: "The intern, all caught up", moment: "Empty queues: nothing to teach, approve or audit." },
  recertifying: { label: "The intern, re-certifying", moment: "Model swap: re-running probation on the frozen record." },
  practising: { label: "The intern, back to practice", moment: "Moved back a stage after audits or drift. Calm, not tragic." },
};

/** The task-type stages used by the API, mapped to the mood that shows them. */
export type InternStage = "shadow" | "supervised" | "autonomous" | "demoted";

export const STAGE_MOOD: Readonly<Record<InternStage, Mood>> = {
  shadow: "learning",
  supervised: "drafting",
  autonomous: "working",
  demoted: "practising",
};

export type AvatarDetail = "icon" | "compact" | "full";

/** Which drawing a given pixel size gets. */
export function avatarDetail(size: number): AvatarDetail {
  if (size <= 28) return "icon";
  if (size < 72) return "compact";
  return "full";
}

export interface InternAvatarProps {
  mood?: Mood;
  /** Rendered width and height in CSS pixels. */
  size?: number;
  className?: string;
  /** Overrides the default aria-label for this mood. */
  title?: string;
  /** Subtle motion at full size (always off under prefers-reduced-motion). Default true. */
  animated?: boolean;
  /** Hide from assistive tech when the text beside it already says the same thing. */
  decorative?: boolean;
}

/* ------------------------------------------------------------------------------------------ */
/* Colours: one CSS variable each, hex fallback. Map them to the theme in globals.css.        */
/* ------------------------------------------------------------------------------------------ */

const TOKENS = {
  shell: ["--ia-shell", "#FB9150"],
  shade: ["--ia-shade", "#E8692A"],
  face: ["--ia-face", "#FFF8F1"],
  ink: ["--ia-ink", "#2B211C"],
  cap: ["--ia-cap", "#2A2766"],
  capd: ["--ia-cap-edge", "#1A1846"],
  caph: ["--ia-cap-sheen", "#5B58C9"],
  tassel: ["--ia-tassel", "#F7B731"],
  cheek: ["--ia-cheek", "#FF8F7E"],
  paper: ["--ia-paper", "#FFFFFF"],
  acc: ["--ia-accent", "#6062E8"],
  accs: ["--ia-accent-soft", "#E3E5FF"],
  ok: ["--ia-ok", "#17834B"],
} as const;

type Token = keyof typeof TOKENS;

const fill = (t: Token) => `ia-f-${t}`;
const stroke = (t: Token) => `ia-s-${t}`;

const CSS = [
  ...Object.entries(TOKENS).map(([k, [v, hex]]) => `.ia .ia-f-${k}{fill:var(${v},${hex})}.ia .ia-s-${k}{stroke:var(${v},${hex})}`),
  ".ia .ia-shadow{fill:var(--ia-ink,#2B211C);opacity:.12}",
  "@keyframes ia-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.6px)}}",
  "@keyframes ia-blink{0%,93%,100%{transform:scaleY(1)}95.5%{transform:scaleY(.12)}}",
  "@keyframes ia-wave{0%,100%{transform:rotate(0)}50%{transform:rotate(-16deg)}}",
  "@keyframes ia-sway{0%,100%{transform:rotate(0)}35%{transform:rotate(9deg)}70%{transform:rotate(-6deg)}}",
  "@keyframes ia-steam{0%{opacity:0;transform:translateY(2px)}45%{opacity:1}100%{opacity:0;transform:translateY(-5px)}}",
  "@keyframes ia-spin{to{transform:rotate(360deg)}}",
  "@keyframes ia-twinkle{0%,100%{opacity:1}50%{opacity:.35}}",
  ".ia-motion .ia-fig{animation:ia-bob 5s ease-in-out infinite}",
  ".ia-motion .ia-blink{transform-box:fill-box;transform-origin:center;animation:ia-blink 6.5s ease-in-out 1.2s infinite}",
  ".ia-motion .ia-wave{transform-box:fill-box;transform-origin:0% 100%;animation:ia-wave .8s ease-in-out .3s 3}",
  ".ia-motion .ia-sway{transform-box:fill-box;transform-origin:50% 0%;animation:ia-sway 2.6s ease-in-out .2s 3}",
  ".ia-motion .ia-steam{animation:ia-steam 3.2s ease-out infinite}",
  ".ia-motion .ia-steam+.ia-steam{animation-delay:1.6s}",
  ".ia-motion .ia-spin{transform-box:fill-box;transform-origin:center;animation:ia-spin 7s linear infinite}",
  ".ia-motion .ia-twinkle{animation:ia-twinkle 1.4s ease-in-out 5}",
  "@media (prefers-reduced-motion:reduce){.ia-motion *{animation:none!important}}",
].join("");

/* ------------------------------------------------------------------------------------------ */
/* Drawing kit                                                                                 */
/* ------------------------------------------------------------------------------------------ */

interface Kit {
  detail: AvatarDetail;
  /** Outline width in viewBox units: thicker as the avatar gets smaller. */
  sw: number;
  /** Highlights, lanyard, text lines, motion marks. */
  fine: boolean;
}

const KITS: Readonly<Record<AvatarDetail, Kit>> = {
  icon: { detail: "icon", sw: 4, fine: false },
  compact: { detail: "compact", sw: 3, fine: false },
  full: { detail: "full", sw: 2.2, fine: true },
};

type Eyes = "open" | "look" | "up" | "down" | "calm" | "happy" | "closed";
type Mouth = "smile" | "small" | "grin" | "hmm";
type Brows = "none" | "raised" | "quizzical" | "soft";

interface Face {
  eyes: Eyes;
  mouth: Mouth;
  brows: Brows;
  cheeks: boolean;
}

const FACES: Readonly<Record<Mood, Face>> = {
  neutral: { eyes: "open", mouth: "smile", brows: "none", cheeks: true },
  hello: { eyes: "open", mouth: "grin", brows: "none", cheeks: true },
  learning: { eyes: "look", mouth: "small", brows: "none", cheeks: true },
  thinking: { eyes: "up", mouth: "hmm", brows: "quizzical", cheeks: false },
  drafting: { eyes: "down", mouth: "small", brows: "none", cheeks: true },
  "handing-back": { eyes: "open", mouth: "small", brows: "raised", cheeks: true },
  working: { eyes: "open", mouth: "smile", brows: "none", cheeks: true },
  graduated: { eyes: "happy", mouth: "grin", brows: "none", cheeks: true },
  resting: { eyes: "closed", mouth: "small", brows: "none", cheeks: true },
  recertifying: { eyes: "calm", mouth: "small", brows: "soft", cheeks: false },
  practising: { eyes: "calm", mouth: "smile", brows: "soft", cheeks: true },
};

/** Pupil offset and height for the pill-shaped eyes. */
const EYE_SHAPE: Readonly<Record<Exclude<Eyes, "happy" | "closed">, { dx: number; dy: number; h: number }>> = {
  open: { dx: 0, dy: 0, h: 11 },
  look: { dx: 3, dy: 1, h: 11 },
  up: { dx: 2, dy: -2.5, h: 10 },
  down: { dx: 0, dy: 2, h: 8.5 },
  calm: { dx: 0, dy: 1, h: 8 },
};

function EyesPart({ kind, kit }: { kind: Eyes; kit: Kit }): ReactElement {
  const icon = kit.detail === "icon";
  const centres = icon ? [51, 77] : [52, 76];
  const arc = icon ? 4 : 2.8;
  if (kind === "happy") {
    return (
      <g className={stroke("ink")} strokeWidth={arc} fill="none">
        {centres.map((c) => <path key={c} d={`M${c - 5} 59.5 Q${c} 51.5 ${c + 5} 59.5`} />)}
      </g>
    );
  }
  if (kind === "closed") {
    return (
      <g className={stroke("ink")} strokeWidth={arc} fill="none">
        {centres.map((c) => <path key={c} d={`M${c - 4.8} 56 Q${c} 61.5 ${c + 4.8} 56`} />)}
      </g>
    );
  }
  const s = EYE_SHAPE[kind];
  const w = icon ? 9.5 : 7;
  const h = icon ? s.h * 1.25 : s.h;
  const dx = icon ? s.dx * 0.7 : s.dx;
  const dy = icon ? s.dy * 0.7 : s.dy;
  return (
    <g className="ia-blink">
      {centres.map((c) => (
        <g key={c}>
          <rect x={c + dx - w / 2} y={57 + dy - h / 2} width={w} height={h} rx={w / 2} className={fill("ink")} />
          {kit.fine && <circle cx={c + dx - 1.2} cy={57 + dy - h / 2 + 2.7} r={1.3} className={fill("face")} />}
        </g>
      ))}
    </g>
  );
}

function MouthPart({ kind, kit }: { kind: Mouth; kit: Kit }): ReactElement {
  const icon = kit.detail === "icon";
  const w = icon ? 4 : 2.6;
  switch (kind) {
    case "grin":
      return (
        <g>
          <path d={icon ? "M55.5 65 Q64 79 72.5 65 Z" : "M56.5 65.5 Q64 76.5 71.5 65.5 Z"} className={`${fill("ink")} ${stroke("ink")}`} strokeWidth={icon ? 2 : 1.4} />
          {kit.fine && <ellipse cx={64} cy={69.4} rx={3.2} ry={1.5} className={fill("cheek")} />}
        </g>
      );
    case "small":
      return <path d={icon ? "M58 67 Q64 72 70 67" : "M59.5 67 Q64 70.4 68.5 67"} className={stroke("ink")} strokeWidth={w} fill="none" />;
    case "hmm":
      return <path d={icon ? "M58 68.5 Q64 66.4 70 68" : "M59 68.2 Q64 66.4 69 67.6"} className={stroke("ink")} strokeWidth={w} fill="none" />;
    default:
      return <path d={icon ? "M56.5 66.5 Q64 74 71.5 66.5" : "M57.5 66 Q64 71.8 70.5 66"} className={stroke("ink")} strokeWidth={w} fill="none" />;
  }
}

function BrowsPart({ kind }: { kind: Brows }): ReactElement | null {
  const paths: Record<Brows, string[]> = {
    none: [],
    raised: ["M48 46.8 Q52 43.6 56 46.8", "M72 46.8 Q76 43.6 80 46.8"],
    quizzical: ["M47.5 47.6 Q52 46.6 56.5 47.6", "M72.5 46 Q77.5 42.6 82 45.2"],
    soft: ["M48 48 Q52 46.6 56 48", "M72 48 Q76 46.6 80 48"],
  };
  if (paths[kind].length === 0) return null;
  return (
    <g className={stroke("ink")} strokeWidth={2} fill="none">
      {paths[kind].map((d) => <path key={d} d={d} />)}
    </g>
  );
}

function Head({ face, kit }: { face: Face; kit: Kit }): ReactElement {
  const icon = kit.detail === "icon";
  return (
    <g>
      <rect x={23} y={47} width={10} height={18} rx={5} className={`${fill("shade")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      <rect x={95} y={47} width={10} height={18} rx={5} className={`${fill("shade")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      <rect x={29} y={27} width={70} height={56} rx={24} className={`${fill("shell")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      {kit.fine && <path d="M35.2 53 Q34.8 45 39.4 40.6" className={stroke("face")} strokeWidth={2.6} opacity={0.55} fill="none" />}
      {icon ? (
        <rect x={35} y={39.5} width={58} height={37} rx={16} className={fill("face")} />
      ) : (
        <rect x={37} y={41} width={54} height={34} rx={15} className={fill("face")} />
      )}
      {face.cheeks && !icon && (
        <g className={fill("cheek")} opacity={0.55}>
          <circle cx={44.5} cy={64.5} r={3.6} />
          <circle cx={83.5} cy={64.5} r={3.6} />
        </g>
      )}
      {!icon && <BrowsPart kind={face.brows} />}
      <EyesPart kind={face.eyes} kit={kit} />
      <MouthPart kind={face.mouth} kit={kit} />
    </g>
  );
}

function Cap({ graduated, kit, sway }: { graduated: boolean; kit: Kit; sway: boolean }): ReactElement {
  const icon = kit.detail === "icon";
  const cord = icon ? 3.2 : 2.2;
  // The tassel hangs on the right while studying and moves to the left on graduation.
  return (
    <g>
      <path d="M43 25 L85 25 L85 34.5 Q64 42.5 43 34.5 Z" className={`${fill("cap")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      <path d="M30 24 L64 36 L98 24 L98 27.2 L64 39.2 L30 27.2 Z" className={`${fill("capd")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      <path d="M30 24 L64 12 L98 24 L64 36 Z" className={`${fill("cap")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      {kit.fine && <path d="M41 23.6 L64 15.6 L75 19.4" className={stroke("caph")} strokeWidth={1.6} fill="none" opacity={0.7} />}
      <g transform={graduated ? "translate(128 0) scale(-1 1)" : undefined}>
        <path d="M64 24 L96.5 25.2" className={stroke("tassel")} strokeWidth={cord} fill="none" />
        <g className={sway ? "ia-sway" : undefined}>
          <path d="M96.5 25.2 Q99.5 25.6 99.5 28.6 L99.5 37" className={stroke("ink")} strokeWidth={cord + 2} fill="none" />
          <path d="M96.5 25.2 Q99.5 25.6 99.5 28.6 L99.5 37" className={stroke("tassel")} strokeWidth={cord} fill="none" />
          {icon ? (
            <rect x={95.5} y={35.5} width={8} height={12} rx={3} className={`${fill("tassel")} ${stroke("ink")}`} strokeWidth={2.4} />
          ) : (
            <rect x={96.5} y={36} width={6} height={11} rx={2.4} className={`${fill("tassel")} ${stroke("ink")}`} strokeWidth={1.6} />
          )}
          {kit.fine && <path d="M96.5 39.6 L102.5 39.6" className={stroke("ink")} strokeWidth={1.1} fill="none" />}
        </g>
      </g>
      <circle cx={64} cy={24} r={icon ? 3.4 : 2.8} className={`${fill("tassel")} ${stroke("ink")}`} strokeWidth={icon ? 1.6 : 1.1} />
    </g>
  );
}

/** A capsule arm: an ink stroke with a narrower shade stroke on top. The round cap is the hand. */
function Arm({ d, kit, className }: { d: string; kit: Kit; className?: string }): ReactElement {
  return (
    <g className={className}>
      <path d={d} className={stroke("ink")} strokeWidth={8 + 2 * kit.sw} fill="none" />
      <path d={d} className={stroke("shade")} strokeWidth={8} fill="none" />
    </g>
  );
}

const ARM_DOWN_L = "M46 88 L37.5 102";
const ARM_DOWN_R = "M82 88 L90.5 102";

function Body({ kit, badge }: { kit: Kit; badge: boolean }): ReactElement {
  return (
    <g>
      <rect x={43} y={78} width={42} height={32} rx={13} className={`${fill("shell")} ${stroke("ink")}`} strokeWidth={kit.sw} />
      {badge && kit.fine && <path d="M53 80 L64 90.5 L75 80" className={stroke("acc")} strokeWidth={1.8} fill="none" />}
      {badge && (
        <g>
          <rect x={58} y={89} width={12} height={11} rx={2.2} className={`${fill("paper")} ${stroke("ink")}`} strokeWidth={kit.fine ? 1.6 : 2.2} />
          {kit.fine && <path d="M61 95.6 L67 95.6" className={stroke("acc")} strokeWidth={1.6} fill="none" />}
        </g>
      )}
    </g>
  );
}

/** A small filled triangle used as an arrowhead. */
function Arrowhead({ pts, className }: { pts: string; className: string }): ReactElement {
  return <polygon points={pts} className={className} />;
}

interface Pose {
  /** Drawn before the body and head (arms hanging behind). */
  back?: ReactNode;
  /** Drawn in front of the body (props and holding arms). */
  front?: ReactNode;
  /** Drawn last, outside the figure (bubbles, badges, confetti). */
  extra?: ReactNode;
  /** Whether the chest badge is visible (props in front hide it). */
  badge: boolean;
}

function pose(mood: Mood, kit: Kit): Pose {
  const sw = kit.sw;
  const showExtras = kit.detail !== "icon";
  const o = (t: Token, w = sw) => ({ className: `${fill(t)} ${stroke("ink")}`, strokeWidth: w });
  const thin = kit.fine ? 1.6 : 2.2;

  switch (mood) {
    case "hello":
      return {
        badge: true,
        back: <Arm d={ARM_DOWN_L} kit={kit} />,
        front: <Arm d="M82 89 L100 70" kit={kit} className="ia-wave" />,
        extra: kit.fine && (
          <g className={stroke("ink")} strokeWidth={1.8} fill="none" opacity={0.45}>
            <path d="M107 62 Q111 66 110 71" />
            <path d="M111.5 57.5 Q117 64 115.5 72" />
          </g>
        ),
      };

    case "learning":
      return {
        badge: false,
        back: undefined,
        front: (
          <g>
            <path d="M46 89 L64 91.5 L82 89 L82 107.5 L64 110 L46 107.5 Z" {...o("acc")} />
            <path d="M48.5 90.5 L64 92.6 L64 107.6 L48.5 105.5 Z" {...o("paper", thin)} />
            <path d="M64 92.6 L79.5 90.5 L79.5 105.5 L64 107.6 Z" {...o("paper", thin)} />
            {kit.fine && (
              <g className={stroke("acc")} strokeWidth={1.4} fill="none" opacity={0.75}>
                <path d="M51.5 95.4 L61 96.6" />
                <path d="M51.5 99.4 L61 100.6" />
                <path d="M67 96.6 L76.5 95.4" />
                <path d="M67 100.6 L74 99.7" />
              </g>
            )}
            <Arm d="M45.5 87.5 Q41.5 95 47.5 100" kit={kit} />
            <Arm d="M82.5 87.5 Q86.5 95 80.5 100" kit={kit} />
          </g>
        ),
      };

    case "thinking":
      return {
        badge: true,
        back: <Arm d={ARM_DOWN_L} kit={kit} />,
        front: <Arm d="M83 91.5 Q95 89.5 83.5 81.5" kit={kit} />,
        extra: showExtras && (
          <g>
            <circle cx={99} cy={36.5} r={2.2} {...o("face", thin)} />
            <circle cx={103.5} cy={29.8} r={3.2} {...o("face", thin)} />
            <circle cx={111} cy={18} r={10} {...o("face", kit.fine ? 1.8 : 2.4)} />
            <path d="M107.4 15.6 Q107.4 11.8 111 11.8 Q114.6 11.8 114.6 15.2 Q114.6 17.8 111 19 L111 21.2" className={stroke("acc")} strokeWidth={kit.fine ? 2.4 : 3} fill="none" />
            <circle cx={111} cy={25.2} r={kit.fine ? 1.4 : 1.8} className={fill("acc")} />
          </g>
        ),
      };

    case "drafting":
      return {
        badge: false,
        back: undefined,
        front: (
          <g>
            <g transform="rotate(-8 64 97)">
              <rect x={50} y={86} width={28} height={22} rx={2} {...o("paper")} />
              <g className={stroke("acc")} strokeWidth={kit.fine ? 1.6 : 2.4} fill="none">
                <path d="M54 92 L72 92" />
                <path d="M54 97 L68 97" />
                {kit.fine && <path d="M54 102 L62 102" />}
              </g>
            </g>
            <Arm d="M46 88 L52 98" kit={kit} />
            <path d="M93 88 L79.7 98.3" className={stroke("ink")} strokeWidth={4.4 + 2 * (kit.fine ? 1.4 : 2)} strokeLinecap="butt" fill="none" />
            <path d="M93 88 L79.7 98.3" className={stroke("acc")} strokeWidth={4.4} strokeLinecap="butt" fill="none" />
            <polygon points="81.1,100.1 78.3,96.5 75,102" {...o("paper", kit.fine ? 1.4 : 2)} />
            <circle cx={75.6} cy={101.4} r={1.1} className={fill("ink")} />
            <Arm d="M81.5 88 L86.7 93" kit={kit} />
          </g>
        ),
      };

    case "handing-back":
      return {
        badge: true,
        back: undefined,
        front: (
          <g>
            <path d="M77 82 L77 79.5 Q77 77.5 79 77.5 L86 77.5 L88.5 82 Z" {...o("acc", thin)} />
            <rect x={75} y={82} width={31} height={23} rx={3} {...o("acc")} />
            <rect x={80} y={79} width={21} height={12} rx={1.5} {...o("paper", thin)} />
            {kit.fine && <path d="M83 83.6 L95 83.6" className={stroke("acc")} strokeWidth={1.5} fill="none" />}
            <path d="M75 88 L106 88 L106 102 Q106 105 103 105 L78 105 Q75 105 75 102 Z" {...o("accs")} />
            <Arm d="M46 89 Q60 101 77 97" kit={kit} />
            <Arm d="M82 89 Q95 93 104.5 97" kit={kit} />
          </g>
        ),
        extra: showExtras && (
          <g>
            <path d="M98 77 Q110 68 119 79" className={stroke("acc")} strokeWidth={kit.fine ? 2.4 : 3.2} fill="none" />
            <Arrowhead pts="120.6,80.9 120.5,76.4 116.2,80" className={`${fill("acc")} ${stroke("acc")}`} />
          </g>
        ),
      };

    case "working":
      return {
        badge: false,
        back: undefined,
        front: (
          <g>
            <rect x={51} y={87} width={26} height={20} rx={2} transform="rotate(6 64 97)" {...o("paper", thin)} />
            <rect x={50} y={89} width={26} height={20} rx={2} transform="rotate(-3 63 99)" {...o("paper")} />
            <g className={stroke("acc")} strokeWidth={kit.fine ? 1.6 : 2.4} fill="none" transform="rotate(-3 63 99)">
              <path d="M54 95 L67 95" />
              {kit.fine && <path d="M54 99.5 L64 99.5" />}
              {kit.fine && <path d="M54 104 L61 104" />}
            </g>
            <Arm d="M46 88 Q42 96 50 101" kit={kit} />
            <Arm d="M82 88 Q86 96 77.5 101" kit={kit} />
            <circle cx={78} cy={89} r={7.2} {...o("ok", kit.fine ? 1.8 : 2.4)} />
            <path d="M74.6 89.2 L77.1 91.7 L81.5 86.6" className={stroke("paper")} strokeWidth={2.4} fill="none" />
          </g>
        ),
      };

    case "graduated": {
      const confetti: { x: number; y: number; r: number; t: Token; c?: boolean; core?: boolean }[] = [
        { x: 18, y: 20, r: 25, t: "acc", core: true },
        { x: 44, y: 5, r: -20, t: "tassel" },
        { x: 86, y: 6, r: 40, t: "ok", c: true },
        { x: 112, y: 30, r: 15, t: "acc", core: true },
        { x: 14, y: 62, r: -35, t: "tassel", core: true },
        { x: 118, y: 52, r: 0, t: "cheek", c: true },
        { x: 108, y: 98, r: 30, t: "shade" },
        { x: 18, y: 96, r: -10, t: "ok" },
        { x: 26, y: 40, r: 0, t: "shade", c: true },
      ];
      return {
        badge: true,
        back: undefined,
        front: (
          <g>
            <Arm d="M46 88 L30 73" kit={kit} />
            <Arm d="M82 88 L99 70" kit={kit} />
            <g transform="translate(101 64.5) rotate(-35)">
              <rect x={-13} y={-4.5} width={26} height={9} rx={4.5} {...o("paper", thin)} />
              <ellipse cx={12} cy={0} rx={2.4} ry={4.5} {...o("paper", thin)} />
              <rect x={-2.5} y={-5} width={5} height={10} rx={1} {...o("acc", kit.fine ? 1.2 : 1.8)} />
            </g>
          </g>
        ),
        extra: showExtras && (
          <g className="ia-twinkle">
            {confetti
              .filter((p) => kit.fine || p.core)
              .map((p) =>
                p.c ? (
                  <circle key={`${p.x}-${p.y}`} cx={p.x} cy={p.y} r={kit.fine ? 2 : 3} className={fill(p.t)} />
                ) : (
                  <rect key={`${p.x}-${p.y}`} x={p.x - (kit.fine ? 3 : 4)} y={p.y - (kit.fine ? 1.4 : 2)} width={kit.fine ? 6 : 8}
                        height={kit.fine ? 2.8 : 4} rx={1} transform={`rotate(${p.r} ${p.x} ${p.y})`} className={fill(p.t)} />
                ),
              )}
          </g>
        ),
      };
    }

    case "resting":
      return {
        badge: true,
        back: <Arm d={ARM_DOWN_L} kit={kit} />,
        front: (
          <g>
            <path d="M100.5 94.5 Q106 94.5 106 99 Q106 103.5 100.5 103.5" className={stroke("ink")} strokeWidth={kit.fine ? 2.2 : 3} fill="none" />
            <rect x={88} y={91} width={13} height={15} rx={3} {...o("paper")} />
            <rect x={88} y={96} width={13} height={3.5} className={fill("acc")} />
            <Arm d="M82 89 L88.5 97.5" kit={kit} />
          </g>
        ),
        extra: kit.fine && (
          <g className={stroke("ink")} strokeWidth={1.6} fill="none" opacity={0.45}>
            <path className="ia-steam" d="M93.5 87 Q91.5 84 93.5 81 Q95.5 78 93.5 75" />
            <path className="ia-steam" d="M98.5 87 Q96.5 84 98.5 81 Q100.5 78 98.5 75" />
          </g>
        ),
      };

    case "recertifying":
      return {
        badge: false,
        back: undefined,
        front: (
          <g>
            <rect x={51} y={86} width={26} height={23} rx={3} {...o("acc")} />
            <rect x={54} y={90} width={20} height={16} rx={1.5} {...o("paper", thin)} />
            <rect x={59} y={84} width={10} height={5} rx={1.5} {...o("cap", thin)} />
            {kit.fine ? (
              <g fill="none">
                <path d="M57 94 L58.5 95.5 L61 92.6" className={stroke("ok")} strokeWidth={1.6} />
                <path d="M63.5 94.2 L71 94.2" className={stroke("acc")} strokeWidth={1.4} />
                <path d="M57 99.2 L58.5 100.7 L61 97.8" className={stroke("ok")} strokeWidth={1.6} />
                <path d="M63.5 99.4 L71 99.4" className={stroke("acc")} strokeWidth={1.4} />
                <circle cx={59} cy={103.6} r={1.4} className={stroke("acc")} strokeWidth={1.2} />
                <path d="M63.5 103.6 L69 103.6" className={stroke("acc")} strokeWidth={1.4} />
              </g>
            ) : (
              <g className={stroke("acc")} strokeWidth={2.2} fill="none">
                <path d="M57.5 95 L70.5 95" />
                <path d="M57.5 101 L67 101" />
              </g>
            )}
            <Arm d="M46 88 L52 100" kit={kit} />
            <Arm d="M82 88 L76 100" kit={kit} />
          </g>
        ),
        extra: showExtras && (
          <g>
            <circle cx={110} cy={22} r={10.5} {...o("accs", kit.fine ? 1.8 : 2.4)} />
            <g className="ia-spin">
              <path d="M103.6 23.1 A6.5 6.5 0 0 1 115 17.8" className={stroke("acc")} strokeWidth={kit.fine ? 2.2 : 2.8} fill="none" />
              <Arrowhead pts="116.4,19.5 116.4,15.3 112.4,18.7" className={`${fill("acc")} ${stroke("acc")}`} />
              <g transform="rotate(180 110 22)">
                <path d="M103.6 23.1 A6.5 6.5 0 0 1 115 17.8" className={stroke("acc")} strokeWidth={kit.fine ? 2.2 : 2.8} fill="none" />
                <Arrowhead pts="116.4,19.5 116.4,15.3 112.4,18.7" className={`${fill("acc")} ${stroke("acc")}`} />
              </g>
            </g>
          </g>
        ),
      };

    case "practising":
      return {
        badge: false,
        back: undefined,
        front: (
          <g>
            <path d="M70 107 L70 115 L72.2 112.8 L74.4 115 L74.4 107 Z" {...o("cheek", thin)} />
            <rect x={52} y={85} width={24} height={24} rx={2.5} {...o("acc")} />
            <rect x={52} y={85} width={5.5} height={24} rx={2} {...o("cap", thin)} />
            <rect x={61} y={90.5} width={11} height={5.5} rx={1.2} {...o("paper", kit.fine ? 1.2 : 1.8)} />
            <Arm d="M46 88 Q50 98 59 100.5" kit={kit} />
            <Arm d="M82 88 Q79 97.5 71 99.5" kit={kit} />
          </g>
        ),
      };

    default:
      return {
        badge: true,
        back: (
          <>
            <Arm d={ARM_DOWN_L} kit={kit} />
            <Arm d={ARM_DOWN_R} kit={kit} />
          </>
        ),
      };
  }
}

/* ------------------------------------------------------------------------------------------ */
/* Component                                                                                   */
/* ------------------------------------------------------------------------------------------ */

export function InternAvatar({
  mood = "neutral",
  size = 48,
  className,
  title,
  animated = true,
  decorative = false,
}: InternAvatarProps): ReactElement {
  const kit = KITS[avatarDetail(size)];
  const face = FACES[mood];
  const icon = kit.detail === "icon";
  const motion = animated && kit.detail === "full";
  const p = icon ? null : pose(mood, kit);
  const a11y = decorative
    ? { "aria-hidden": true as const }
    : { role: "img" as const, "aria-label": title ?? MOOD_INFO[mood].label };

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={icon ? "20 4 88 88" : "0 0 128 128"}
      width={size}
      height={size}
      className={["ia", motion ? "ia-motion" : null, className].filter(Boolean).join(" ")}
      data-mood={mood}
      {...a11y}
    >
      <style>{CSS}</style>
      <g strokeLinecap="round" strokeLinejoin="round">
        {p && <ellipse cx={64} cy={118} rx={25} ry={3.4} className="ia-shadow" />}
        <g className="ia-fig">
          {p?.back}
          {p && <Body kit={kit} badge={p.badge} />}
          <Head face={face} kit={kit} />
          <Cap graduated={mood === "graduated"} kit={kit} sway={motion && mood === "graduated"} />
          {p?.front}
          {p?.extra}
        </g>
      </g>
    </svg>
  );
}

export default InternAvatar;
