import { useEffect, useRef, useState } from "react";
import { Box, Hand, RotateCcw, SlidersHorizontal, ZoomIn } from "lucide-react";
import { cn } from "@/lib/utils";
import { clamp, type VolumeData, type WindowPreset } from "@/viewer/nifti";
import {
  buildVolumeRenderProfiles,
  getDefaultVolumeRenderProfile,
  prepareVolumeFor3D,
  renderPreparedVolumeToCanvas,
  type PreparedVolume3D,
  type VolumeCameraState,
  type VolumeRenderMode,
} from "@/viewer/volume3d";

const coronalPitch = Math.PI / 2 - 0.02;
const defaultCamera: VolumeCameraState = {
  yaw: 0,
  pitch: coronalPitch,
  zoom: 1,
  panX: 0,
  panY: 0,
};

const cameraPresets = [
  { id: "coronal", label: "Coronal", camera: defaultCamera },
  {
    id: "axial",
    label: "Axial",
    camera: { yaw: 0, pitch: 0, zoom: 1, panX: 0, panY: 0 },
  },
  {
    id: "sagittal",
    label: "Sagittal",
    camera: { yaw: Math.PI / 2, pitch: 0, zoom: 1, panX: 0, panY: 0 },
  },
] as const;

interface VolumeRenderer3DProps {
  volume: VolumeData;
  modality: string | null;
  windowPreset: WindowPreset;
  fullHeight?: boolean;
  className?: string;
}

