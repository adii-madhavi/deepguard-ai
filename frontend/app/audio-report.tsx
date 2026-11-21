"use client";

import { useRef, useState } from "react";

export type AudioSegment = {
  start: number;
  end: number;
  ai_score: number | null;
  flagged: boolean;
  status: string;
  rms_dbfs: number;
  speech_ratio?: number;
};
export type AudioSummary = {
  total_segments: number;
  scored_segments: number;
  flagged_segments: number;
  skipped_segments: number;
  speech_segments?: number;
};
const time = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
const statuses: Record<string, string> = {
  near_silent: "Near-silent · not scored",
  too_short: "Too short · not scored",
  no_speech: "No voice-like activity · not scored",
  unavailable: "Model unavailable",
  failed: "Scoring failed",
};

export default function AudioReport({
  segments,
  summary,
  waveform,
  src,
  embedded = false,
  playbackOffset = 0,
}: {
  segments: AudioSegment[];
  summary: AudioSummary;
  waveform: number[];
  src: string;
  embedded?: boolean;
  playbackOffset?: number | null;
}) {
  const player = useRef<HTMLMediaElement | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [playbackError, setPlaybackError] = useState(false);
  return (
    <section
      className="video-report audio-report"
      aria-label={
        embedded ? "Embedded audio segment timeline" : "Audio segment timeline"
      }
    >
      <div className="timeline-heading">
        <div>
          <h3>
            {embedded
              ? "Speech evidence from this video"
              : "Listen closer. Inspect each segment."}
          </h3>
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
      {!src ? (
        <p className="playback-note">
          Saved report: the original file is not stored, so playback is
          unavailable.
        </p>
      ) : embedded ? (
        <video
          ref={(node) => {
            player.current = node;
          }}
          src={src}
          controls
          preload="metadata"
          aria-label="Embedded audio video player"
          onError={() => setPlaybackError(true)}
        />
      ) : (
        <audio
          ref={(node) => {
            player.current = node;
          }}
          src={src}
          controls
          preload="metadata"
          aria-label="Analysis audio player"
          onError={() => setPlaybackError(true)}
        />
      )}
      {embedded && (
        <p className="timeline-note">
          Segment times are relative to the decoded audio.{" "}
          {playbackOffset === null
            ? "Playback offset is unavailable; automatic seeking is disabled."
            : "Seeking includes the audio track's offset in the video."}
        </p>
      )}
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
                  if (
                    player.current &&
                    player.current.readyState >= 1 &&
                    playbackOffset !== null
                  ) {
                    player.current.currentTime = Math.max(
                      0,
                      segment.start + playbackOffset,
                    );
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
                <small>
                  {segment.rms_dbfs} dBFS RMS
                  {segment.speech_ratio != null &&
                    ` · ${Math.round(segment.speech_ratio * 100)}% voice-like`}
                </small>
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
        Silence, segments shorter than one second, and segments with under 10%
        voice-like frames (a heuristic check, not a trained detector) are left
        unscored.
      </p>
    </section>
  );
}
