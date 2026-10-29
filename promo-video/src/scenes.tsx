import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Caption, Logo, Panel } from "./parts";
import { c, clamp, ease, mono, sans, serif } from "./theme";

const pop = (frame: number, at: number) => ({
  opacity: interpolate(frame, [at, at + 6], [0, 1], clamp),
  scale: interpolate(frame, [at, at + 12], [0.85, 1], {
    ...clamp,
    easing: Easing.bezier(0.34, 1.56, 0.64, 1),
  }),
});

const Check: React.FC<{ progress: number; color?: string; size?: number }> = ({
  progress,
  color = c.success,
  size = 34,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="11" fill={color} opacity={progress > 0 ? 1 : 0} />
    <path
      d="M6.5 12.5l3.5 3.5 7.5-8"
      fill="none"
      stroke="#fff"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="20"
      strokeDashoffset={20 - 20 * progress}
    />
  </svg>
);

/* ---------- 1. Intro ---------- */
export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{ alignItems: "center", justifyContent: "center", gap: 40 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 36 }}>
        <Logo
          size={150}
          progress={interpolate(frame, [0, 0.9 * fps], [0, 1], {
            ...clamp,
            easing: ease,
          })}
        />
        <div
          style={{
            fontFamily: serif,
            fontSize: 120,
            fontWeight: 600,
            color: c.ink,
            letterSpacing: -1,
            clipPath: `inset(0 ${interpolate(frame, [12, 1.4 * fps], [100, 0], { ...clamp, easing: ease })}% 0 0)`,
          }}
        >
          StatEase
        </div>
      </div>
      <div
        style={{
          fontFamily: sans,
          fontSize: 46,
          color: c.ink2,
          opacity: interpolate(frame, [1.1 * fps, 1.6 * fps], [0, 1], clamp),
          translate: interpolate(
            frame,
            [1.1 * fps, 1.7 * fps],
            ["0px 24px", "0px 0px"],
            { ...clamp, easing: ease },
          ),
        }}
      >
        Research statistics —{" "}
        <span style={{ color: c.rust, fontWeight: 600 }}>without code.</span>
      </div>
    </AbsoluteFill>
  );
};

/* ---------- 2. Upload ---------- */
const columns = [
  { name: "Age", type: "Numeric", color: c.accent },
  { name: "Sex", type: "Categorical", color: c.rust },
  { name: "Year level", type: "Ordinal", color: "#6a5a95" },
  { name: "Satisfaction Q1–Q10", type: "Likert scale", color: "#b88a1c" },
  { name: "Exam score", type: "Numeric", color: c.accent },
];

