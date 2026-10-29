import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { c, clamp, ease, sans, serif } from "./theme";

// Fades and lifts a whole scene in and out at its Sequence boundaries.
export const SceneFrame: React.FC<{
  children: React.ReactNode;
  duration: number;
}> = ({ children, duration }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        opacity: interpolate(
          frame,
          [0, 8, duration - 8, duration],
          [0, 1, 1, 0],
          clamp,
        ),
        translate: interpolate(frame, [duration - 8, duration], ["0px 0px", "0px -24px"], {
          ...clamp,
          easing: ease,
        }),
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

// Step label + headline on the left side of feature scenes.
export const Caption: React.FC<{
  step: string;
  title: string;
  body: string;
}> = ({ step, title, body }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = (delay: number) => ({
    opacity: interpolate(frame, [delay, delay + 0.5 * fps], [0, 1], clamp),
    translate: interpolate(
      frame,
      [delay, delay + 0.6 * fps],
      ["0px 30px", "0px 0px"],
      { ...clamp, easing: ease },
    ),
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        top: 0,
        bottom: 0,
        width: 640,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 28,
      }}
    >
      <div
        style={{
          fontFamily: sans,
          fontSize: 26,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: "uppercase",
          color: c.rust,
          ...rise(0),
        }}
      >
        {step}
      </div>
      <div
        style={{
          fontFamily: serif,
          fontSize: 84,
          lineHeight: 1.05,
          fontWeight: 600,
          color: c.ink,
          ...rise(4),
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: sans,
          fontSize: 34,
          lineHeight: 1.4,
          color: c.ink2,
          ...rise(9),
        }}
      >
        {body}
      </div>
    </div>
  );
};

// The StatEase mark (from frontend/public/favicon.svg), drawn up from the baseline.
export const Logo: React.FC<{ size: number; progress: number }> = ({
  size,
  progress,
}) => (
  <svg width={size} height={size} viewBox="0 0 32 32">
    <defs>
      <clipPath id="reveal">
        <rect x="0" y={28 - 28 * progress} width="32" height={28 * progress} />
      </clipPath>
    </defs>
    <g clipPath="url(#reveal)">
      <path
        fill={c.ink}
        d="M0.5 23.7L0.5 21.8L1.0 21.4L1.6 20.9L2.1 20.3L2.7 19.7L3.2 19.0L3.8 18.2L4.3 17.3L4.9 16.4L5.4 15.3L6.0 14.3L6.5 13.2L7.1 12.1L7.6 11.0L8.2 9.9L8.7 8.8L9.3 7.8L9.8 6.9L10.4 6.1L10.9 5.4L11.5 4.8L12.0 4.5L12.6 4.2L13.1 4.2L13.7 4.3L14.2 4.6L14.8 5.1L15.3 5.7L15.9 6.5L16.4 7.3L17.0 8.3L17.0 23.7Z"
      />
      <path
        fill={c.rust}
        d="M18.3 23.7L18.3 10.8L19.4 13.1L20.5 15.2L21.6 17.2L22.7 18.9L23.8 20.2L24.9 21.3L26.0 22.1L27.1 22.7L28.2 23.1L29.3 23.3L30.4 23.5L31.5 23.6L31.5 23.7Z"
      />
    </g>
    <rect
      fill={c.ink}
      x="0.5"
      y="25.2"
      width={31 * Math.min(1, progress * 2)}
      height="2.6"
      rx="1.3"
    />
  </svg>
);

// White card on the right side of feature scenes.
export const Panel: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        position: "absolute",
        right: 140,
        top: 0,
        bottom: 0,
        width: 900,
        display: "flex",
        alignItems: "center",
      }}
    >
    <div
      style={{
        width: "100%",
        background: c.surface,
        border: `2px solid ${c.line}`,
        borderRadius: 8,
        boxShadow: "0 30px 60px -30px rgba(20,33,58,0.25)",
        padding: 48,
        boxSizing: "border-box",
        fontFamily: sans,
        color: c.ink,
        opacity: interpolate(frame, [2, 0.5 * fps], [0, 1], clamp),
        translate: interpolate(frame, [2, 0.8 * fps], ["60px 0px", "0px 0px"], {
          ...clamp,
          easing: ease,
        }),
        ...style,
      }}
    >
      {children}
    </div>
    </div>
  );
};
