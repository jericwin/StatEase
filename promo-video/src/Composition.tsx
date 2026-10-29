import React from "react";
import {
  AbsoluteFill,
  Composition,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SceneFrame } from "./parts";
import { Export, Intro, Outro, Results, Suggest, Upload } from "./scenes";
import { c, clamp } from "./theme";

export const MyComposition = () => {
  return (
    <Composition
      id="StatEasePromo"
      component={StatEasePromo}
      durationInFrames={450}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

// Faint ruled-paper grid that drifts slowly behind every scene.
const Background: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        background: c.paper,
        backgroundImage: `linear-gradient(${c.line}55 2px, transparent 2px), linear-gradient(90deg, ${c.line}55 2px, transparent 2px)`,
        backgroundSize: "80px 80px",
        backgroundPosition: `${-frame * 0.4}px ${-frame * 0.4}px`,
      }}
    />
  );
};

const Progress: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        bottom: 0,
        height: 8,
        background: c.rust,
        width: `${interpolate(frame, [0, durationInFrames], [0, 100], clamp)}%`,
      }}
    />
  );
};

export const StatEasePromo: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Background />
      <Sequence name="Intro" from={0} durationInFrames={2.5 * fps}>
        <SceneFrame duration={2.5 * fps}>
          <Intro />
        </SceneFrame>
      </Sequence>
      <Sequence name="Upload" from={2.5 * fps} durationInFrames={3 * fps}>
        <SceneFrame duration={3 * fps}>
          <Upload />
        </SceneFrame>
      </Sequence>
      <Sequence name="Suggest" from={5.5 * fps} durationInFrames={3 * fps}>
        <SceneFrame duration={3 * fps}>
          <Suggest />
        </SceneFrame>
      </Sequence>
      <Sequence name="Results" from={8.5 * fps} durationInFrames={3 * fps}>
        <SceneFrame duration={3 * fps}>
          <Results />
        </SceneFrame>
      </Sequence>
      <Sequence name="Export" from={11.5 * fps} durationInFrames={2 * fps}>
        <SceneFrame duration={2 * fps}>
          <Export />
        </SceneFrame>
      </Sequence>
      <Sequence name="Outro" from={13.5 * fps} durationInFrames={1.5 * fps}>
        <Outro />
      </Sequence>
      <Progress />
    </AbsoluteFill>
  );
};
