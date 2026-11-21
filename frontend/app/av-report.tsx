import AudioReport, {
  type AudioSegment,
  type AudioSummary,
} from "./audio-report";

export type TrackTiming = {
  stream_index: number;
  start_seconds: number | null;
  duration_seconds: number | null;
  source: string;
};
export type AVTiming = {
  status: string;
  video: TrackTiming;
  audio: TrackTiming | null;
  start_offset_seconds: number | null;
  end_offset_seconds: number | null;
  duration_difference_seconds: number | null;
  review_threshold_seconds: number;
};
export type LipSync = {
  status: string;
  window_start_seconds: number | null;
  window_seconds: number | null;
  frames_analyzed: number;
  face_coverage: number | null;
  best_offset_seconds: number | null;
  peak_correlation: number | null;
  zero_lag_correlation: number | null;
  max_lag_seconds: number;
  weak_correlation_threshold: number;
  offset_review_seconds: number;
};
const lipLabels: Record<string, string> = {
  no_audio: "No audio track",
  no_face: "No steady face found",
  insufficient_frames: "Too few frames",
  low_activity: "Too little mouth or audio activity",
  weak_correspondence: "Weak mouth/audio correspondence",
  offset_candidate: "Possible audio offset",
  consistent_cue: "Mouth motion follows audio",
};
export type EmbeddedAudio =
  | { error: string }
  | {
      segments: AudioSegment[];
      audio_summary: AudioSummary;
      waveform: number[];
      ai_score: number | null;
      playback_offset_seconds: number | null;
      model: { id: string; revision: string; status: string };
      notes: string[];
    };
const labels: Record<string, string> = {
  no_audio: "No audio track",
  unavailable: "Timing unavailable",
  timing_difference: "Track boundaries differ",
  boundaries_aligned: "Track boundaries align",
};
const offset = (value: number | null) =>
  value === null
    ? "Unknown"
    : `${value > 0 ? "+" : ""}${Math.round(value * 1000)} ms`;

export default function AVReport({
  timing,
  audio,
  lipSync,
  src,
}: {
  timing: AVTiming;
  audio?: EmbeddedAudio | null;
  lipSync?: LipSync;
  src: string;
}) {
  return (
    <section className="video-report" aria-label="Audio and video consistency">
      <div className="timeline-heading">
        <div>
          <h3>Audio & video consistency</h3>
          <p>{labels[timing.status] || "Timing unavailable"}</p>
        </div>
        <span>
          Lip-sync cue:{" "}
          {lipSync
            ? lipLabels[lipSync.status] || lipSync.status
            : "Not assessed"}
        </span>
      </div>
      {timing.audio && (
        <dl className="metadata">
          <div>
            <dt>Audio start relative to video</dt>
            <dd>{offset(timing.start_offset_seconds)}</dd>
          </div>
          <div>
            <dt>Audio end relative to video</dt>
            <dd>{offset(timing.end_offset_seconds)}</dd>
          </div>
          <div>
            <dt>Audio minus video duration</dt>
            <dd>{offset(timing.duration_difference_seconds)}</dd>
          </div>
        </dl>
      )}
      <p className="timeline-note">
        Positive offsets mean audio starts or ends later. Differences over{" "}
        {Math.round(timing.review_threshold_seconds * 1000)} ms are highlighted
        for review. These are track boundaries, not measured lip-sync delay.
        Edits, soundtracks, and codec padding can explain differences.
      </p>
      {lipSync?.peak_correlation != null && (
        <dl className="metadata">
          <div>
            <dt>Best mouth/audio offset</dt>
            <dd>{offset(lipSync.best_offset_seconds)}</dd>
          </div>
          <div>
            <dt>Peak / zero-lag correlation</dt>
            <dd>
              {lipSync.peak_correlation.toFixed(2)} /{" "}
              {lipSync.zero_lag_correlation?.toFixed(2) ?? "—"}
            </dd>
          </div>
          <div>
            <dt>Window / face coverage</dt>
            <dd>
              {lipSync.window_start_seconds}s +{lipSync.window_seconds}s /{" "}
              {Math.round((lipSync.face_coverage ?? 0) * 100)}%
            </dd>
          </div>
        </dl>
      )}
      {lipSync && lipSync.status !== "no_audio" && (
        <p className="timeline-note">
          Lip-sync cue: mouth-region motion of the largest OpenCV face is
          correlated with audio loudness over up to 8 seconds, at offsets up to
          ±{Math.round(lipSync.max_lag_seconds * 1000)} ms. Offsets over{" "}
          {Math.round(lipSync.offset_review_seconds * 1000)} ms or correlation
          below {lipSync.weak_correlation_threshold} are described, not scored.
          This uncalibrated heuristic is not a trained sync model; off-screen
          speakers, music, and head motion affect it, and it does not change the
          verdict.
        </p>
      )}
      {timing.audio && (
        <p className="timeline-note">
          Timing sources: video {timing.video.source.replaceAll("_", " ")},
          audio {timing.audio.source.replaceAll("_", " ")}. Only the first video
          and audio tracks are inspected.
        </p>
      )}
      {audio &&
        ("error" in audio ? (
          <p role="status" className="playback-note">
            Embedded audio unavailable: {audio.error}
          </p>
        ) : (
          <>
            <div className="embedded-score">
              <strong>Embedded speech detector</strong>
              <span>
                {audio.ai_score === null
                  ? "No score"
                  : `${Math.round(audio.ai_score * 100)}% peak segment score`}
              </span>
            </div>
            <AudioReport
              segments={audio.segments}
              summary={audio.audio_summary}
              waveform={audio.waveform}
              src={src}
              embedded
              playbackOffset={audio.playback_offset_seconds}
            />
            <details>
              <summary>Embedded audio model & limitations</summary>
              <p>
                {audio.model.id} · {audio.model.status}
              </p>
              <p>Revision: {audio.model.revision}</p>
              <ul>
                {audio.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </details>
          </>
        ))}
    </section>
  );
}