export const Upload: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Caption
        step="01 · Upload"
        title="Drop in your data"
        body="Excel, CSV, JSON or Parquet. Every column's type is detected for you."
      />
      <Panel>
        <div
          style={{
            height: 190,
            border: `3px dashed ${interpolate(frame, [18, 26], [0, 1], clamp) > 0.5 ? c.accent : c.line}`,
            background: interpolate(frame, [18, 26], [0, 1], clamp) > 0.5 ? c.accentSoft : c.paper,
            borderRadius: 8,
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 22,
              background: c.surface,
              border: `2px solid ${c.border}`,
              borderRadius: 6,
              padding: "18px 28px",
              boxShadow: "0 12px 24px -12px rgba(20,33,58,0.3)",
              translate: interpolate(frame, [4, 24], ["0px -260px", "0px 0px"], {
                ...clamp,
                easing: Easing.bezier(0.34, 1.3, 0.64, 1),
              }),
              rotate: interpolate(frame, [4, 24], ["-6deg", "0deg"], clamp),
            }}
          >
            <div
              style={{
                width: 52,
                height: 62,
                background: c.success,
                borderRadius: 4,
                color: "#fff",
                fontSize: 18,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              XLSX
            </div>
            <div>
              <div style={{ fontSize: 32, fontWeight: 500 }}>
                thesis_survey.xlsx
              </div>
              <div style={{ fontSize: 24, color: c.ink2 }}>
                {Math.round(
                  interpolate(frame, [26, 1.5 * fps], [0, 120], clamp),
                )}{" "}
                respondents · 14 columns
              </div>
            </div>
          </div>
          <div
            style={{
              position: "absolute",
              left: 0,
              bottom: -3,
              height: 6,
              background: c.accent,
              borderRadius: 3,
              width: `${interpolate(frame, [24, 1.5 * fps], [0, 100], { ...clamp, easing: ease })}%`,
            }}
          />
        </div>
        <div
          style={{
            marginTop: 40,
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: 2,
            textTransform: "uppercase",
            color: c.ink2,
            opacity: interpolate(frame, [1.4 * fps, 1.6 * fps], [0, 1], clamp),
          }}
        >
          Detected variables
        </div>
        <div style={{ marginTop: 14 }}>
          {columns.map((col, i) => {
            const at = 1.5 * fps + i * 4;
            return (
              <div
                key={col.name}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "14px 0",
                  borderBottom: `2px solid ${c.border}`,
                  fontSize: 30,
                  opacity: interpolate(frame, [at, at + 6], [0, 1], clamp),
                  translate: interpolate(
                    frame,
                    [at, at + 10],
                    ["-30px 0px", "0px 0px"],
                    { ...clamp, easing: ease },
                  ),
                }}
              >
                <span>{col.name}</span>
                <span
                  style={{
                    fontSize: 24,
                    fontWeight: 600,
                    color: col.color,
                    border: `2px solid ${col.color}`,
                    borderRadius: 4,
                    padding: "4px 14px",
                    ...pop(frame, at + 4),
                  }}
                >
                  {col.type}
                </span>
              </div>
            );
          })}
        </div>
      </Panel>
    </AbsoluteFill>
  );
};

/* ---------- 3. Suggest ---------- */
const objective =
  "Determine whether exam scores differ between male and female students.";
const checks = [
  "Normality — Shapiro–Wilk",
  "Equal variances — Levene's test",
  "Independent groups",
];

export const Suggest: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const typed = Math.round(
    interpolate(frame, [6, 1.3 * fps], [0, objective.length], clamp),
  );
  const cardAt = 1.4 * fps;
  return (
    <AbsoluteFill>
      <Caption
        step="02 · Analyze"
        title="The right test, suggested"
        body="Paste your objectives. Each one is matched to the analysis that fits your data."
      />
      <Panel>
        <div
          style={{
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: 2,
            textTransform: "uppercase",
            color: c.ink2,
          }}
        >
          Objective 1
        </div>
        <div
          style={{
            marginTop: 14,
            fontFamily: serif,
            fontSize: 36,
            lineHeight: 1.4,
            minHeight: 110,
            borderLeft: `5px solid ${c.rust}`,
            paddingLeft: 24,
          }}
        >
          {objective.slice(0, typed)}
          <span
            style={{
              opacity: typed < objective.length && frame % 16 < 10 ? 1 : 0,
              color: c.rust,
            }}
          >
            |
          </span>
        </div>
        <div
          style={{
            marginTop: 36,
            background: c.accentSoft,
            border: `2px solid ${c.accent}`,
            borderRadius: 8,
            padding: "26px 32px",
            ...pop(frame, cardAt),
          }}
        >
          <div
            style={{
              fontSize: 22,
              fontWeight: 600,
              letterSpacing: 2,
              textTransform: "uppercase",
              color: c.accent,
            }}
          >
            Recommended analysis
          </div>
          <div style={{ fontSize: 44, fontWeight: 600, marginTop: 6 }}>
            Independent-samples t-test
          </div>
        </div>
        <div style={{ marginTop: 30 }}>
          {checks.map((label, i) => {
            const at = cardAt + 10 + i * 6;
            return (
              <div
                key={label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 18,
                  fontSize: 30,
                  padding: "10px 0",
                  opacity: interpolate(frame, [at, at + 5], [0, 1], clamp),
                }}
              >
                <Check
                  progress={interpolate(frame, [at, at + 10], [0, 1], clamp)}
                />
                {label}
                <span
                  style={{
                    marginLeft: "auto",
                    fontFamily: mono,
                    fontSize: 24,
                    color: c.success,
                  }}
                >
                  passed
                </span>
              </div>
            );
          })}
        </div>
      </Panel>
    </AbsoluteFill>
  );
};

