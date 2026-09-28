"use client";

import { useEffect, useRef, useState } from "react";
import VideoReport, {
  type VideoFrame,
  type TemporalEvidence,
} from "./video-report";
import AVReport, { type AVTiming, type EmbeddedAudio } from "./av-report";
import AudioReport, {
  type AudioSegment,
  type AudioSummary,
} from "./audio-report";
import {
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  FileImage,
  Fingerprint,
  Image as ImageIcon,
  Layers,
  LoaderCircle,
  LockKeyhole,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Upload,
  Video,
  X,
} from "lucide-react";

type Report = {
  av_timing?: AVTiming;
  embedded_audio?: EmbeddedAudio | null;
  media_type?: "image" | "video" | "audio";
  segments?: AudioSegment[];
  audio_summary?: AudioSummary;
  waveform?: number[];
  frames?: VideoFrame[];
  temporal?: TemporalEvidence;
  summary?: {
    sampled_frames: number;
    scored_frames: number;
    flagged_frames: number;
    frames_with_faces: number;
  };
  id: string;
  created_at: string;
  sha256: string;
  verdict: string;
  ai_score: number | null;
  model: { id: string; revision: string; status: string };
  metadata: {
    format: string;
    width: number;
    height: number;
    color_mode: string;
    size_bytes: number;
    exif_fields: number;
    software: string | null;
    duration_seconds?: number;
    fps?: number | null;
    codec?: string;
    sample_rate?: number;
    channels?: number;
  };
  notes: string[];
  observations: { title: string; value: string; detail: string }[];
};
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const verdicts: Record<string, string> = {
  likely_ai_generated: "Likely AI-generated",
  likely_natural: "Likely natural",
  inconclusive: "Inconclusive",
  review_recommended: "Flagged frames · review recommended",
  audio_review_recommended: "Flagged audio · review recommended",
  av_review_recommended: "Media signals · review recommended",
};

