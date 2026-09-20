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
  lip_sync: string;
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
  src,
}: {
  timing: AVTiming;
  audio?: EmbeddedAudio | null;
  src: string;
}) {
  return (
    <section className="video-report" aria-label="Audio and video consistency">
      <div className="timeline-heading">
        <div>
          <h3>Audio & video consistency</h3>
          <p>{labels[timing.status] || "Timing unavailable"}</p>
        </div>
        <span>Lip synchronization: not assessed</span>
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