/* ---------- 4. Results ---------- */
const groups = [
  { label: "Male", mean: 78.4, sd: 6.1, color: c.accent },
  { label: "Female", mean: 83.1, sd: 5.4, color: c.chart2 },
];

export const Results: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const grow = interpolate(frame, [8, 1.2 * fps], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const scale = (v: number) => ((v - 60) / 35) * 300;
  const apaAt = 1.3 * fps;
  return (
    <AbsoluteFill>
      <Caption
        step="03 · Interpret"
        title="Results in APA style"
        body="Tables, charts and plain-language interpretation, computed from your data."
      />
      <Panel>
        <div style={{ fontSize: 26, fontWeight: 600 }}>
          Exam score by sex
        </div>
        <div
          style={{
            position: "relative",
            height: 340,
            marginTop: 20,
            borderBottom: `3px solid ${c.ink}`,
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            gap: 140,
          }}
        >
          {[0, 1, 2, 3].map((g) => (
            <div
              key={g}
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: g * 100,
                borderTop: `2px solid ${c.border}`,
                width: `${interpolate(frame, [0, 14], [0, 100], clamp)}%`,
              }}
            />
          ))}
          {groups.map((g) => {
            const h = scale(g.mean) * grow;
            return (
              <div
                key={g.label}
                style={{
                  position: "relative",
                  width: 170,
                  height: h,
                  background: g.color,
                  borderRadius: "4px 4px 0 0",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: 83,
                    width: 4,
                    background: c.ink,
                    top: -((scale(g.mean + g.sd) - scale(g.mean)) * grow),
                    height: (scale(g.mean + g.sd) - scale(g.mean - g.sd)) * grow,
                    opacity: interpolate(frame, [1 * fps, 1.2 * fps], [0, 1], clamp),
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: -70 - (scale(g.mean + g.sd) - scale(g.mean)) * grow,
                    width: "100%",
                    textAlign: "center",
                    fontFamily: mono,
                    fontSize: 32,
                    fontWeight: 500,
                  }}
                >
                  {(g.mean * grow).toFixed(1)}
                </div>
                <div
                  style={{
                    position: "absolute",
                    bottom: -50,
                    width: "100%",
                    textAlign: "center",
                    fontSize: 26,
                    color: c.ink2,
                  }}
                >
                  {g.label}
                </div>
              </div>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 80,
            fontFamily: serif,
            fontSize: 31,
            lineHeight: 1.5,
            color: c.ink,
            opacity: interpolate(frame, [apaAt, apaAt + 8], [0, 1], clamp),
            translate: interpolate(
              frame,
              [apaAt, apaAt + 12],
              ["0px 20px", "0px 0px"],
              { ...clamp, easing: ease },
            ),
          }}
        >
          Female students scored significantly higher,{" "}
          <span
            style={{
              fontStyle: "italic",
              whiteSpace: "nowrap",
              backgroundImage: `linear-gradient(${c.accentSoft}, ${c.accentSoft})`,
              backgroundRepeat: "no-repeat",
              backgroundSize: `${interpolate(frame, [apaAt + 10, apaAt + 30], [0, 100], { ...clamp, easing: ease })}% 100%`,
            }}
          >
            t(118) = 4.49, p &lt; .001, d = 0.82
          </span>
          .
        </div>
      </Panel>
    </AbsoluteFill>
  );
};

/* ---------- 5. Export ---------- */
const docs = [
  { ext: "DOCX", name: "Chapter 4 – Results", color: c.accent },
  { ext: "XLSX", name: "Tables & charts", color: c.success },
];

