import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeInfo,
  Clock3,
  Crosshair as CrosshairIcon,
  Eye,
  FolderOpen,
  Hand,
  LayoutGrid,
  LoaderCircle,
  Monitor,
  Palette as PaletteIcon,
  Pause,
  Play,
  RotateCcw,
  SlidersHorizontal,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { SegmentLegendItem } from "@/types/api";
import {
  Plane,
  PaletteId,
  axisForPlane,
  buildLegendColorMap,
  buildWindowPresets,
  clamp,
  deriveMaskLabels,
  getPlaneDimensions,
  getSliceCount,
  loadNiftiVolume,
  pointerToVoxel,
  renderSliceToCanvas,
  type VolumeData,
} from "@/viewer/nifti";

const planes: Plane[] = ["axial", "coronal", "sagittal"];
const defaultViewport = { zoom: 1, panX: 0, panY: 0 };

type ViewMode = "single" | "mpr";
type PanelVariant = "hero" | "standard" | "rail";

const planeLabels: Record<Plane, string> = {
  axial: "Axial",
  coronal: "Coronal",
  sagittal: "Sagittal",
};

const viewModeOptions: Array<{
  id: ViewMode;
  label: string;
  Icon: typeof Monitor;
}> = [
  { id: "single", label: "Axial", Icon: Monitor },
  { id: "mpr", label: "MPR", Icon: LayoutGrid },
];

const panelVariantConfig: Record<
  PanelVariant,
  {
    canvasWidth: number;
    canvasHeight: number;
    canvasClassName: string;
    bodyClassName: string;
  }
> = {
  hero: {
    canvasWidth: 1440,
    canvasHeight: 900,
    canvasClassName: "aspect-[16/10] w-full max-h-[72vh]",
    bodyClassName: "flex-1 p-2 md:p-3",
  },
  standard: {
    canvasWidth: 720,
    canvasHeight: 720,
    canvasClassName: "aspect-square w-full",
    bodyClassName: "p-2",
  },
  rail: {
    canvasWidth: 420,
    canvasHeight: 320,
    canvasClassName: "aspect-[4/3] w-full",
    bodyClassName: "p-2",
  },
};

function isPlane(value: string): value is Plane {
  return planes.includes(value as Plane);
}

function axisKeyForPlane(plane: Plane) {
  const axis = axisForPlane(plane);
  return axis === "x" ? "x" : axis === "y" ? "y" : "z";
}

