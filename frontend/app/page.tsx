"use client";

import { useEffect, useRef, useState } from "react";
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
  };
  notes: string[];
  observations: { title: string; value: string; detail: string }[];
};
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const verdicts: Record<string, string> = {
  likely_ai_generated: "Likely AI-generated",
  likely_natural: "Likely natural",
  inconclusive: "Inconclusive",
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [modelStatus, setModelStatus] = useState("connecting");
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
        setModelStatus(data.model_status);
      } catch {
        if (!controller.signal.aborted) setModelStatus("offline");
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
    if (!["image/jpeg", "image/png", "image/webp"].includes(candidate.type)) {
      setFile(null);
      setError("Please select a JPEG, PNG, or WebP image.");
      return;
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setFile(null);
      setError("This image exceeds the 10 MB limit.");
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
      const response = await fetch(`${API}/analyze`, {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
        signal: AbortSignal.timeout(120000),
      });
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
          <p>Images are processed in memory and are not saved by DeepGuard.</p>
          <span className="version">IMAGE ANALYSIS · v0.1</span>
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
              Go beyond what you see. Inspect your images for signs of
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
              <span className="selected">
                <ImageIcon size={17} /> Image
              </span>
              <span aria-disabled="true">
                <Video size={17} /> Video <small>SOON</small>
              </span>
              <span aria-disabled="true">
                <AudioLines size={17} /> Audio <small>SOON</small>
              </span>
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
                aria-label="Select an image"
                accept="image/jpeg,image/png,image/webp"
                disabled={busy}
                className="sr-only"
                onChange={(e) => {
                  choose(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              {file ? (
                <div className="file-preview">
                  {preview && (
                    <img src={preview} alt="Selected image preview" />
                  )}
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
                      Choose another image
                    </button>
                  </div>
                  <button
                    className="remove"
                    aria-label="Remove selected image"
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
                  <h3>Drop your image here</h3>
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
                    JPG, PNG, WEBP <b>·</b> Up to 10 MB <b>·</b> 20 megapixels
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
                <ShieldCheck size={15} /> Your file is never stored by this app
              </span>
              <button
                className="primary-button"
                disabled={!file || busy}
                onClick={analyze}
              >
                {busy ? (
                  <>
                    <LoaderCircle size={17} className="spin" /> Analyzing image…
                  </>
                ) : (
                  <>
                    <ScanLine size={17} /> Analyze image{" "}
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
                  <span>AI-generation model score</span>
                  <strong>{score === null ? "—" : `${score}%`}</strong>
                  <div className="meter">
                    <span style={{ width: `${score ?? 0}%` }} />
                  </div>
                  <p>
                    {score === null
                      ? "No detector score available for this image."
                      : "Uncalibrated model output. This is not a confidence percentage or proof of origin."}
                  </p>
                </div>
                <dl className="metadata">
                  <div>
                    <dt>Dimensions</dt>
                    <dd>
                      {report.metadata.width} × {report.metadata.height}
                    </dd>
                  </div>
                  <div>
                    <dt>Format / color</dt>
                    <dd>
                      {report.metadata.format} / {report.metadata.color_mode}
                    </dd>
                  </div>
                  <div>
                    <dt>File size</dt>
                    <dd>{(report.metadata.size_bytes / 1024).toFixed(1)} KB</dd>
                  </div>
                  <div>
                    <dt>Embedded software</dt>
                    <dd>{report.metadata.software || "Not recorded"}</dd>
                  </div>
                </dl>
              </div>
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
                  A pretrained vision model examines visual patterns associated
                  with generated images.
                </p>
              </article>
              <article>
                <div className="feature-icon">
                  <FileImage size={20} />
                </div>
                <h3>Inspect the details</h3>
                <p>
                  Explore image properties, embedded metadata, and a unique file
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