export default function Home() {
  const [mode, setMode] = useState<"image" | "video" | "audio">("image");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [visionModelStatus, setVisionModelStatus] = useState("connecting");
  const [audioModelStatus, setAudioModelStatus] = useState("connecting");
  const modelStatus = mode === "audio" ? audioModelStatus : visionModelStatus;
  const input = useRef<HTMLInputElement>(null);
  const result = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    const controller = new AbortController();
    async function health() {
      try {
        const response = await fetch(`${API}/health`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        setVisionModelStatus(data.model_status);
        setAudioModelStatus(data.audio_model_status ?? "unavailable");
      } catch {
        if (!controller.signal.aborted) {
          setVisionModelStatus("offline");
          setAudioModelStatus("offline");
        }
      }
    }
    void health();
    const timer = setInterval(health, 10000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  function choose(candidate?: File) {
    if (busy || !candidate) return;
    setError("");
    setReport(null);
    const allowed =
      mode === "image"
        ? ["image/jpeg", "image/png", "image/webp"]
        : mode === "video"
          ? ["video/mp4", "video/quicktime", "video/webm"]
          : [
              "audio/wav",
              "audio/x-wav",
              "audio/wave",
              "audio/mpeg",
              "audio/mp3",
              "audio/flac",
              "audio/x-flac",
              "audio/mp4",
              "audio/x-m4a",
            ];
    if (
      !allowed.includes(candidate.type) &&
      !(
        mode !== "image" &&
        !candidate.type &&
        (mode === "video"
          ? /\.(mp4|mov|webm)$/i
          : /\.(wav|mp3|flac|m4a)$/i
        ).test(candidate.name)
      )
    ) {
      setFile(null);
      setError(
        mode === "image"
          ? "Please select a JPEG, PNG, or WebP image."
          : mode === "video"
            ? "Please select an MP4, MOV, or WebM video."
            : "Please select a WAV, MP3, FLAC, or M4A audio file.",
      );
      return;
    }
    if (
      candidate.size >
      (mode === "image" ? 10 : mode === "video" ? 100 : 50) * 1024 * 1024
    ) {
      setFile(null);
      setError(
        mode === "image"
          ? "This image exceeds the 10 MB limit."
          : mode === "video"
            ? "This video exceeds the 100 MB limit."
            : "This audio exceeds the 50 MB limit.",
      );
      return;
    }
    setFile(candidate);
  }

  async function analyze() {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const response = await fetch(
        `${API}/analyze${mode === "image" ? "" : `/${mode}`}`,
        {
          method: "POST",
          headers: { "Content-Type": file.type },
          body: file,
          signal: AbortSignal.timeout(mode === "image" ? 120000 : 240000),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Analysis failed. Please try again.",
        );
      setReport(data);
      setTimeout(
        () =>
          result.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          }),
        100,
      );
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "Cannot reach the analysis service. Start the backend and try again."
          : e instanceof Error
            ? e.message
            : "Something went wrong.",
      );
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `deepguard-${report.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const score =
    report?.ai_score != null ? Math.round(report.ai_score * 100) : null;

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="DeepGuard AI home">
          <span className="brand-icon">
            <ShieldCheck size={23} />
          </span>
          <span>
            deepguard<span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <a className="nav-item active" href="#analyzer">
            <ScanLine size={18} /> Media analyzer <ChevronRight size={15} />
          </a>
          <a className="nav-item" href="#methodology">
            <Layers size={18} /> How it works
          </a>
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-icon">
            <LockKeyhole size={19} />
          </div>
          <strong>Your media stays yours.</strong>
          <p>
            Images stay in memory. Video and audio use temporary files that are
            deleted after analysis.
          </p>
          <span className="version">IMAGE · VIDEO · AUDIO · v0.4</span>
        </div>
      </aside>

      <div className="main-wrap">
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} />
            <span>Media analyzer</span>
          </div>
          <span className="service">
            <i className={modelStatus === "ready" ? "online" : ""} />
            {modelStatus === "ready"
              ? "Detector ready"
              : modelStatus === "loading"
                ? "Detector loading"
                : modelStatus === "offline"
                  ? "Service offline"
                  : modelStatus === "connecting"
                    ? "Connecting"
                    : "Metadata mode"}
          </span>
        </header>
        <main>
          <section className="intro">
            <div className="eyebrow">
              <span /> MEDIA INTELLIGENCE
            </div>
            <h1>
              A closer look.
              <br />
              <span>A clearer picture.</span>
            </h1>
            <p>
              Go beyond what you see. Inspect your media for signs of
              <br className="desktop-break" /> AI generation with transparent,
              evidence-led analysis.
            </p>
            <div className="intro-mark" aria-hidden="true">
              <Fingerprint />
            </div>
          </section>

          <section
            className="analyzer-card"
            id="analyzer"
            aria-label="Upload media"
          >
            <div className="card-heading">
              <div>
                <h2>Analyze your media</h2>
                <p>Start with a file. Get a better understanding.</p>
              </div>
              <span className="private-badge">
                <LockKeyhole size={12} /> Private by design
              </span>
            </div>
            <div className="media-tabs">
              <button
                type="button"
                className={mode === "image" ? "selected" : ""}
                aria-pressed={mode === "image"}
                disabled={busy}
                onClick={() => {
                  setMode("image");
                  setFile(null);
                  setReport(null);
                  setError("");
                }}
              >
                <ImageIcon size={17} /> Image
              </button>
              <button
                type="button"
                className={mode === "video" ? "selected" : ""}
                aria-pressed={mode === "video"}
                disabled={busy}
                onClick={() => {
                  setMode("video");
                  setFile(null);
                  setReport(null);
                  setError("");
                }}
              >
                <Video size={17} /> Video
              </button>
              <button
                type="button"
                className={mode === "audio" ? "selected" : ""}
                aria-pressed={mode === "audio"}
                disabled={busy}
                onClick={() => {
                  setMode("audio");
                  setFile(null);
                  setReport(null);
                  setError("");
                }}
              >
                <AudioLines size={17} /> Audio
              </button>
            </div>
            <div
              className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                if (!busy) setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                choose(e.dataTransfer.files[0]);
              }}
            >
              <input
                ref={input}
                type="file"
                aria-label={
                  mode === "image"
                    ? "Select an image"
                    : mode === "video"
                      ? "Select a video"
                      : "Select an audio file"
                }
                accept={
                  mode === "image"
                    ? "image/jpeg,image/png,image/webp"
                    : mode === "video"
                      ? "video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                      : "audio/wav,audio/mpeg,audio/flac,audio/mp4,.wav,.mp3,.flac,.m4a"
                }
                disabled={busy}
                className="sr-only"
                onChange={(e) => {
                  choose(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              {file ? (
                <div className="file-preview">
                  {preview &&
                    (mode === "image" ? (
                      <img src={preview} alt="Selected image preview" />
                    ) : mode === "audio" ? (
                      <audio
                        src={preview}
                        controls
                        preload="metadata"
                        aria-label="Selected audio preview"
                      />
                    ) : (
                      <video
                        src={preview}
                        controls
                        preload="metadata"
                        aria-label="Selected video preview"
                      />
                    ))}
                  <div>
                    <strong>{file.name}</strong>
                    <p>
                      {(file.size / 1024 / 1024).toFixed(2)} MB · Ready to
                      inspect
                    </p>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => input.current?.click()}
                    >
                      Choose another {mode}
                    </button>
                  </div>
                  <button
                    className="remove"
                    aria-label={`Remove selected ${mode}`}
                    disabled={busy}
                    onClick={() => {
                      setFile(null);
                      setReport(null);
                      setError("");
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              ) : (
                <>
                  <div className="upload-icon">
                    <Upload size={26} />
                  </div>
                  <h3>Drop your {mode} here</h3>
                  <p>
                    or{" "}
                    <button
                      className="text-button"
                      onClick={() => input.current?.click()}
                    >
                      browse files
                    </button>{" "}
                    from your device
                  </p>
                  <span className="file-types">
                    {mode === "image" ? (
                      <>
                        JPG, PNG, WEBP <b>·</b> Up to 10 MB <b>·</b> 20
                        megapixels
                      </>
                    ) : (
                      <>
                        {mode === "video"
                          ? "MP4, MOV, WEBM · Up to 100 MB · 2 minutes / 4K"
                          : "WAV, MP3, FLAC, M4A · Up to 50 MB · 1–120 seconds"}
                      </>
                    )}
                  </span>
                </>
              )}
            </div>
            <div aria-live="polite">
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
            </div>
            <div className="upload-footer">
              <span>
                <ShieldCheck size={15} />{" "}
                {mode === "image"
                  ? "Your image is processed in memory"
                  : "Temporary media files are deleted after analysis"}
              </span>
              <button
                className="primary-button"
                disabled={!file || busy}
                onClick={analyze}
              >
                {busy ? (
                  <>
                    <LoaderCircle size={17} className="spin" /> Analyzing {mode}
                    …
                  </>
                ) : (
                  <>
                    <ScanLine size={17} /> Analyze {mode}{" "}
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </section>

          {report && (
            <section
              ref={result}
              className="results"
              aria-label="Analysis results"
              aria-live="polite"
            >
              <div className="result-heading">
                <div>
                  <div className="eyebrow">ANALYSIS COMPLETE</div>
                  <h2>{verdicts[report.verdict] || "Inconclusive"}</h2>
                </div>
                <button className="secondary-button" onClick={download}>
                  <ArrowDownToLine size={16} /> Export report
                </button>
              </div>
              <div className="result-grid">
                <div className="score-card">
                  <span>
                    {report.media_type === "video"
                      ? "Highest sampled-frame score"
                      : report.media_type === "audio"
                        ? "Highest audio-segment score"
                        : "AI-generation model score"}
                  </span>
                  <strong>{score === null ? "—" : `${score}%`}</strong>
                  <div className="meter">
                    <span style={{ width: `${score ?? 0}%` }} />
                  </div>
                  <p>
                    {score === null
                      ? "No detector score available for this media."
                      : report.media_type === "video"
                        ? "Peak image-detector output across sampled frames. This does not measure whole-video authenticity."
                        : report.media_type === "audio"
                          ? "Peak synthetic-speech score across analyzed segments. Experimental and uncalibrated; not proof of origin."
                          : "Uncalibrated model output. This is not a confidence percentage or proof of origin."}
                  </p>
                </div>
                <dl className="metadata">
                  <div>
                    <dt>
                      {report.media_type === "audio"
                        ? "Sample rate / channels"
                        : "Dimensions"}
                    </dt>
                    <dd>
                      {report.media_type === "audio"
                        ? `${report.metadata.sample_rate} Hz / ${report.metadata.channels}`
                        : `${report.metadata.width} × ${report.metadata.height}`}
                    </dd>
                  </div>
                  <div>
                    <dt>
                      {report.media_type === "audio"
                        ? "Format / codec"
                        : "Format / color"}
                    </dt>
                    <dd>
                      {report.metadata.format} /{" "}
                      {report.media_type === "audio"
                        ? report.metadata.codec
                        : report.metadata.color_mode}
                    </dd>
                  </div>
                  <div>
                    <dt>File size</dt>
                    <dd>{(report.metadata.size_bytes / 1024).toFixed(1)} KB</dd>
                  </div>
                  <div>
                    <dt>
                      {report.media_type === "video"
                        ? "Duration / frame rate"
                        : report.media_type === "audio"
                          ? "Duration"
                          : "Embedded software"}
                    </dt>
                    <dd>
                      {report.media_type === "video"
                        ? `${report.metadata.duration_seconds}s / ${report.metadata.fps ?? "Unknown"} fps`
                        : report.media_type === "audio"
                          ? `${report.metadata.duration_seconds} seconds`
                          : report.metadata.software || "Not recorded"}
                    </dd>
                  </div>
                </dl>
              </div>
              {report.frames && report.summary && (
                <VideoReport
                  frames={report.frames}
                  summary={report.summary}
                  src={preview}
                  temporal={report.temporal}
                />
              )}
              {report.segments && report.audio_summary && report.waveform && (
                <AudioReport
                  segments={report.segments}
                  summary={report.audio_summary}
                  waveform={report.waveform}
                  src={preview}
                />
              )}
              {report.av_timing && (
                <AVReport
                  timing={report.av_timing}
                  audio={report.embedded_audio}
                  src={preview}
                />
              )}
              <div className="observations">
                {report.observations.map((item) => (
                  <div key={item.title}>
                    <Check size={16} />
                    <div>
                      <h3>
                        {item.title}
                        <span>{item.value}</span>
                      </h3>
                      <p>{item.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
              <details>
                <summary>Model, limitations & file fingerprint</summary>
                <p>
                  Model: {report.model.id} · {report.model.status}
                </p>
                <p>Revision: {report.model.revision}</p>
                <p className="hash">SHA-256: {report.sha256}</p>
                <ul>
                  {report.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </details>
            </section>
          )}

          <section className="methodology" id="methodology">
            <div className="section-label">
              A LITTLE CONTEXT. A LOT MORE CLARITY.
            </div>
            <div className="feature-grid">
              <article>
                <div className="feature-icon">
                  <Sparkles size={20} />
                </div>
                <h3>Look for AI signals</h3>
                <p>
                  Dedicated image and speech models examine patterns associated
                  with generated media.
                </p>
              </article>
              <article>
                <div className="feature-icon">
                  <FileImage size={20} />
                </div>
                <h3>Inspect the details</h3>
                <p>
                  Explore media properties, embedded metadata, and a unique file
                  fingerprint.
                </p>
              </article>
              <article>
                <div className="feature-icon">
                  <Fingerprint size={20} />
                </div>
                <h3>Understand the evidence</h3>
                <p>
                  Get a transparent report with model scores, observations, and
                  their limitations.
                </p>
              </article>
            </div>
          </section>
          <div className="context-note">
            <ShieldCheck size={19} />
            <p>
              <strong>A signal, not a final verdict.</strong> Detection is
              imperfect. Use these results alongside source verification and
              human judgment.
            </p>
          </div>
          <footer>
            <span>© {new Date().getFullYear()} DeepGuard AI</span>
            <span>Built for a more transparent digital world.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