export const Export: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Caption
        step="04 · Export"
        title="Editable Word & Excel reports"
        body="Exactly the tables, charts and text you choose, ready for your manuscript."
      />
      <div
        style={{
          position: "absolute",
          right: 140,
          top: 170,
          width: 900,
          height: 740,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 70,
        }}
      >
        {docs.map((d, i) => {
          const at = 4 + i * 7;
          return (
            <div
              key={d.ext}
              style={{
                width: 340,
                height: 440,
                background: c.surface,
                border: `2px solid ${c.line}`,
                borderRadius: 8,
                boxShadow: "0 30px 60px -30px rgba(20,33,58,0.35)",
                padding: 36,
                boxSizing: "border-box",
                fontFamily: sans,
                position: "relative",
                opacity: interpolate(frame, [at, at + 6], [0, 1], clamp),
                translate: interpolate(
                  frame,
                  [at, at + 18],
                  ["0px 160px", "0px 0px"],
                  { ...clamp, easing: Easing.bezier(0.34, 1.4, 0.64, 1) },
                ),
                rotate: interpolate(
                  frame,
                  [at, at + 18],
                  [i === 0 ? "-8deg" : "8deg", i === 0 ? "-3deg" : "3deg"],
                  { ...clamp, easing: ease },
                ),
              }}
            >
              <div
                style={{
                  display: "inline-block",
                  background: d.color,
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 30,
                  padding: "8px 18px",
                  borderRadius: 4,
                }}
              >
                {d.ext}
              </div>
              <div style={{ fontSize: 30, fontWeight: 600, marginTop: 24, color: c.ink }}>
                {d.name}
              </div>
              {[0, 1, 2, 3, 4].map((l) => (
                <div
                  key={l}
                  style={{
                    height: 12,
                    marginTop: 20,
                    borderRadius: 6,
                    background: l === 2 ? c.accentSoft : c.paper2,
                    width: `${interpolate(frame, [at + 10 + l * 2, at + 22 + l * 2], [0, [100, 85, 92, 70, 60][l]], { ...clamp, easing: ease })}%`,
                  }}
                />
              ))}
              <div style={{ position: "absolute", right: -22, bottom: -22 }}>
                <Check
                  size={64}
                  color={d.color}
                  progress={interpolate(
                    frame,
                    [0.9 * fps + i * 5, 1.2 * fps + i * 5],
                    [0, 1],
                    clamp,
                  )}
                />
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* ---------- 6. Outro ---------- */
export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const steps = ["Upload", "Analyze", "Report"];
  return (
    <AbsoluteFill
      style={{ alignItems: "center", justifyContent: "center", gap: 44 }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 30,
          ...pop(frame, 0),
        }}
      >
        <Logo size={110} progress={1} />
        <div
          style={{
            fontFamily: serif,
            fontSize: 96,
            fontWeight: 600,
            color: c.ink,
          }}
        >
          StatEase Analytics
        </div>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 28,
          fontFamily: sans,
          fontSize: 44,
          color: c.ink2,
        }}
      >
        {steps.map((s, i) => (
          <React.Fragment key={s}>
            {i > 0 && (
              <span
                style={{
                  color: c.rust,
                  opacity: interpolate(frame, [6 + i * 6, 10 + i * 6], [0, 1], clamp),
                }}
              >
                →
              </span>
            )}
            <span
              style={{
                opacity: interpolate(frame, [6 + i * 6, 12 + i * 6], [0, 1], clamp),
                translate: interpolate(
                  frame,
                  [6 + i * 6, 14 + i * 6],
                  ["0px 20px", "0px 0px"],
                  { ...clamp, easing: ease },
                ),
              }}
            >
              {s}
            </span>
          </React.Fragment>
        ))}
      </div>
      <div
        style={{
          height: 4,
          background: c.rust,
          borderRadius: 2,
          width: interpolate(frame, [18, 36], [0, 520], { ...clamp, easing: ease }),
        }}
      />
    </AbsoluteFill>
  );
};
