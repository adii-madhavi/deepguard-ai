"use client";

import { useRef, useState } from "react";

export type VideoFrame = {
  timestamp: number;
  thumbnail: string;
  ai_score: number | null;
  flagged: boolean;
  faces: { x: number; y: number; width: number; height: number }[];
  visual_change_percent: number | null;
  near_duplicate_previous: boolean;
  strong_visual_change: boolean;
};
export type TemporalEvidence = {
  status: string;
  sample_count: number;
  transition_count: number;
  near_duplicate_pairs: number;
  strong_change_candidates: number;
  median_change_percent: number | null;
  max_change_percent: number | null;
  median_timestamp_gap_seconds: number | null;
  max_timestamp_gap_seconds: number | null;
  near_duplicate_threshold_percent: number;
  strong_change_threshold_percent: number;
};

export function timestamp(seconds: number) {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(2).padStart(5, "0")}`;
}

export default function VideoReport({
  frames,
  summary,
  src,
  temporal,
}: {
  frames: VideoFrame[];
  summary: {
    sampled_frames: number;
    scored_frames: number;
    flagged_frames: number;
    frames_with_faces: number;
  };
  src: string;
  temporal?: TemporalEvidence;
}) {
  const player = useRef<HTMLVideoElement>(null);
  const [selected, setSelected] = useState(0);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [playbackError, setPlaybackError] = useState(false);
  const frame = frames[selected];
  return (
    <section className="video-report" aria-label="Video frame timeline">
      <div className="timeline-heading">
        <div>
          <h3>Frame-by-frame evidence</h3>
          <p>
            Select a sample to jump to its timestamp. Only sampled frames were
            inspected.
          </p>
        </div>
        <span>
          {summary.scored_frames}/{summary.sampled_frames} scored ·{" "}
          {summary.flagged_frames} flagged
        </span>
      </div>
      {src ? (
        <video
          ref={player}
          src={src}
          controls
          preload="metadata"
          aria-label="Analysis video player"
          onError={() => setPlaybackError(true)}
        />
      ) : (
        <p className="playback-note">
          Saved report: the original file is not stored, so playback is
          unavailable.
        </p>
      )}
      {playbackError && (
        <p className="playback-note">
          Your browser cannot play this codec. The decoded frame previews and
          report remain available.
        </p>
      )}
      <div className="timeline-controls">
        <span>
          Selected: {frame ? timestamp(frame.timestamp) : "—"} ·{" "}
          {frame?.faces.length ?? 0} face detections
        </span>
        <label>
          <input
            type="checkbox"
            checked={flaggedOnly}
            onChange={(event) => setFlaggedOnly(event.target.checked)}
          />{" "}
          Flagged only
        </label>
      </div>
      <div className="frame-grid">
        {frames.map(
          (sample, index) =>
            (!flaggedOnly || sample.flagged) && (
              <button
                type="button"
                key={sample.timestamp}
                className={`frame-card ${selected === index ? "chosen" : ""} ${sample.flagged ? "flagged" : ""}`}
                aria-pressed={selected === index}
                aria-label={`Inspect frame at ${timestamp(sample.timestamp)}`}
                onClick={() => {
                  setSelected(index);
                  if (player.current && player.current.readyState >= 1) {
                    player.current.currentTime = sample.timestamp;
                    player.current.pause();
                  }
                }}
              >
                <div className="frame-image">
                  <img
                    src={sample.thumbnail}
                    alt={`Sample at ${timestamp(sample.timestamp)}`}
                  />
                  {sample.faces.map((face, faceIndex) => (
                    <span
                      key={faceIndex}
                      className="face-box"
                      aria-hidden="true"
                      style={{
                        left: `${face.x * 100}%`,
                        top: `${face.y * 100}%`,
                        width: `${face.width * 100}%`,
                        height: `${face.height * 100}%`,
                      }}
                    />
                  ))}
                </div>
                <span className="frame-caption">
                  <strong>{timestamp(sample.timestamp)}</strong>
                  <span>
                    {sample.ai_score === null
                      ? "Unscored"
                      : `${Math.round(sample.ai_score * 100)}%`}
                  </span>
                </span>
                <small>
                  {sample.flagged
                    ? "Flagged for review"
                    : sample.ai_score === null
                      ? "Model unavailable"
                      : "Below review threshold"}
                </small>
                {sample.visual_change_percent !== null && (
                  <small className="visual-change">
                    {sample.near_duplicate_previous
                      ? "Near-duplicate sample"
                      : sample.strong_visual_change
                        ? "Strong visual change"
                        : `${sample.visual_change_percent}% visual change`}
                  </small>
                )}
              </button>
            ),
        )}
      </div>
      {temporal && (
        <section
          className="temporal-evidence"
          aria-label="Temporal consistency evidence"
        >
          <div className="timeline-heading">
            <div>
              <h3>Sampled temporal evidence</h3>
              <p>Pixel changes between consecutive sampled frames.</p>
            </div>
            <span>
              {temporal.near_duplicate_pairs} near-duplicate ·{" "}
              {temporal.strong_change_candidates} strong change
            </span>
          </div>
          <div className="temporal-metrics">
            <div>
              <span>Median change</span>
              <strong>{temporal.median_change_percent ?? "—"}%</strong>
            </div>
            <div>
              <span>Maximum change</span>
              <strong>{temporal.max_change_percent ?? "—"}%</strong>
            </div>
            <div>
              <span>Largest sample gap</span>
              <strong>{temporal.max_timestamp_gap_seconds ?? "—"}s</strong>
            </div>
          </div>
          <p className="timeline-note">
            Near-duplicate means at or below{" "}
            {temporal.near_duplicate_threshold_percent}% grayscale pixel change;
            strong change means at or above{" "}
            {temporal.strong_change_threshold_percent}%. These are scene-change
            and repetition cues, not proof of temporal manipulation. Only{" "}
            {temporal.sample_count} frames were sampled.
          </p>
        </section>
      )}
      {flaggedOnly && !summary.flagged_frames && (
        <p className="playback-note">
          No sampled frames crossed the review threshold. This does not
          establish authenticity.
        </p>
      )}
      <p className="timeline-note">
        Face boxes are basic frontal-face detections, not manipulation findings.
        A frame is flagged at an uncalibrated score of 80% or above.
      </p>
    </section>
  );
}
