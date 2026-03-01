import { normalizeViewerAssetUrl } from "@/lib/viewer-url";
import type { SegmentLegendItem } from "@/types/api";

export type Plane = "axial" | "coronal" | "sagittal";
export type PaletteId = "legend" | "teal" | "warm" | "contrast";

export interface VolumeData {
  sourceUrl: string;
  dims: [number, number, number];
  spacing: [number, number, number];
  data: Float32Array;
  min: number;
  max: number;
}

export interface WindowPreset {
  id: string;
  label: string;
  min: number;
  max: number;
}

const datatypeReaders = {
  2: {
    bytes: 1,
    read: (view: DataView, offset: number) => view.getUint8(offset),
  },
  4: {
    bytes: 2,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getInt16(offset, littleEndian),
  },
  8: {
    bytes: 4,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getInt32(offset, littleEndian),
  },
  16: {
    bytes: 4,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getFloat32(offset, littleEndian),
  },
  64: {
    bytes: 8,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getFloat64(offset, littleEndian),
  },
  256: {
    bytes: 1,
    read: (view: DataView, offset: number) => view.getInt8(offset),
  },
  512: {
    bytes: 2,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getUint16(offset, littleEndian),
  },
  768: {
    bytes: 4,
    read: (view: DataView, offset: number, littleEndian: boolean) =>
      view.getUint32(offset, littleEndian),
  },
} as const;

const paletteMap: Record<Exclude<PaletteId, "legend">, string[]> = {
  teal: ["#14b8a6", "#0ea5e9", "#38bdf8", "#06b6d4", "#22c55e", "#10b981"],
  warm: ["#f97316", "#fb7185", "#f59e0b", "#ef4444", "#f43f5e", "#eab308"],
  contrast: ["#60a5fa", "#f472b6", "#facc15", "#4ade80", "#fb7185", "#c084fc"],
};

const planeConfig = {
  axial: {
    axes: ["x", "y", "z"] as const,
    flipX: true,
    flipY: true,
    orientation: { left: "R", right: "L", top: "A", bottom: "P" },
  },
  coronal: {
    axes: ["x", "z", "y"] as const,
    flipX: true,
    flipY: true,
    orientation: { left: "R", right: "L", top: "S", bottom: "I" },
  },
  sagittal: {
    axes: ["y", "z", "x"] as const,
    flipX: false,
    flipY: true,
    orientation: { left: "A", right: "P", top: "S", bottom: "I" },
  },
} satisfies Record<
  Plane,
  {
    axes: readonly ["x" | "y", "y" | "z", "x" | "y" | "z"];
    flipX: boolean;
    flipY: boolean;
    orientation: { left: string; right: string; top: string; bottom: string };
  }
>;

export function axisForPlane(plane: Plane) {
  return planeConfig[plane].axes[2];
}

export function getSliceCount(volume: VolumeData, plane: Plane) {
  const axis = axisForPlane(plane);
  if (axis === "x") {
    return volume.dims[0];
  }
  if (axis === "y") {
    return volume.dims[1];
  }
  return volume.dims[2];
}

export function getPlaneDimensions(volume: VolumeData, plane: Plane) {
  const [x, y, z] = volume.dims;
  if (plane === "axial") {
    return { width: x, height: y };
  }
  if (plane === "coronal") {
    return { width: x, height: z };
  }
  return { width: y, height: z };
}

function getPlaneDisplayDimensions(volume: VolumeData, plane: Plane) {
  const { width, height } = getPlaneDimensions(volume, plane);
  const [spacingX, spacingY, spacingZ] = volume.spacing;

  if (plane === "axial") {
    return {
      width: width * spacingX,
      height: height * spacingY,
    };
  }

  if (plane === "coronal") {
    return {
      width: width * spacingX,
      height: height * spacingZ,
    };
  }

  return {
    width: width * spacingY,
    height: height * spacingZ,
  };
}