export function OrthogonalViewer({
  imageUrl,
  maskUrl,
  modality,
  segmentsLegend,
}: {
  imageUrl: string;
  maskUrl: string;
  modality: string | null;
  segmentsLegend: SegmentLegendItem[];
}) {
  const [imageVolume, setImageVolume] = useState<VolumeData | null>(null);
  const [maskVolume, setMaskVolume] = useState<VolumeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(0.45);
  const [paletteId, setPaletteId] = useState<PaletteId>("legend");
  const [interactionMode, setInteractionMode] = useState<"crosshair" | "pan">(
    "crosshair",
  );
  const [cinePlane, setCinePlane] = useState<Plane>("axial");
  const [cinePlaying, setCinePlaying] = useState(false);
  const [viewportState, setViewportState] = useState<
    Record<Plane, { zoom: number; panX: number; panY: number }>
  >({
    axial: { ...defaultViewport },
    coronal: { ...defaultViewport },
    sagittal: { ...defaultViewport },
  });
  const [selectedPresetId, setSelectedPresetId] = useState<string>("auto");
  const [slices, setSlices] = useState({ x: 0, y: 0, z: 0 });
  const [viewMode, setViewMode] = useState<ViewMode>("single");
  const [primaryPlane, setPrimaryPlane] = useState<Plane>("axial");
  const [draggedPlane, setDraggedPlane] = useState<Plane | null>(null);
  const [singleDropActive, setSingleDropActive] = useState(false);
  const [visibleSegmentIds, setVisibleSegmentIds] = useState<Set<number>>(
    () => new Set(),
  );
  const viewerRootRef = useRef<HTMLDivElement | null>(null);

  const canvasRefs = {
    axial: useRef<HTMLCanvasElement | null>(null),
    coronal: useRef<HTMLCanvasElement | null>(null),
    sagittal: useRef<HTMLCanvasElement | null>(null),
  };
  const dragState = useRef<{
    plane: Plane;
    mode: "crosshair" | "pan";
    startX: number;
    startY: number;
    originPanX: number;
    originPanY: number;
  } | null>(null);

  const legendMap = useMemo(
    () => buildLegendColorMap(segmentsLegend),
    [segmentsLegend],
  );

  const loadVolumes = useCallback(async () => {
    setLoading(true);
    try {
      const [nextImageVolume, nextMaskVolume] = await Promise.all([
        loadNiftiVolume(imageUrl),
        loadNiftiVolume(maskUrl),
      ]);

      if (nextImageVolume.dims.join("x") !== nextMaskVolume.dims.join("x")) {
        throw new Error(
          "Image and mask volumes do not share the same dimensions",
        );
      }

      setImageVolume(nextImageVolume);
      setMaskVolume(nextMaskVolume);
      setSlices({
        x: Math.floor(nextImageVolume.dims[0] / 2),
        y: Math.floor(nextImageVolume.dims[1] / 2),
        z: Math.floor(nextImageVolume.dims[2] / 2),
      });
      setViewportState({
        axial: { ...defaultViewport },
        coronal: { ...defaultViewport },
        sagittal: { ...defaultViewport },
      });
      setPrimaryPlane("axial");
      setDraggedPlane(null);
      setSingleDropActive(false);
      setError(null);
    } catch (viewerError) {
      if (viewerError instanceof Error) {
        setError(viewerError.message);
      } else {
        setError("Failed to load viewer assets");
      }
    } finally {
      setLoading(false);
    }
  }, [imageUrl, maskUrl]);

  useEffect(() => {
    void loadVolumes();
  }, [imageUrl, loadVolumes, maskUrl]);

  useEffect(() => {
    const handleNativeWheel = (event: WheelEvent) => {
      if (!(event.target instanceof Element)) {
        return;
      }

      if (!event.target.closest('[data-viewer-canvas="true"]')) {
        return;
      }

      if (event.cancelable) {
        event.preventDefault();
      }
    };

    window.addEventListener("wheel", handleNativeWheel, {
      passive: false,
      capture: true,
    });

    return () => {
      window.removeEventListener("wheel", handleNativeWheel, true);
    };
  }, []);

  const presets = useMemo(
    () => (imageVolume ? buildWindowPresets(imageVolume, modality) : []),
    [imageVolume, modality],
  );
  const activePreset =
    presets.find((preset) => preset.id === selectedPresetId) ||
    presets[0] ||
    null;

  useEffect(() => {
    if (presets.length) {
      setSelectedPresetId(presets[0].id);
    }
  }, [presets]);

  const legendItems = useMemo(() => {
    if (segmentsLegend.length) {
      return segmentsLegend;
    }
    if (!maskVolume) {
      return [];
    }
    return deriveMaskLabels(maskVolume).map((label) => ({
      id: label,
      label: `Label ${label}`,
      prompt: "",
      voxels: 0,
      fraction: 0,
      percentage: 0,
      color: legendMap.get(label) || "#0a84ff",
    }));
  }, [legendMap, maskVolume, segmentsLegend]);

  const legendItemIdsKey = useMemo(
    () => legendItems.map((segment) => segment.id).join(","),
    [legendItems],
  );

  useEffect(() => {
    setVisibleSegmentIds(new Set(legendItems.map((segment) => segment.id)));
  }, [legendItemIdsKey, legendItems]);

  const drawViewports = useCallback(() => {
    if (!imageVolume || !activePreset) {
      return;
    }

    for (const plane of planes) {
      const canvas = canvasRefs[plane].current;
      if (!canvas) {
        continue;
      }

      renderSliceToCanvas({
        canvas,
        imageVolume,
        maskVolume,
        visibleSegmentIds,
        plane,
        slices,
        windowRange: activePreset,
        overlayOpacity,
        paletteId,
        legendMap,
        viewport: viewportState[plane],
      });
    }
  }, [
    activePreset,
    imageVolume,
    legendMap,
    maskVolume,
    overlayOpacity,
    paletteId,
    slices,
    visibleSegmentIds,
    viewportState,
  ]);

  useEffect(() => {
    drawViewports();
  }, [drawViewports, primaryPlane, viewMode]);

  useEffect(() => {
    if (!cinePlaying || !imageVolume) {
      return;
    }

    const axisKey = axisKeyForPlane(cinePlane);
    const maxSlice = getSliceCount(imageVolume, cinePlane) - 1;

    const intervalId = window.setInterval(() => {
      setSlices((current) => ({
        ...current,
        [axisKey]: current[axisKey] >= maxSlice ? 0 : current[axisKey] + 1,
      }));
    }, 130);

    return () => window.clearInterval(intervalId);
  }, [cinePlane, cinePlaying, imageVolume]);

  function updateViewport(
    plane: Plane,
    updater: (current: { zoom: number; panX: number; panY: number }) => {
      zoom: number;
      panX: number;
      panY: number;
    },
  ) {
    setViewportState((current) => ({
      ...current,
      [plane]: updater(current[plane]),
    }));
  }

  function handleWheel(
    plane: Plane,
    event: React.WheelEvent<HTMLCanvasElement>,
  ) {
    event.preventDefault();
    event.stopPropagation();
    if (!imageVolume) {
      return;
    }

    if (event.ctrlKey || event.metaKey) {
      updateViewport(plane, (current) => ({
        ...current,
        zoom: clamp(current.zoom + (event.deltaY < 0 ? 0.12 : -0.12), 0.6, 6),
      }));
      return;
    }

    const axisKey = axisKeyForPlane(plane);
    const maxSlice = getSliceCount(imageVolume, plane) - 1;
    setSlices((current) => ({
      ...current,
      [axisKey]: clamp(
        current[axisKey] + (event.deltaY > 0 ? 1 : -1),
        0,
        maxSlice,
      ),
    }));
  }

  function updateCrosshairFromPointer(
    plane: Plane,
    clientX: number,
    clientY: number,
  ) {
    if (!imageVolume) {
      return;
    }

    const canvas = canvasRefs[plane].current;
    if (!canvas) {
      return;
    }

    const voxel = pointerToVoxel({
      canvas,
      plane,
      imageVolume,
      slices,
      viewport: viewportState[plane],
      clientX,
      clientY,
    });

    if (!voxel) {
      return;
    }

    setSlices({
      x: voxel.x,
      y: voxel.y,
      z: voxel.z,
    });
  }

  function handleMouseDown(
    plane: Plane,
    event: React.MouseEvent<HTMLCanvasElement>,
  ) {
    const mode =
      interactionMode === "pan" || event.shiftKey ? "pan" : "crosshair";
    dragState.current = {
      plane,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      originPanX: viewportState[plane].panX,
      originPanY: viewportState[plane].panY,
    };

    if (mode === "crosshair") {
      updateCrosshairFromPointer(plane, event.clientX, event.clientY);
    }
  }

  function handleMouseMove(
    plane: Plane,
    event: React.MouseEvent<HTMLCanvasElement>,
  ) {
    const activeDrag = dragState.current;
    if (!activeDrag || activeDrag.plane !== plane) {
      return;
    }

    if (activeDrag.mode === "pan") {
      updateViewport(plane, () => ({
        ...viewportState[plane],
        panX: activeDrag.originPanX + (event.clientX - activeDrag.startX),
        panY: activeDrag.originPanY + (event.clientY - activeDrag.startY),
      }));
      return;
    }

    updateCrosshairFromPointer(plane, event.clientX, event.clientY);
  }

  function handlePointerRelease() {
    dragState.current = null;
  }

  function handleZoom(plane: Plane, direction: "in" | "out") {
    updateViewport(plane, (current) => ({
      ...current,
      zoom: clamp(current.zoom + (direction === "in" ? 0.18 : -0.18), 0.6, 6),
    }));
  }

  function handleResetView(plane: Plane) {
    updateViewport(plane, () => ({ ...defaultViewport }));
  }

  function handleSliceInput(plane: Plane, value: number) {
    const axisKey = axisKeyForPlane(plane);
    setSlices((current) => ({
      ...current,
      [axisKey]: value,
    }));
  }

  function handleSegmentVisibilityToggle(segmentId: number) {
    setVisibleSegmentIds((current) => {
      const next = new Set(current);
      if (next.has(segmentId)) {
        next.delete(segmentId);
      } else {
        next.add(segmentId);
      }
      return next;
    });
  }

  function handleAllSegmentsVisibility(nextVisible: boolean) {
    setVisibleSegmentIds(
      nextVisible ? new Set(legendItems.map((segment) => segment.id)) : new Set(),
    );
  }

  function handlePlaneDragStart(
    plane: Plane,
    event: React.DragEvent<HTMLElement>,
  ) {
    if (viewMode !== "single" || plane === primaryPlane) {
      event.preventDefault();
      return;
    }

    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", plane);
    setDraggedPlane(plane);
  }

  function handlePlaneDragEnd() {
    setDraggedPlane(null);
    setSingleDropActive(false);
  }

  function handlePrimaryPlaneDragOver(event: React.DragEvent<HTMLElement>) {
    if (viewMode !== "single") {
      return;
    }

    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setSingleDropActive(true);
  }

  function handlePrimaryPlaneDragLeave(event: React.DragEvent<HTMLElement>) {
    const relatedTarget = event.relatedTarget as Node | null;
    if (relatedTarget && event.currentTarget.contains(relatedTarget)) {
      return;
    }

    setSingleDropActive(false);
  }

  function handlePrimaryPlaneDrop(event: React.DragEvent<HTMLElement>) {
    if (viewMode !== "single") {
      return;
    }

    event.preventDefault();
    const nextPlane = event.dataTransfer.getData("text/plain");
    if (isPlane(nextPlane) && nextPlane !== primaryPlane) {
      setPrimaryPlane(nextPlane);
    }

    setDraggedPlane(null);
    setSingleDropActive(false);
  }

  function getPlaneMetrics(plane: Plane) {
    if (!imageVolume) {
      return null;
    }

    const axisKey = axisKeyForPlane(plane);
    const sliceCount = getSliceCount(imageVolume, plane);
    const { width, height } = getPlaneDimensions(imageVolume, plane);
    const currentSlice = slices[axisKey];

    return { axisKey, sliceCount, width, height, currentSlice };
  }

  function renderToolbarButton({
    active,
    label,
    Icon,
    onClick,
  }: {
    active?: boolean;
    label: string;
    Icon?: typeof Monitor;
    onClick: () => void;
  }) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-2 rounded-[8px] border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] transition",
          active
            ? "border-sky-300/45 bg-sky-500/14 text-sky-50"
            : "border-white/8 bg-[#26272e] text-slate-200 hover:border-white/16 hover:bg-[#2d2f37] hover:text-white",
        )}
      >
        {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
        {label}
      </button>
    );
  }

  function renderPlanePanel({
    plane,
    variant,
    interactive = true,
    emphasized = false,
    draggable = false,
    promotable = false,
    className,
    onDragOver,
    onDragLeave,
    onDrop,
  }: {
    plane: Plane;
    variant: PanelVariant;
    interactive?: boolean;
    emphasized?: boolean;
    draggable?: boolean;
    promotable?: boolean;
    className?: string;
    onDragOver?: React.DragEventHandler<HTMLElement>;
    onDragLeave?: React.DragEventHandler<HTMLElement>;
    onDrop?: React.DragEventHandler<HTMLElement>;
  }) {
    const metrics = getPlaneMetrics(plane);
    if (!metrics) {
      return null;
    }

    const variantConfig = panelVariantConfig[variant];

    return (
      <section
        key={plane}
        draggable={draggable}
        onDragStart={
          draggable ? (event) => handlePlaneDragStart(plane, event) : undefined
        }
        onDragEnd={draggable ? handlePlaneDragEnd : undefined}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "flex h-full flex-col overflow-hidden rounded-[10px] border border-white/8 bg-[#1d1f26]",
          emphasized && "border-sky-300/30",
          draggedPlane === plane && "border-sky-300/45 bg-[#232b36]",
          draggable && "cursor-grab active:cursor-grabbing",
          className,
        )}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/6 bg-[#2b2d35] px-3 py-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Eye className="h-3.5 w-3.5 text-sky-300/80" />
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-100/85">
                {planeLabels[plane]}
              </p>
              {emphasized ? (
                <span className="rounded-[6px] border border-sky-300/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-50">
                  Main
                </span>
              ) : null}
              {emphasized && singleDropActive ? (
                <span className="rounded-[6px] border border-sky-200/24 bg-sky-300/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-50">
                  Drop
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              {metrics.width} x {metrics.height} px
            </p>
          </div>

          {interactive ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => handleZoom(plane, "out")}
                className="rounded-[6px] border border-white/8 bg-[#20222a] p-1.5 text-slate-200 transition hover:border-white/18 hover:bg-[#292b34]"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => handleZoom(plane, "in")}
                className="rounded-[6px] border border-white/8 bg-[#20222a] p-1.5 text-slate-200 transition hover:border-white/18 hover:bg-[#292b34]"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => handleResetView(plane)}
                className="rounded-[6px] border border-white/8 bg-[#20222a] p-1.5 text-slate-200 transition hover:border-white/18 hover:bg-[#292b34]"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : promotable ? (
            <button
              type="button"
              onClick={() => setPrimaryPlane(plane)}
              className="rounded-[6px] border border-white/8 bg-[#20222a] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-100 transition hover:border-sky-300/24 hover:bg-[#2a3040] hover:text-white"
            >
              Main
            </button>
          ) : null}
        </div>

        <div className={cn("bg-black", variantConfig.bodyClassName)}>
          <canvas
            ref={(node) => {
              canvasRefs[plane].current = node;
            }}
            data-viewer-canvas={interactive ? "true" : undefined}
            width={variantConfig.canvasWidth}
            height={variantConfig.canvasHeight}
            onWheel={
              interactive ? (event) => handleWheel(plane, event) : undefined
            }
            onMouseDown={
              interactive ? (event) => handleMouseDown(plane, event) : undefined
            }
            onMouseMove={
              interactive ? (event) => handleMouseMove(plane, event) : undefined
            }
            onMouseUp={interactive ? handlePointerRelease : undefined}
            onMouseLeave={interactive ? handlePointerRelease : undefined}
            className={cn(
              "mx-auto rounded-[8px] border border-white/8 bg-black",
              variantConfig.canvasClassName,
              !interactive && "pointer-events-none opacity-90",
            )}
          />
        </div>

        <div className="border-t border-white/6 bg-[#23252d] px-3 py-2">
          {interactive ? (
            <div className="grid items-center gap-2 md:grid-cols-[auto_minmax(0,1fr)_auto]">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Slice {metrics.currentSlice + 1} / {metrics.sliceCount}
              </div>
              <input
                type="range"
                min={0}
                max={metrics.sliceCount - 1}
                step={1}
                value={metrics.currentSlice}
                onChange={(event) =>
                  handleSliceInput(plane, Number(event.target.value))
                }
                className="w-full accent-sky-400"
              />
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                {interactionMode}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Slice {metrics.currentSlice + 1} / {metrics.sliceCount}
              </div>
              {promotable ? (
                <div className="text-[10px] uppercase tracking-[0.16em] text-sky-100/75">
                  Drag to replace
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>
    );
  }

  function renderQuickPlaneControl(plane: Plane) {
    const metrics = getPlaneMetrics(plane);
    if (!metrics) {
      return null;
    }

    return (
      <div
        key={plane}
        className="space-y-2 rounded-[10px] border border-white/8 bg-[#24262e] p-3"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-100/80">
              {planeLabels[plane]}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">
              {metrics.width} x {metrics.height}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setPrimaryPlane(plane)}
            className={cn(
              "rounded-[6px] border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] transition",
              primaryPlane === plane
                ? "border-sky-300/35 bg-sky-500/10 text-sky-50"
                : "border-white/8 bg-[#20222a] text-slate-200 hover:border-white/16",
            )}
          >
            Focus
          </button>
        </div>
        <input
          type="range"
          min={0}
          max={metrics.sliceCount - 1}
          step={1}
          value={metrics.currentSlice}
          onChange={(event) =>
            handleSliceInput(plane, Number(event.target.value))
          }
          className="w-full accent-sky-400"
        />
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <span>
            {metrics.currentSlice + 1} / {metrics.sliceCount}
          </span>
          <span>{primaryPlane === plane ? "main" : "sync"}</span>
        </div>
      </div>
    );
  }

  function renderLegendBar() {
    if (!legendItems.length) {
      return null;
    }

    return (
      <div className="border-t border-white/6 bg-[#20222a] px-3 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <BadgeInfo className="h-3.5 w-3.5 text-sky-300/80" />
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-100/80">
              Legenda
            </p>
          </div>
          <span className="text-[10px] uppercase tracking-[0.16em] text-slate-500">
            {visibleSegmentIds.size}/{legendItems.length} visiveis
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => handleAllSegmentsVisibility(true)}
            className="rounded-[6px] border border-white/8 bg-[#282a33] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-100 transition hover:border-white/16 hover:bg-[#2d3039]"
          >
            Mostrar todas
          </button>
          <button
            type="button"
            onClick={() => handleAllSegmentsVisibility(false)}
            className="rounded-[6px] border border-white/8 bg-[#282a33] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-100 transition hover:border-white/16 hover:bg-[#2d3039]"
          >
            Ocultar todas
          </button>
        </div>

        <div className="mt-3">
          <div className="flex flex-wrap gap-2">
            {legendItems.map((segment) => {
              const isVisible = visibleSegmentIds.has(segment.id);

              return (
                <button
                  key={segment.id}
                  type="button"
                  onClick={() => handleSegmentVisibilityToggle(segment.id)}
                  className={cn(
                    "flex min-w-[220px] flex-1 basis-[220px] items-start gap-3 rounded-[8px] border px-3 py-2 text-left transition",
                    isVisible
                      ? "border-white/8 bg-[#282a33] hover:border-white/16 hover:bg-[#2d3039]"
                      : "border-white/6 bg-[#1f2128] opacity-55 hover:opacity-80",
                  )}
                >
                  <span
                    className="mt-1 inline-flex h-2.5 w-2.5 shrink-0"
                    style={{ backgroundColor: segment.color }}
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-100">
                      {segment.label}
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {segment.voxels
                        ? `${segment.voxels.toLocaleString()} voxels · ${segment.percentage}%`
                        : `Label ${segment.id}`}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "ml-auto shrink-0 rounded-[6px] border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em]",
                      isVisible
                        ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
                        : "border-white/8 bg-[#24262e] text-slate-400",
                    )}
                  >
                    {isVisible ? "Ativa" : "Oculta"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  function renderSidebar() {
    const singleModePlanes = planes.filter((plane) => plane !== primaryPlane);

    return (
      <aside className="flex min-h-0 flex-col border-r border-white/6 bg-[#22242c]">
        <div className="border-b border-white/6 px-3 py-3">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-3.5 w-3.5 text-sky-300/80" />
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-100/80">
              Viewport Rail
            </p>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            {viewMode === "single"
              ? "Arraste um corte lateral para o viewport principal."
              : "Controles rapidos e sincronizados dos cortes."}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {viewMode === "single" ? (
            <div className="space-y-2">
              {singleModePlanes.map((plane) =>
                renderPlanePanel({
                  plane,
                  variant: "rail",
                  interactive: false,
                  draggable: true,
                  promotable: true,
                }),
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {planes.map((plane) => renderQuickPlaneControl(plane))}
            </div>
          )}
        </div>
      </aside>
    );
  }

  function renderMainContent() {
    if (viewMode === "single") {
      return (
        <div className="h-full p-2">
          {renderPlanePanel({
            plane: primaryPlane,
            variant: "hero",
            emphasized: true,
            className: cn(
              "min-h-[72vh]",
              singleDropActive && "border-sky-300/50 bg-[#232b36]",
            ),
            onDragOver: handlePrimaryPlaneDragOver,
            onDragLeave: handlePrimaryPlaneDragLeave,
            onDrop: handlePrimaryPlaneDrop,
          })}
        </div>
      );
    }

    return (
      <div className="grid h-full gap-px bg-white/6 p-px xl:grid-cols-3">
        {planes.map((plane) =>
          renderPlanePanel({
            plane,
            variant: "standard",
            emphasized: plane === primaryPlane,
          }),
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="overflow-hidden rounded-[12px] border border-white/8 bg-[#1d1f26]">
        <div className="flex min-h-[70vh] items-center justify-center gap-3 text-sm text-slate-200">
          <LoaderCircle className="h-5 w-5 animate-spin text-sky-300" />
          Loading image and mask volumes...
        </div>
      </div>
    );
  }

  if (error || !imageVolume || !activePreset) {
    return (
      <div className="overflow-hidden rounded-[12px] border border-rose-400/20 bg-[#1d1f26] p-5">
        <p className="text-lg font-semibold text-white">
          Viewer failed to load
        </p>
        <p className="mt-2 text-sm leading-7 text-slate-300">{error}</p>
        <button
          type="button"
          onClick={() => {
            toast.dismiss();
            void loadVolumes();
          }}
          className="mt-4 rounded-[8px] border border-sky-300/30 bg-sky-500/12 px-4 py-2 text-sm font-semibold text-sky-50 transition hover:bg-sky-500/18"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div
      ref={viewerRootRef}
      className="overflow-hidden overscroll-contain rounded-[12px] border border-white/8 bg-[#1d1f26] text-white shadow-[0_30px_80px_rgba(0,0,0,0.28)]"
    >
      <div className="border-b border-white/6 bg-[#34343c] px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-px">
            {viewModeOptions.map((option) =>
              renderToolbarButton({
                active: viewMode === option.id,
                label: option.label,
                Icon: option.Icon,
                onClick: () => setViewMode(option.id),
              }),
            )}
          </div>

          <div className="h-6 w-px bg-white/10" />

          <div className="flex h-8 items-center gap-2 rounded-[8px] border border-white/8 bg-[#26272e] px-3">
            <SlidersHorizontal className="h-3.5 w-3.5 text-sky-300/80" />
            <select
              value={selectedPresetId}
              onChange={(event) => setSelectedPresetId(event.target.value)}
              className="h-full bg-transparent pr-2 text-xs font-semibold uppercase tracking-[0.14em] text-white outline-none"
            >
              {presets.map((preset) => (
                <option
                  key={preset.id}
                  value={preset.id}
                  className="bg-slate-950"
                >
                  {preset.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex h-8 items-center gap-2 rounded-[8px] border border-white/8 bg-[#26272e] px-3">
            <PaletteIcon className="h-3.5 w-3.5 text-sky-300/80" />
            <select
              value={paletteId}
              onChange={(event) =>
                setPaletteId(event.target.value as PaletteId)
              }
              className="h-full bg-transparent pr-2 text-xs font-semibold uppercase tracking-[0.14em] text-white outline-none"
            >
              {[
                { id: "legend", label: "Legend" },
                { id: "teal", label: "Teal" },
                { id: "warm", label: "Warm" },
                { id: "contrast", label: "Contrast" },
              ].map((palette) => (
                <option
                  key={palette.id}
                  value={palette.id}
                  className="bg-slate-950"
                >
                  {palette.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 rounded-[8px] border border-white/8 bg-[#26272e] px-3 py-1.5">
            <PaletteIcon className="h-3.5 w-3.5 text-sky-300/80" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
              Mask
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={overlayOpacity}
              onChange={(event) =>
                setOverlayOpacity(Number(event.target.value))
              }
              className="w-24 accent-sky-400"
            />
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
              {Math.round(overlayOpacity * 100)}%
            </span>
          </div>

          <div className="h-6 w-px bg-white/10" />

          <div className="flex items-center gap-px">
            {[
              { id: "crosshair", label: "Crosshair", Icon: CrosshairIcon },
              { id: "pan", label: "Pan", Icon: Hand },
            ].map((mode) =>
              renderToolbarButton({
                active: interactionMode === mode.id,
                label: mode.label,
                Icon: mode.Icon,
                onClick: () =>
                  setInteractionMode(mode.id as "crosshair" | "pan"),
              }),
            )}
          </div>

          <div className="ml-auto flex h-8 items-center gap-2 rounded-[8px] border border-white/8 bg-[#26272e] px-3">
            <Clock3 className="h-3.5 w-3.5 text-sky-300/80" />
            <select
              value={cinePlane}
              onChange={(event) => setCinePlane(event.target.value as Plane)}
              className="h-full bg-transparent pr-2 text-xs font-semibold uppercase tracking-[0.14em] text-white outline-none"
            >
              {planes.map((plane) => (
                <option key={plane} value={plane} className="bg-slate-950">
                  {planeLabels[plane]}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => setCinePlaying((current) => !current)}
            className="inline-flex h-8 items-center gap-2 rounded-[8px] border border-sky-300/30 bg-[#26272e] px-3 text-xs font-semibold uppercase tracking-[0.14em] text-sky-50 transition hover:bg-[#2d3341]"
          >
            {cinePlaying ? (
              <Pause className="h-3.5 w-3.5" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {cinePlaying ? "Pause" : "Cine"}
          </button>
        </div>
      </div>

      <div className="grid min-h-[78vh] xl:grid-cols-[260px_minmax(0,1fr)]">
        {renderSidebar()}
        <section className="flex min-w-0 flex-col bg-black">
          <div className="min-h-0 flex-1">{renderMainContent()}</div>
          {renderLegendBar()}
        </section>
      </div>
    </div>
  );
}
