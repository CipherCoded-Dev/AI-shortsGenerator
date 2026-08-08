"use client";

import { useState, useEffect, useRef } from "react";
import { Download, Loader2, AlertCircle, CheckCircle2, Clapperboard, Layers, Trash2, Subtitles } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type RenderMode = "crop" | "fit";

interface RenderedClip {
  clip_id: string;
  filename: string;
  download_url: string;
  segment: {
    start_time: number;
    end_time: number;
    clip_title?: string;
    hook_reason?: string;
    virality_score?: number;
  };
  renderMode?: RenderMode;
  subtitleEnabled?: boolean;
}

interface JobStatusResponse {
  job_id: string;
  status: "queued" | "downloading" | "transcribing" | "analyzing" | "rendering" | "completed" | "failed";
  message: string;
  progress_percent: number;
  video_title?: string;
  clips?: RenderedClip[];
  error?: string;
}

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const MODE_LABELS: Record<RenderMode, string> = {
  crop: "Full Crop (9:16)",
  fit: "Fit (Black Bars)",
};

export default function Home() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [lastSubmittedUrl, setLastSubmittedUrl] = useState("");
  const [renderMode, setRenderMode] = useState<RenderMode>("crop");
  const activeRenderModeRef = useRef<RenderMode>("crop");
  const [subtitleEnabled, setSubtitleEnabled] = useState(true);
  const activeSubtitleRef = useRef(true);

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobData, setJobData] = useState<JobStatusResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Accumulated gallery clips across multiple runs
  const [accumulatedClips, setAccumulatedClips] = useState<RenderedClip[]>([]);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/status/${jobId}`);

        if (res.status === 404) {
          if (!cancelled) {
            setJobData({
              job_id: jobId,
              status: "failed",
              message: "Job not found on server.",
              progress_percent: 0,
              error: "The backend was restarted, so this job is no longer tracked. Please submit a new video.",
            });
            setIsSubmitting(false);
          }
          clearInterval(interval);
          return;
        }

        if (!res.ok) {
          throw new Error(`Server error (${res.status})`);
        }

        const data: JobStatusResponse = await res.json();

        if (data && data.status) {
          if (!cancelled) setJobData(data);

          if (data.status === "completed") {
            clearInterval(interval);
            setIsSubmitting(false);

            // Merge new clips into accumulated state using active submitted mode
            if (data.clips && data.clips.length > 0) {
              const currentMode = activeRenderModeRef.current;
              const currentSubtitle = activeSubtitleRef.current;
              const newTaggedClips = data.clips.map((clip) => ({
                ...clip,
                renderMode: currentMode,
                subtitleEnabled: currentSubtitle,
              }));

              setAccumulatedClips((prev) => {
                const existingKeys = new Set(prev.map((c) => `${c.clip_id}_${c.renderMode}_${c.subtitleEnabled}`));
                const filteredNew = newTaggedClips.filter(
                  (c) => !existingKeys.has(`${c.clip_id}_${c.renderMode}_${c.subtitleEnabled}`)
                );
                return [...prev, ...filteredNew];
              });
            }
          } else if (data.status === "failed") {
            clearInterval(interval);
            setIsSubmitting(false);
          }
        }
      } catch (err) {
        console.error("Failed to poll status:", err);
        if (!cancelled) {
          setJobData({
            job_id: jobId,
            status: "failed",
            message: "Unable to reach the backend.",
            progress_percent: 0,
            error: `Failed to poll job status: ${err instanceof Error ? err.message : err}. Is the backend running on ${API_BASE}?`,
          });
          setIsSubmitting(false);
        }
        clearInterval(interval);
      }
    };

    const interval = setInterval(poll, 2000);
    poll();

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!youtubeUrl.trim()) return;

    // Track mode submitted for this job run
    activeRenderModeRef.current = renderMode;
    activeSubtitleRef.current = subtitleEnabled;

    // If a brand NEW video URL is submitted, clear previous gallery
    if (youtubeUrl.trim() !== lastSubmittedUrl) {
      setAccumulatedClips([]);
      setLastSubmittedUrl(youtubeUrl.trim());
    }

    setIsSubmitting(true);
    setJobData(null);
    setJobId(null);

    try {
      const res = await fetch(`${API_BASE}/api/process-video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          youtube_url: youtubeUrl,
          url: youtubeUrl,
          render_mode: renderMode,
          subtitle_enabled: subtitleEnabled,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server error (${res.status})`);
      }

      const data = await res.json();
      if (!data.job_id) {
        throw new Error("No job_id returned by server.");
      }
      setJobId(data.job_id);
    } catch (err: any) {
      setIsSubmitting(false);
      alert(`Failed to start video processing: ${err.message}`);
    }
  };

  const handleClearGallery = () => {
    setAccumulatedClips([]);
    setJobData(null);
  };

  return (
    <main className="relative min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6 overflow-hidden">
      {/* signature blob */}
      <div
        aria-hidden
        className="pointer-events-none absolute top-[-10%] left-1/2 -translate-x-1/2 w-[520px] h-[420px] opacity-40 blur-[90px]"
        style={{
          background:
            "radial-gradient(circle at 30% 30%, var(--accent-violet), transparent 60%), radial-gradient(circle at 70% 40%, var(--accent-blue), transparent 55%), radial-gradient(circle at 50% 75%, var(--accent-pink), transparent 60%)",
        }}
      />

      <div className="relative w-full max-w-3xl space-y-10">

        {/* Header */}
        <div className="text-center space-y-4">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-secondary">
            youtube → shorts
          </p>
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-foreground">
            Turn YouTube videos into <span className="text-gradient">shorts</span>
          </h1>
          <p className="text-text-secondary text-base">
            Paste a link. Choose framing layout, caption style, and render clips ready to post.
          </p>
        </div>

        {/* Form Container */}
        <div className="bg-panel border border-border rounded-lg p-4 space-y-4 shadow-xl">
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
            <input
              type="url"
              required
              placeholder="https://youtube.com/watch?v=..."
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              disabled={isSubmitting}
              className="flex-1 bg-background border border-border focus:border-[var(--accent-blue)] rounded-md px-4 py-3 font-mono text-sm text-foreground placeholder-text-secondary outline-none transition disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[var(--accent-blue)]/40"
            />
            <button
              type="submit"
              disabled={isSubmitting || !youtubeUrl.trim()}
              className="bg-gradient-accent disabled:bg-panel disabled:bg-none disabled:text-text-secondary text-white font-medium px-6 py-3 rounded-md transition flex items-center justify-center gap-2 hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--accent-blue)]/40 focus-visible:outline-none shrink-0"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing
                </>
              ) : (
                <>
                  <Clapperboard className="w-4 h-4" />
                  Generate shorts
                </>
              )}
            </button>
          </form>

          {/* Framing Mode Selector */}
          <div className="pt-3 border-t border-border space-y-2 font-mono text-xs">
            <div className="flex items-center gap-1.5 text-text-secondary text-[11px] uppercase tracking-wider">
              <Layers className="w-3 h-3 text-[var(--accent-blue)]" />
              <span>Framing Mode</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setRenderMode("crop")}
                disabled={isSubmitting}
                className={`py-2 px-3 rounded-md border text-center transition-all ${
                  renderMode === "crop"
                    ? "border-[var(--accent-blue)] bg-[var(--accent-blue)]/10 text-white font-semibold"
                    : "border-border bg-background/50 text-text-secondary hover:text-foreground"
                }`}
              >
                Full Crop (9:16)
              </button>

              <button
                type="button"
                onClick={() => setRenderMode("fit")}
                disabled={isSubmitting}
                className={`py-2 px-3 rounded-md border text-center transition-all ${
                  renderMode === "fit"
                    ? "border-[var(--accent-blue)] bg-[var(--accent-blue)]/10 text-white font-semibold"
                    : "border-border bg-background/50 text-text-secondary hover:text-foreground"
                }`}
              >
                Fit (Black Bars)
              </button>
            </div>
          </div>

          {/* Subtitle Toggle */}
          <div className="pt-3 border-t border-border space-y-2 font-mono text-xs">
            <div className="flex items-center gap-1.5 text-text-secondary text-[11px] uppercase tracking-wider">
              <Subtitles className="w-3 h-3 text-[var(--accent-blue)]" />
              <span>Burned-In Captions</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setSubtitleEnabled(true)}
                disabled={isSubmitting}
                className={`py-2 px-3 rounded-md border text-center transition-all ${
                  subtitleEnabled
                    ? "border-[var(--accent-blue)] bg-[var(--accent-blue)]/10 text-white font-semibold"
                    : "border-border bg-background/50 text-text-secondary hover:text-foreground"
                }`}
              >
                On
              </button>

              <button
                type="button"
                onClick={() => setSubtitleEnabled(false)}
                disabled={isSubmitting}
                className={`py-2 px-3 rounded-md border text-center transition-all ${
                  !subtitleEnabled
                    ? "border-[var(--accent-blue)] bg-[var(--accent-blue)]/10 text-white font-semibold"
                    : "border-border bg-background/50 text-text-secondary hover:text-foreground"
                }`}
              >
                Off
              </button>
            </div>
          </div>
        </div>

        {/* Active Progress */}
        {jobData && jobData.status !== "completed" && jobData.status !== "failed" && (
          <div className="bg-panel border border-border rounded-lg p-6 space-y-4">
            <div className="flex justify-between items-center font-mono text-xs">
              <span className="text-[var(--accent-blue)] uppercase tracking-wider flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {jobData.status} ({MODE_LABELS[renderMode]})
              </span>
              <span className="text-text-secondary">{jobData.progress_percent || 0}%</span>
            </div>
            <div className="w-full bg-border h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-gradient-accent h-full transition-all duration-500 rounded-full"
                style={{ width: `${jobData.progress_percent || 0}%` }}
              />
            </div>
            <p className="text-xs text-text-secondary text-center">{jobData.message}</p>
          </div>
        )}

        {/* Error State */}
        {jobData?.status === "failed" && (
          <div className="bg-red-500/5 border border-red-500/20 text-red-400 rounded-lg p-6 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h3 className="font-medium text-sm text-red-300">Processing failed</h3>
              <p className="text-sm text-red-400/80">{jobData.error || jobData.message}</p>
            </div>
          </div>
        )}

        {/* Completed Accumulated Clips */}
        {accumulatedClips.length > 0 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <p className="font-mono text-sm text-emerald-400 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                {accumulatedClips.length} total clip{accumulatedClips.length === 1 ? "" : "s"} rendered
              </p>

              <button
                type="button"
                onClick={handleClearGallery}
                className="text-xs font-mono text-text-secondary hover:text-red-400 flex items-center gap-1.5 transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear workspace
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {accumulatedClips.map((clip, index) => {
                const videoSrc = `${API_BASE}${clip.download_url}`;
                const start = clip.segment?.start_time ?? 0;
                const end = clip.segment?.end_time ?? 0;
                const duration = Math.max(0, Math.round(end - start));
                const score = clip.segment?.virality_score;
                const scorePct =
                  typeof score === "number"
                    ? Math.round(score <= 1 ? score * 100 : score)
                    : null;
                const modeUsed = clip.renderMode || "crop";
                const subsUsed = clip.subtitleEnabled ?? true;

                return (
                  <div
                    key={`${clip.clip_id}_${modeUsed}_${subsUsed}_${index}`}
                    className="bg-panel border border-border rounded-lg overflow-hidden flex flex-col"
                  >
                    <div className="flex items-center justify-between px-3 py-2 border-b border-border font-mono text-[11px]">
                      <span className="text-text-secondary">
                        {formatTime(start)}–{formatTime(end)} ({duration}s)
                      </span>
                      <span className="px-2 py-0.5 rounded bg-[var(--accent-blue)]/10 text-[var(--accent-blue)] font-medium">
                        {MODE_LABELS[modeUsed]}
                      </span>
                    </div>

                    <div className="relative w-full aspect-[9/16] bg-black">
                      <video
                        src={videoSrc}
                        controls
                        className="w-full h-full object-contain"
                        onError={(e) => console.error("Video load error:", e)}
                      />
                    </div>

                    <div className="p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="space-y-1">
                          <h4 className="font-medium text-sm text-foreground">
                            {clip.segment?.clip_title || "Untitled clip"}
                          </h4>
                          {clip.segment?.hook_reason && (
                            <p className="text-xs text-text-secondary line-clamp-2">
                              {clip.segment.hook_reason}
                            </p>
                          )}
                        </div>
                        <span
                          className={`shrink-0 text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${
                            subsUsed
                              ? "bg-[var(--accent-blue)]/10 text-[var(--accent-blue)]"
                              : "bg-text-secondary/10 text-text-secondary"
                          }`}
                        >
                          Captions {subsUsed ? "On" : "Off"}
                        </span>
                      </div>

                      {scorePct !== null && (
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] uppercase tracking-wider text-text-secondary/70">
                            hook
                          </span>
                          <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-accent rounded-full"
                              style={{ width: `${scorePct}%` }}
                            />
                          </div>
                          <span className="font-mono text-[10px] text-text-secondary">{scorePct}</span>
                        </div>
                      )}

                      <a
                        href={videoSrc}
                        download={clip.filename}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full border border-border hover:bg-white/5 text-foreground font-medium py-2 px-4 rounded-md text-sm transition flex items-center justify-center gap-2 focus-visible:ring-2 focus-visible:ring-[var(--accent-blue)]/40 focus-visible:outline-none"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download .mp4
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