export function getPlaneOrientation(plane: Plane) {
  return planeConfig[plane].orientation;
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function getVoxelIndex(
  dims: [number, number, number],
  x: number,
  y: number,
  z: number,
) {
  return x + y * dims[0] + z * dims[0] * dims[1];
}

function mapPlanePointToVoxel(
  plane: Plane,
  x: number,
  y: number,
  slices: { x: number; y: number; z: number },
) {
  if (plane === "axial") {
    return { x, y, z: slices.z };
  }
  if (plane === "coronal") {
    return { x, y: slices.y, z: y };
  }
  return { x: slices.x, y: x, z: y };
}

function mapCrosshairToPlane(
  plane: Plane,
  slices: { x: number; y: number; z: number },
) {
  if (plane === "axial") {
    return { x: slices.x, y: slices.y };
  }
  if (plane === "coronal") {
    return { x: slices.x, y: slices.z };
  }
  return { x: slices.y, y: slices.z };
}

function getReader(datatype: number) {
  const reader = datatypeReaders[datatype as keyof typeof datatypeReaders];
  if (!reader) {
    throw new Error(`Unsupported NIfTI datatype: ${datatype}`);
  }
  return reader;
}

async function gunzipBuffer(buffer: ArrayBuffer) {
  if (typeof DecompressionStream === "undefined") {
    throw new Error(
      "This browser does not support gzip decompression for NIfTI assets.",
    );
  }

  const stream = new Blob([buffer])
    .stream()
    .pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

async function fetchBuffer(url: string) {
  const resolvedUrl = normalizeViewerAssetUrl(url);
  const response = await fetch(resolvedUrl);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch volume: ${response.status} ${response.statusText}`,
    );
  }

  const rawBuffer = await response.arrayBuffer();
  if (url.endsWith(".gz")) {
    return gunzipBuffer(rawBuffer);
  }
  return rawBuffer;
}

export async function loadNiftiVolume(assetUrl: string) {
  const buffer = await fetchBuffer(assetUrl);
  const view = new DataView(buffer);

  const littleEndian =
    view.getInt32(0, true) === 348
      ? true
      : view.getInt32(0, false) === 348
        ? false
        : (() => {
            throw new Error("Invalid NIfTI header");
          })();

  const dimX = Math.max(view.getInt16(42, littleEndian), 1);
  const dimY = Math.max(view.getInt16(44, littleEndian), 1);
  const dimZ = Math.max(view.getInt16(46, littleEndian), 1);
  const datatype = view.getInt16(70, littleEndian);
  const voxOffset = Math.max(
    Math.floor(view.getFloat32(108, littleEndian)),
    352,
  );
  const scaleSlope = view.getFloat32(112, littleEndian) || 1;
  const scaleIntercept = view.getFloat32(116, littleEndian) || 0;
  const spacingX = Math.abs(view.getFloat32(80, littleEndian)) || 1;
  const spacingY = Math.abs(view.getFloat32(84, littleEndian)) || 1;
  const spacingZ = Math.abs(view.getFloat32(88, littleEndian)) || 1;

  const reader = getReader(datatype);
  const voxelCount = dimX * dimY * dimZ;
  const data = new Float32Array(voxelCount);

  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;

  for (let voxelIndex = 0; voxelIndex < voxelCount; voxelIndex += 1) {
    const offset = voxOffset + voxelIndex * reader.bytes;
    const rawValue = reader.read(view, offset, littleEndian);
    const scaledValue = rawValue * scaleSlope + scaleIntercept;
    data[voxelIndex] = scaledValue;
    if (scaledValue < min) {
      min = scaledValue;
    }
    if (scaledValue > max) {
      max = scaledValue;
    }
  }

  return {
    sourceUrl: assetUrl,
    dims: [dimX, dimY, dimZ],
    spacing: [spacingX, spacingY, spacingZ],
    data,
    min,
    max,
  } satisfies VolumeData;
}

export function buildWindowPresets(
  volume: VolumeData,
  modality: string | null | undefined,
) {
  const normalized = (modality || "").toLowerCase();
  if (normalized.includes("ct")) {
    const ctPresets = [
      { id: "brain", label: "Brain", center: 40, width: 80 },
      { id: "bone", label: "Bone", center: 300, width: 2000 },
      { id: "lung", label: "Lung", center: -600, width: 1500 },
      { id: "mediastinum", label: "Mediastinum", center: 40, width: 400 },
    ];

    return ctPresets.map((preset) => ({
      id: preset.id,
      label: preset.label,
      min: preset.center - preset.width / 2,
      max: preset.center + preset.width / 2,
    }));
  }

  const [p01, p1, p10, p25, p75, p90, p99] = estimatePercentiles(
    volume.data,
    [0.01, 0.05, 0.1, 0.25, 0.75, 0.9, 0.99],
  );

  return [
    { id: "auto", label: "Auto", min: p01, max: p99 },
    { id: "soft-tissue", label: "Soft tissue", min: p1, max: p90 },
    { id: "high-contrast", label: "High contrast", min: p25, max: p75 },
    { id: "wide", label: "Wide", min: p01, max: Math.max(p90, volume.max) },
  ] satisfies WindowPreset[];
}

function estimatePercentiles(data: Float32Array, percentiles: number[]) {
  const stride = Math.max(1, Math.floor(data.length / 120_000));
  const sample: number[] = [];

  for (let index = 0; index < data.length; index += stride) {
    const value = data[index];
    if (Number.isFinite(value)) {
      sample.push(value);
    }
  }

  sample.sort((left, right) => left - right);

  return percentiles.map((percentile) => {
    const clamped = clamp(percentile, 0, 1);
    const targetIndex = Math.floor((sample.length - 1) * clamped);
    return sample[targetIndex] ?? 0;
  });
}

function hexToRgb(hex: string) {
  const normalized = hex.replace("#", "");
  const value =
    normalized.length === 3
      ? normalized
          .split("")
          .map((character) => `${character}${character}`)
          .join("")
      : normalized;

  const numeric = Number.parseInt(value, 16);
  return {
    r: (numeric >> 16) & 255,
    g: (numeric >> 8) & 255,
    b: numeric & 255,
  };
}

export function getLabelColor(
  label: number,
  paletteId: PaletteId,
  legendMap: Map<number, string>,
) {
  if (paletteId === "legend") {
    return (
      legendMap.get(label) ||
      paletteMap.contrast[label % paletteMap.contrast.length]
    );
  }

  return paletteMap[paletteId][label % paletteMap[paletteId].length];
}

export function buildLegendColorMap(legend: SegmentLegendItem[]) {
  return new Map(legend.map((segment) => [segment.id, segment.color]));
}

export function deriveMaskLabels(maskVolume: VolumeData, limit = 18) {
  const labels = new Set<number>();
  for (let index = 0; index < maskVolume.data.length; index += 1) {
    const label = Math.round(maskVolume.data[index]);
    if (label > 0) {
      labels.add(label);
      if (labels.size >= limit) {
        break;
      }
    }
  }
  return Array.from(labels).sort((left, right) => left - right);
}

export function renderSliceToCanvas(options: {
  canvas: HTMLCanvasElement;
  imageVolume: VolumeData;
  maskVolume: VolumeData | null;
  visibleSegmentIds: Set<number>;
  plane: Plane;
  slices: { x: number; y: number; z: number };
  windowRange: { min: number; max: number };
  overlayOpacity: number;
  paletteId: PaletteId;
  legendMap: Map<number, string>;
  viewport: { zoom: number; panX: number; panY: number };
}) {
  const {
    canvas,
    imageVolume,
    maskVolume,
    visibleSegmentIds,
    plane,
    slices,
    windowRange,
    overlayOpacity,
    paletteId,
    legendMap,
    viewport,
  } = options;
  const { width, height } = getPlaneDimensions(imageVolume, plane);
  const displaySize = getPlaneDisplayDimensions(imageVolume, plane);
  const config = planeConfig[plane];
  const offscreen = document.createElement("canvas");
  offscreen.width = width;
  offscreen.height = height;
  const offscreenContext = offscreen.getContext("2d");
  const context = canvas.getContext("2d");

  if (!offscreenContext || !context) {
    return;
  }

  const imageData = offscreenContext.createImageData(width, height);
  const range = Math.max(windowRange.max - windowRange.min, 1e-6);

  for (let row = 0; row < height; row += 1) {
    for (let column = 0; column < width; column += 1) {
      const planeX = config.flipX ? width - 1 - column : column;
      const planeY = config.flipY ? height - 1 - row : row;
      const voxel = mapPlanePointToVoxel(plane, planeX, planeY, slices);
      const voxelIndex = getVoxelIndex(
        imageVolume.dims,
        voxel.x,
        voxel.y,
        voxel.z,
      );
      const intensity = imageVolume.data[voxelIndex];
      const normalized = clamp((intensity - windowRange.min) / range, 0, 1);
      const gray = Math.round(normalized * 255);

      let red = gray;
      let green = gray;
      let blue = gray;

      if (maskVolume) {
        const label = Math.round(maskVolume.data[voxelIndex]);
        if (label > 0 && visibleSegmentIds.has(label)) {
          const color = hexToRgb(getLabelColor(label, paletteId, legendMap));
          red = Math.round(
            gray * (1 - overlayOpacity) + color.r * overlayOpacity,
          );
          green = Math.round(
            gray * (1 - overlayOpacity) + color.g * overlayOpacity,
          );
          blue = Math.round(
            gray * (1 - overlayOpacity) + color.b * overlayOpacity,
          );
        }
      }

      const pixelIndex = (row * width + column) * 4;
      imageData.data[pixelIndex] = red;
      imageData.data[pixelIndex + 1] = green;
      imageData.data[pixelIndex + 2] = blue;
      imageData.data[pixelIndex + 3] = 255;
    }
  }

  offscreenContext.putImageData(imageData, 0, 0);

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#000000";
  context.fillRect(0, 0, canvas.width, canvas.height);

  const fitScale = Math.min(
    canvas.width / displaySize.width,
    canvas.height / displaySize.height,
  );
  const drawWidth = displaySize.width * fitScale * viewport.zoom;
  const drawHeight = displaySize.height * fitScale * viewport.zoom;
  const originX = (canvas.width - drawWidth) / 2 + viewport.panX;
  const originY = (canvas.height - drawHeight) / 2 + viewport.panY;

  context.imageSmoothingEnabled = false;
  context.drawImage(offscreen, originX, originY, drawWidth, drawHeight);

  const crosshair = mapCrosshairToPlane(plane, slices);
  const drawCrosshairX = config.flipX ? width - 1 - crosshair.x : crosshair.x;
  const drawCrosshairY = config.flipY ? height - 1 - crosshair.y : crosshair.y;
  const crosshairX = originX + ((drawCrosshairX + 0.5) / width) * drawWidth;
  const crosshairY = originY + ((drawCrosshairY + 0.5) / height) * drawHeight;

  context.strokeStyle = "rgba(148, 163, 184, 0.72)";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(originX, crosshairY);
  context.lineTo(originX + drawWidth, crosshairY);
  context.moveTo(crosshairX, originY);
  context.lineTo(crosshairX, originY + drawHeight);
  context.stroke();

  context.fillStyle = "rgba(15, 23, 42, 0.72)";
  context.fillRect(12, 12, 132, 34);
  context.fillStyle = "#f8fafc";
  context.font = "600 14px IBM Plex Sans, sans-serif";
  context.fillText(
    `${plane.toUpperCase()} ${getSliceLabel(plane, slices)}`,
    24,
    34,
  );

  const orientation = getPlaneOrientation(plane);
  context.font = "600 13px IBM Plex Sans, sans-serif";
  context.fillStyle = "#e2e8f0";
  context.fillText(orientation.left, 14, canvas.height / 2);
  context.fillText(orientation.right, canvas.width - 24, canvas.height / 2);
  context.fillText(orientation.top, canvas.width / 2 - 4, 22);
  context.fillText(
    orientation.bottom,
    canvas.width / 2 - 4,
    canvas.height - 14,
  );
}

export function getSliceLabel(
  plane: Plane,
  slices: { x: number; y: number; z: number },
) {
  if (plane === "axial") {
    return slices.z + 1;
  }
  if (plane === "coronal") {
    return slices.y + 1;
  }
  return slices.x + 1;
}

export function pointerToVoxel(options: {
  canvas: HTMLCanvasElement;
  plane: Plane;
  imageVolume: VolumeData;
  slices: { x: number; y: number; z: number };
  viewport: { zoom: number; panX: number; panY: number };
  clientX: number;
  clientY: number;
}) {
  const { canvas, plane, imageVolume, slices, viewport, clientX, clientY } =
    options;
  const { width, height } = getPlaneDimensions(imageVolume, plane);
  const displaySize = getPlaneDisplayDimensions(imageVolume, plane);
  const config = planeConfig[plane];
  const rect = canvas.getBoundingClientRect();
  const canvasX = ((clientX - rect.left) / rect.width) * canvas.width;
  const canvasY = ((clientY - rect.top) / rect.height) * canvas.height;
  const fitScale = Math.min(
    canvas.width / displaySize.width,
    canvas.height / displaySize.height,
  );
  const drawWidth = displaySize.width * fitScale * viewport.zoom;
  const drawHeight = displaySize.height * fitScale * viewport.zoom;
  const originX = (canvas.width - drawWidth) / 2 + viewport.panX;
  const originY = (canvas.height - drawHeight) / 2 + viewport.panY;

  if (
    canvasX < originX ||
    canvasX > originX + drawWidth ||
    canvasY < originY ||
    canvasY > originY + drawHeight
  ) {
    return null;
  }

  const planeX = clamp(
    Math.floor(((canvasX - originX) / drawWidth) * width),
    0,
    width - 1,
  );
  const planeY = clamp(
    Math.floor(((canvasY - originY) / drawHeight) * height),
    0,
    height - 1,
  );
  const normalizedX = config.flipX ? width - 1 - planeX : planeX;
  const normalizedY = config.flipY ? height - 1 - planeY : planeY;
  return mapPlanePointToVoxel(plane, normalizedX, normalizedY, slices);
}