export function VolumeRenderer3D({
  volume,
  modality,
  windowPreset,
  fullHeight = false,
  className,
}: VolumeRenderer3DProps) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragState = useRef<{
    mode: "orbit" | "pan";
    startX: number;
    startY: number;
    yaw: number;
    pitch: number;
    panX: number;
    panY: number;
  } | null>(null);
  const renderRevision = useRef(0);
  const profiles = buildVolumeRenderProfiles(modality);
  const fallbackProfile = getDefaultVolumeRenderProfile(modality);
  const [selectedProfileId, setSelectedProfileId] = useState(
    fallbackProfile.id,
  );
  const [renderMode, setRenderMode] = useState<VolumeRenderMode>(
    fallbackProfile.mode,
  );
  const [threshold, setThreshold] = useState(fallbackProfile.threshold);
  const [exposure, setExposure] = useState(fallbackProfile.exposure);
  const [quality, setQuality] = useState(fallbackProfile.quality);
  const [camera, setCamera] = useState<VolumeCameraState>(defaultCamera);
  const [preparedVolume, setPreparedVolume] = useState<PreparedVolume3D | null>(
    null,
  );
  const [preparing, setPreparing] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [viewportSize, setViewportSize] = useState({
    width: 960,
    height: fullHeight ? 720 : 560,
  });

  const selectedProfile =
    profiles.find((profile) => profile.id === selectedProfileId) ||
    fallbackProfile;

  useEffect(() => {
    const nextProfile = getDefaultVolumeRenderProfile(modality);
    setSelectedProfileId(nextProfile.id);
    setRenderMode(nextProfile.mode);
    setThreshold(nextProfile.threshold);
    setExposure(nextProfile.exposure);
    setQuality(nextProfile.quality);
    setCamera(defaultCamera);
  }, [modality, volume.sourceUrl]);

  useEffect(() => {
    setRenderMode(selectedProfile.mode);
    setThreshold(selectedProfile.threshold);
    setExposure(selectedProfile.exposure);
    setQuality(selectedProfile.quality);
  }, [selectedProfile]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) {
      return;
    }

    const updateViewportSize = () => {
      const nextSize = {
        width: Math.max(360, Math.round(frame.clientWidth)),
        height: Math.max(
          fullHeight ? 520 : 440,
          Math.round(frame.clientHeight),
        ),
      };

      setViewportSize((current) =>
        current.width === nextSize.width && current.height === nextSize.height
          ? current
          : nextSize,
      );
    };

    updateViewportSize();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateViewportSize);
      return () => window.removeEventListener("resize", updateViewportSize);
    }

    const observer = new ResizeObserver(updateViewportSize);
    observer.observe(frame);

    return () => observer.disconnect();
  }, [fullHeight]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const devicePixelRatio = window.devicePixelRatio || 1;
    const nextWidth = Math.max(
      480,
      Math.round(viewportSize.width * devicePixelRatio),
    );
    const nextHeight = Math.max(
      320,
      Math.round(viewportSize.height * devicePixelRatio),
    );

    if (canvas.width !== nextWidth) {
      canvas.width = nextWidth;
    }
    if (canvas.height !== nextHeight) {
      canvas.height = nextHeight;
    }
  }, [viewportSize]);

  useEffect(() => {
    let cancelled = false;
    setPreparing(true);

    const timeoutId = window.setTimeout(() => {
      const nextPreparedVolume = prepareVolumeFor3D(
        volume,
        windowPreset,
        modality?.toLowerCase().includes("ct") ? 176 : 160,
      );

      if (cancelled) {
        return;
      }

      setPreparedVolume(nextPreparedVolume);
      setPreparing(false);
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [modality, volume, windowPreset]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !preparedVolume) {
      return;
    }

    renderRevision.current += 1;
    const revision = renderRevision.current;
    setRendering(true);

    void renderPreparedVolumeToCanvas({
      canvas,
      preparedVolume,
      camera,
      settings: {
        mode: renderMode,
        threshold,
        exposure,
        quality,
        color: selectedProfile.color,
        targetHeight: clamp(Math.round(viewportSize.height * 0.72), 260, 680),
      },
      shouldAbort: () => revision !== renderRevision.current,
    }).finally(() => {
      if (revision === renderRevision.current) {
        setRendering(false);
      }
    });

    return () => {
      if (revision === renderRevision.current) {
        renderRevision.current += 1;
      }
    };
  }, [
    camera,
    preparedVolume,
    quality,
    renderMode,
    selectedProfile,
    threshold,
    exposure,
    viewportSize.height,
  ]);

  function applyCameraPreset(presetId: (typeof cameraPresets)[number]["id"]) {
    const preset = cameraPresets.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }

    setCamera({ ...preset.camera });
  }

  function handlePointerDown(event: React.MouseEvent<HTMLCanvasElement>) {
    dragState.current = {
      mode: event.shiftKey || event.button === 1 ? "pan" : "orbit",
      startX: event.clientX,
      startY: event.clientY,
      yaw: camera.yaw,
      pitch: camera.pitch,
      panX: camera.panX,
      panY: camera.panY,
    };
  }

  function handlePointerMove(event: React.MouseEvent<HTMLCanvasElement>) {
    const activeDrag = dragState.current;
    if (!activeDrag) {
      return;
    }

    const deltaX = event.clientX - activeDrag.startX;
    const deltaY = event.clientY - activeDrag.startY;

    if (activeDrag.mode === "pan") {
      const widthFactor = Math.max(viewportSize.width, 1);
      const heightFactor = Math.max(viewportSize.height, 1);

      setCamera((current) => ({
        ...current,
        panX: activeDrag.panX + (deltaX / widthFactor) * 1.2,
        panY: activeDrag.panY - (deltaY / heightFactor) * 1.2,
      }));
      return;
    }

    setCamera((current) => ({
      ...current,
      yaw: activeDrag.yaw + deltaX * 0.012,
      pitch: clamp(activeDrag.pitch - deltaY * 0.012, -1.55, 1.55),
    }));
  }

  function handlePointerRelease() {
    dragState.current = null;
  }

  function handleWheel(event: React.WheelEvent<HTMLCanvasElement>) {
    event.preventDefault();
    setCamera((current) => ({
      ...current,
      zoom: clamp(current.zoom + (event.deltaY < 0 ? 0.14 : -0.14), 0.55, 2.8),
    }));
  }

  return (
    <section
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden rounded-[10px] border border-white/8 bg-[#1c1d24]",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/6 bg-[#2b2d35] px-3 py-2">
        <div>
          <div className="flex items-center gap-2">
            <Box className="h-3.5 w-3.5 text-sky-300/80" />
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-100/80">
              Volume Render
            </p>
            <span className="rounded-[6px] border border-sky-300/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-50">
              {selectedProfile.label}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Window {windowPreset.label} · {modality || "MRI"} · Drag rotaciona,
            Shift + drag move, scroll aproxima
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {cameraPresets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => applyCameraPreset(preset.id)}
              className="rounded-[7px] border border-white/8 bg-[#20222a] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-100 transition hover:border-sky-300/20 hover:bg-[#262b36]"
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setCamera(defaultCamera)}
            className="inline-flex items-center gap-2 rounded-[7px] border border-white/8 bg-[#20222a] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-100 transition hover:border-sky-300/20 hover:bg-[#262b36]"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset
          </button>
        </div>
      </div>

      <div className="grid gap-px border-b border-white/6 bg-white/6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <div className="flex flex-wrap items-center gap-3 bg-[#24262e] px-3 py-2.5">
          <div className="inline-flex items-center gap-2 rounded-[7px] border border-white/8 bg-[#20222a] px-3 py-1.5">
            <SlidersHorizontal className="h-3.5 w-3.5 text-sky-300/80" />
            <select
              value={selectedProfileId}
              onChange={(event) => setSelectedProfileId(event.target.value)}
              className="bg-transparent text-[11px] font-semibold uppercase tracking-[0.16em] text-white outline-none"
            >
              {profiles.map((profile) => (
                <option
                  key={profile.id}
                  value={profile.id}
                  className="bg-slate-950"
                >
                  {profile.label}
                </option>
              ))}
            </select>
          </div>

          <div className="inline-flex items-center gap-px rounded-[7px] border border-white/8 bg-[#20222a] p-1">
            {[
              { id: "surface" as const, label: "Surface" },
              { id: "mip" as const, label: "MIP" },
            ].map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setRenderMode(option.id)}
                className={cn(
                  "rounded-[6px] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] transition",
                  renderMode === option.id
                    ? "bg-sky-500/16 text-sky-50"
                    : "text-slate-300 hover:bg-white/6 hover:text-white",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-px bg-white/6 sm:grid-cols-3">
          {[
            {
              label: "Threshold",
              value: threshold,
              min: 0.05,
              max: 0.95,
              step: 0.01,
              onChange: setThreshold,
            },
            {
              label: "Exposure",
              value: exposure,
              min: 0.6,
              max: 1.6,
              step: 0.02,
              onChange: setExposure,
            },
            {
              label: "Detail",
              value: quality,
              min: 0.7,
              max: 1.6,
              step: 0.02,
              onChange: setQuality,
            },
          ].map((control) => (
            <label
              key={control.label}
              className="flex flex-col gap-1.5 bg-[#24262e] px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                <span>{control.label}</span>
                <span>{control.value.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={control.min}
                max={control.max}
                step={control.step}
                value={control.value}
                onChange={(event) =>
                  control.onChange(Number(event.target.value))
                }
                className="w-full accent-sky-400"
              />
            </label>
          ))}
        </div>
      </div>

      <div
        ref={frameRef}
        className={cn(
          "relative flex-1 overflow-hidden bg-black",
          fullHeight ? "min-h-[62vh]" : "min-h-[48vh]",
        )}
      >
        <canvas
          ref={canvasRef}
          onContextMenu={(event) => event.preventDefault()}
          onWheel={handleWheel}
          onMouseDown={handlePointerDown}
          onMouseMove={handlePointerMove}
          onMouseUp={handlePointerRelease}
          onMouseLeave={handlePointerRelease}
          className="h-full w-full bg-black"
        />

        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-[8px] border border-white/8 bg-black/60 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-200 backdrop-blur">
          <ZoomIn className="h-3.5 w-3.5 text-sky-300/80" />
          Zoom {camera.zoom.toFixed(2)}x
        </div>

        <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-2 rounded-[8px] border border-white/8 bg-black/60 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-200 backdrop-blur">
          <Hand className="h-3.5 w-3.5 text-sky-300/80" />
          {renderMode === "mip" ? "MIP" : "Volume surface"} ·{" "}
          {rendering ? "rendering" : preparing ? "preparing" : "ready"}
        </div>

        {(preparing || rendering) && !preparedVolume ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/55">
            <div className="rounded-[10px] border border-white/8 bg-[#20222a]/90 px-4 py-3 text-center text-sm text-slate-200 backdrop-blur">
              Preparando volume 3D...
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
