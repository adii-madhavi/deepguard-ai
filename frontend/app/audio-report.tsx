"use client";

import { useRef, useState } from "react";

export type AudioSegment = {
  start: number;
  end: number;
  ai_score: number | null;
  flagged: boolean;
  status: string;
  rms_dbfs: number;
};
export type AudioSummary = {
  total_segments: number;
  scored_segments: number;
  flagged_segments: number;
  skipped_segments: number;
};
const time = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
const statuses: Record<string, string> = {
  near_silent: "Near-silent · not scored",
  too_short: "Too short · not scored",
  unavailable: "Model unavailable",
  failed: "Scoring failed",
};

export default function AudioReport({
  segments,
  summary,
  waveform,
  src,
}: {
  segments: AudioSegment[];
  summary: AudioSummary;
  waveform: number[];
  src: string;
}) {
  const player = useRef<HTMLAudioElement>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [playbackError, setPlaybackError] = useState(false);
  return (
    <section
      className="video-report audio-report"
      aria-label="Audio segment timeline"
    >
      <div className="timeline-heading">
        <div>
          <h3>Listen closer. Inspect each segment.</h3>
          <p>Six-second segments with experimental synthetic-speech scores.</p>
        </div>
        <span>
          {summary.scored_segments}/{summary.total_segments} scored ·{" "}
          {summary.flagged_segments} flagged
        </span>
      </div>
      <svg
        viewBox="0 0 800 80"
        role="img"
        aria-label="Peak amplitude waveform of the resampled audio"
        className="audio-waveform"
      >
        <line x1="0" x2="800" y1="40" y2="40" stroke="#d5e6dd" />
        {waveform.map((value, index) => (
          <rect
            key={index}
            x={(index * 800) / waveform.length}
            y={40 - Math.max(1, value * 38)}
            width={Math.max(1, 800 / waveform.length - 2)}
            height={Math.max(2, value * 76)}
            rx="1"
            fill="#147d70"
          />
        ))}
      </svg>
      <audio
        ref={player}
        src={src}
        controls
        preload="metadata"
        aria-label="Analysis audio player"
        onError={() => setPlaybackError(true)}
      />
      {playbackError && (
        <p className="playback-note">
          Your browser cannot play this format. Segment scores and the
          downloadable report remain available.
        </p>
      )}
      <div className="timeline-controls">
        <span>
          {selected === null
            ? "Select a segment to seek in the recording"
            : `Selected: ${time(segments[selected].start)} – ${time(segments[selected].end)}`}
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
      <div className="audio-segments">
        {segments.map(
          (segment, index) =>
            (!flaggedOnly || segment.flagged) && (
              <button
                key={segment.start}
                type="button"
                className={`audio-segment ${selected === index ? "chosen" : ""} ${segment.flagged ? "flagged" : ""}`}
                aria-pressed={selected === index}
                aria-label={`Inspect audio segment at ${time(segment.start)}`}
                onClick={() => {
                  setSelected(index);
                  if (player.current && player.current.readyState >= 1) {
                    player.current.currentTime = segment.start;
                    player.current.pause();
                  }
                }}
              >
                <span className="frame-caption">
                  <strong>
                    {time(segment.start)} – {time(segment.end)}
                  </strong>
                  <span>
                    {segment.ai_score === null
                      ? "—"
                      : `${Math.round(segment.ai_score * 100)}%`}
                  </span>
                </span>
                <div className="meter">
                  <span
                    style={{ width: `${(segment.ai_score ?? 0) * 100}%` }}
                  />
                </div>
                <small>
                  {segment.status === "scored"
                    ? segment.flagged
                      ? "Flagged for review"
                      : "Below review threshold"
                    : statuses[segment.status] || segment.status}
                </small>
                <small>{segment.rms_dbfs} dBFS RMS</small>
              </button>
            ),
        )}
      </div>
      {flaggedOnly && summary.flagged_segments === 0 && (
        <p className="playback-note">
          No segments crossed the review threshold. Missing and low scores do
          not establish authenticity.
        </p>
      )}
      <p className="timeline-note">
        For speech recordings. Music and noise may produce unreliable scores.
        Silence and segments shorter than one second are left unscored.
      </p>
    </section>
  );
}
