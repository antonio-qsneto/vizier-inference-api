import { normalizeViewerAssetUrl } from "@/lib/viewer-url";
import type { SegmentLegendItem } from "@/types/api";

export type Plane = "axial" | "coronal" | "sagittal";
export type PaletteId = "legend" | "teal" | "warm" | "contrast";

export interface VolumeData {
  sourceUrl: string;
  dims: [number, number, number];
  spacing: [number, number, number];
  affine: [
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
  ];
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
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

const planeConfig = {
  axial: {
    axes: ["x", "y", "z"] as const,
    defaultFlipX: true,
    defaultFlipY: true,
    preferredOrientation: { left: "R", right: "L", top: "A", bottom: "P" },
  },
  coronal: {
    axes: ["x", "z", "y"] as const,
    defaultFlipX: true,
    defaultFlipY: true,
    preferredOrientation: { left: "R", right: "L", top: "S", bottom: "I" },
  },
  sagittal: {
    axes: ["y", "z", "x"] as const,
    defaultFlipX: false,
    defaultFlipY: true,
    preferredOrientation: { left: "A", right: "P", top: "S", bottom: "I" },
  },
} satisfies Record<
  Plane,
  {
    axes: readonly ["x" | "y", "y" | "z", "x" | "y" | "z"];
    defaultFlipX: boolean;
    defaultFlipY: boolean;
    preferredOrientation: {
      left: string;
      right: string;
      top: string;
      bottom: string;
    };
  }
>;

const orientationOpposites: Record<string, string> = {
  R: "L",
  L: "R",
  A: "P",
  P: "A",
  S: "I",
  I: "S",
};

type PlaneDisplayConfig = {
  flipX: boolean;
  flipY: boolean;
  orientation: { left: string; right: string; top: string; bottom: string };
};

type AxisKey = "x" | "y" | "z";

function buildFallbackAffine(
  spacingX: number,
  spacingY: number,
  spacingZ: number,
): VolumeData["affine"] {
  return [
    spacingX,
    0,
    0,
    0,
    0,
    spacingY,
    0,
    0,
    0,
    0,
    spacingZ,
    0,
    0,
    0,
    0,
    1,
  ];
}

function readSformAffine(
  view: DataView,
  littleEndian: boolean,
): VolumeData["affine"] | null {
  const sformCode = view.getInt16(254, littleEndian);
  if (sformCode <= 0) {
    return null;
  }

  const raw = [
    view.getFloat32(280, littleEndian),
    view.getFloat32(284, littleEndian),
    view.getFloat32(288, littleEndian),
    view.getFloat32(292, littleEndian),
    view.getFloat32(296, littleEndian),
    view.getFloat32(300, littleEndian),
    view.getFloat32(304, littleEndian),
    view.getFloat32(308, littleEndian),
    view.getFloat32(312, littleEndian),
    view.getFloat32(316, littleEndian),
    view.getFloat32(320, littleEndian),
    view.getFloat32(324, littleEndian),
  ];

  if (!raw.every((value) => Number.isFinite(value))) {
    return null;
  }

  return [
    raw[0],
    raw[1],
    raw[2],
    raw[3],
    raw[4],
    raw[5],
    raw[6],
    raw[7],
    raw[8],
    raw[9],
    raw[10],
    raw[11],
    0,
    0,
    0,
    1,
  ];
}

function readQformAffine(
  view: DataView,
  littleEndian: boolean,
  spacingX: number,
  spacingY: number,
  spacingZ: number,
): VolumeData["affine"] | null {
  const qformCode = view.getInt16(252, littleEndian);
  if (qformCode <= 0) {
    return null;
  }

  let b = view.getFloat32(256, littleEndian);
  let c = view.getFloat32(260, littleEndian);
  let d = view.getFloat32(264, littleEndian);
  if (![b, c, d].every((value) => Number.isFinite(value))) {
    return null;
  }

  const xOffset = view.getFloat32(268, littleEndian);
  const yOffset = view.getFloat32(272, littleEndian);
  const zOffset = view.getFloat32(276, littleEndian);
  if (![xOffset, yOffset, zOffset].every((value) => Number.isFinite(value))) {
    return null;
  }

  const qfacRaw = view.getFloat32(76, littleEndian);
  const qfac = Number.isFinite(qfacRaw) && qfacRaw < 0 ? -1 : 1;

  let aSquared = 1.0 - (b * b + c * c + d * d);
  let a = aSquared > 1e-7 ? Math.sqrt(aSquared) : 0;
  if (a === 0) {
    const magnitude = Math.sqrt(b * b + c * c + d * d);
    if (magnitude > 1e-8) {
      b /= magnitude;
      c /= magnitude;
      d /= magnitude;
      aSquared = 0;
    } else {
      b = 0;
      c = 0;
      d = 0;
      aSquared = 1;
    }
    a = Math.sqrt(Math.max(aSquared, 0));
  }

  const r11 = a * a + b * b - c * c - d * d;
  const r12 = 2 * (b * c - a * d);
  const r13 = 2 * (b * d + a * c);
  const r21 = 2 * (b * c + a * d);
  const r22 = a * a + c * c - b * b - d * d;
  const r23 = 2 * (c * d - a * b);
  const r31 = 2 * (b * d - a * c);
  const r32 = 2 * (c * d + a * b);
  const r33 = a * a + d * d - b * b - c * c;

  const dz = spacingZ * qfac;
  const raw = [
    r11 * spacingX,
    r12 * spacingY,
    r13 * dz,
    xOffset,
    r21 * spacingX,
    r22 * spacingY,
    r23 * dz,
    yOffset,
    r31 * spacingX,
    r32 * spacingY,
    r33 * dz,
    zOffset,
  ];
  if (!raw.every((value) => Number.isFinite(value))) {
    return null;
  }

  return [
    raw[0],
    raw[1],
    raw[2],
    raw[3],
    raw[4],
    raw[5],
    raw[6],
    raw[7],
    raw[8],
    raw[9],
    raw[10],
    raw[11],
    0,
    0,
    0,
    1,
  ];
}

function readNiftiAffine(
  view: DataView,
  littleEndian: boolean,
  spacingX: number,
  spacingY: number,
  spacingZ: number,
): VolumeData["affine"] {
  return (
    readSformAffine(view, littleEndian) ||
    readQformAffine(view, littleEndian, spacingX, spacingY, spacingZ) ||
    buildFallbackAffine(spacingX, spacingY, spacingZ)
  );
}

function getVolumeAxisVector(volume: VolumeData, axis: AxisKey) {
  const axisIndex = axis === "x" ? 0 : axis === "y" ? 1 : 2;
  return [
    volume.affine[axisIndex],
    volume.affine[4 + axisIndex],
    volume.affine[8 + axisIndex],
  ] as [number, number, number];
}

function negateVector3(vector: [number, number, number]): [number, number, number] {
  return [-vector[0], -vector[1], -vector[2]];
}

function orientationLabelForVector(vector: [number, number, number]) {
  const [x, y, z] = vector;
  if (![x, y, z].every((value) => Number.isFinite(value))) {
    return "?";
  }

  const absX = Math.abs(x);
  const absY = Math.abs(y);
  const absZ = Math.abs(z);
  if (absX >= absY && absX >= absZ) {
    return x >= 0 ? "R" : "L";
  }
  if (absY >= absX && absY >= absZ) {
    return y >= 0 ? "A" : "P";
  }
  return z >= 0 ? "S" : "I";
}

function oppositeOrientationLabel(label: string) {
  return orientationOpposites[label] || label;
}

function computeOrientationLabels(
  horizontalAxis: [number, number, number],
  verticalAxis: [number, number, number],
  flipX: boolean,
  flipY: boolean,
) {
  const rightLabel = orientationLabelForVector(
    flipX ? negateVector3(horizontalAxis) : horizontalAxis,
  );
  const bottomLabel = orientationLabelForVector(
    flipY ? negateVector3(verticalAxis) : verticalAxis,
  );
  return {
    left: oppositeOrientationLabel(rightLabel),
    right: rightLabel,
    top: oppositeOrientationLabel(bottomLabel),
    bottom: bottomLabel,
  };
}

function scoreOrientation(
  candidate: { left: string; right: string; top: string; bottom: string },
  preferred: { left: string; right: string; top: string; bottom: string },
) {
  let score = 0;
  if (candidate.left === preferred.left) {
    score += 1;
  }
  if (candidate.right === preferred.right) {
    score += 1;
  }
  if (candidate.top === preferred.top) {
    score += 1;
  }
  if (candidate.bottom === preferred.bottom) {
    score += 1;
  }
  return score;
}

function getPlaneDisplayConfig(
  volume: VolumeData,
  plane: Plane,
): PlaneDisplayConfig {
  const config = planeConfig[plane];
  const horizontalAxis = getVolumeAxisVector(volume, config.axes[0]);
  const verticalAxis = getVolumeAxisVector(volume, config.axes[1]);

  let best: {
    flipX: boolean;
    flipY: boolean;
    orientation: { left: string; right: string; top: string; bottom: string };
    score: number;
    defaultDistance: number;
  } | null = null;

  for (const flipX of [false, true]) {
    for (const flipY of [false, true]) {
      const orientation = computeOrientationLabels(
        horizontalAxis,
        verticalAxis,
        flipX,
        flipY,
      );
      const score = scoreOrientation(orientation, config.preferredOrientation);
      const defaultDistance =
        (flipX === config.defaultFlipX ? 0 : 1) +
        (flipY === config.defaultFlipY ? 0 : 1);

      if (!best) {
        best = { flipX, flipY, orientation, score, defaultDistance };
        continue;
      }

      if (score > best.score) {
        best = { flipX, flipY, orientation, score, defaultDistance };
        continue;
      }

      if (score === best.score && defaultDistance < best.defaultDistance) {
        best = { flipX, flipY, orientation, score, defaultDistance };
      }
    }
  }

  if (!best) {
    return {
      flipX: config.defaultFlipX,
      flipY: config.defaultFlipY,
      orientation: config.preferredOrientation,
    };
  }

  return {
    flipX: best.flipX,
    flipY: best.flipY,
    orientation: best.orientation,
  };
}

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

export function getPlaneOrientation(volume: VolumeData, plane: Plane) {
  return getPlaneDisplayConfig(volume, plane).orientation;
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

function isHexColor(value: string) {
  return HEX_COLOR_PATTERN.test(value.trim());
}

function paletteIndexForLabel(label: number, paletteSize: number) {
  if (paletteSize <= 0) {
    return 0;
  }
  const normalized = Math.max(1, Math.round(label));
  return (normalized - 1) % paletteSize;
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

function hasGzipExtension(targetUrl: string) {
  try {
    const parsed = new URL(targetUrl, window.location.origin);
    return parsed.pathname.toLowerCase().endsWith(".gz");
  } catch {
    return targetUrl.split("?")[0].toLowerCase().endsWith(".gz");
  }
}

function isGzipPayload(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  return bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
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
  const shouldGunzip =
    hasGzipExtension(url) ||
    hasGzipExtension(resolvedUrl) ||
    isGzipPayload(rawBuffer);
  if (shouldGunzip) {
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
  const affine = readNiftiAffine(
    view,
    littleEndian,
    spacingX,
    spacingY,
    spacingZ,
  );

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
    affine,
    data,
    min,
    max,
  } satisfies VolumeData;
}

export function resampleMaskVolumeToDims(
  maskVolume: VolumeData,
  targetDims: [number, number, number],
): VolumeData {
  const [srcX, srcY, srcZ] = maskVolume.dims;
  const [dstX, dstY, dstZ] = targetDims;

  if (srcX === dstX && srcY === dstY && srcZ === dstZ) {
    return maskVolume;
  }

  const dstVoxelCount = dstX * dstY * dstZ;
  const nextData = new Float32Array(dstVoxelCount);

  const mapIndex = (targetIndex: number, targetSize: number, sourceSize: number) => {
    if (targetSize <= 1 || sourceSize <= 1) {
      return 0;
    }
    return Math.round((targetIndex * (sourceSize - 1)) / (targetSize - 1));
  };

  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;

  for (let z = 0; z < dstZ; z += 1) {
    const srcZi = mapIndex(z, dstZ, srcZ);
    for (let y = 0; y < dstY; y += 1) {
      const srcYi = mapIndex(y, dstY, srcY);
      for (let x = 0; x < dstX; x += 1) {
        const srcXi = mapIndex(x, dstX, srcX);
        const srcIndex = getVoxelIndex(maskVolume.dims, srcXi, srcYi, srcZi);
        const dstIndex = x + y * dstX + z * dstX * dstY;
        const value = maskVolume.data[srcIndex];
        nextData[dstIndex] = value;
        if (value < min) {
          min = value;
        }
        if (value > max) {
          max = value;
        }
      }
    }
  }

  return {
    sourceUrl: `${maskVolume.sourceUrl}#resampled`,
    dims: [dstX, dstY, dstZ],
    spacing: maskVolume.spacing,
    affine: maskVolume.affine,
    data: nextData,
    min,
    max,
  };
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

function boostOverlayColor(color: { r: number; g: number; b: number }) {
  // Keep colors vivid and readable over grayscale background.
  return {
    r: clamp(Math.round(color.r * 1.18 + 16), 0, 255),
    g: clamp(Math.round(color.g * 1.18 + 16), 0, 255),
    b: clamp(Math.round(color.b * 1.18 + 16), 0, 255),
  };
}

function mixColor(
  source: { r: number; g: number; b: number },
  target: { r: number; g: number; b: number },
  targetWeight: number,
) {
  const clampedWeight = clamp(targetWeight, 0, 1);
  const sourceWeight = 1 - clampedWeight;
  return {
    r: Math.round(source.r * sourceWeight + target.r * clampedWeight),
    g: Math.round(source.g * sourceWeight + target.g * clampedWeight),
    b: Math.round(source.b * sourceWeight + target.b * clampedWeight),
  };
}

function countMatchingNeighbors(
  labels: Int32Array,
  width: number,
  height: number,
  row: number,
  column: number,
  label: number,
) {
  let matches = 0;
  for (let deltaY = -1; deltaY <= 1; deltaY += 1) {
    for (let deltaX = -1; deltaX <= 1; deltaX += 1) {
      if (deltaX === 0 && deltaY === 0) {
        continue;
      }
      const nextRow = row + deltaY;
      const nextColumn = column + deltaX;
      if (
        nextRow < 0 ||
        nextRow >= height ||
        nextColumn < 0 ||
        nextColumn >= width
      ) {
        continue;
      }
      const nextIndex = nextRow * width + nextColumn;
      if (labels[nextIndex] === label) {
        matches += 1;
      }
    }
  }
  return matches;
}

function isBoundaryPixel(
  labels: Int32Array,
  width: number,
  height: number,
  row: number,
  column: number,
  label: number,
) {
  for (let deltaY = -1; deltaY <= 1; deltaY += 1) {
    for (let deltaX = -1; deltaX <= 1; deltaX += 1) {
      if (deltaX === 0 && deltaY === 0) {
        continue;
      }
      const nextRow = row + deltaY;
      const nextColumn = column + deltaX;
      if (
        nextRow < 0 ||
        nextRow >= height ||
        nextColumn < 0 ||
        nextColumn >= width
      ) {
        return true;
      }
      const nextIndex = nextRow * width + nextColumn;
      if (labels[nextIndex] !== label) {
        return true;
      }
    }
  }
  return false;
}

function appendContourSegment(
  segments: number[],
  x1: number,
  y1: number,
  x2: number,
  y2: number,
) {
  segments.push(x1, y1, x2, y2);
}

function extractContourSegmentsForLabel(
  labelData: Int32Array,
  width: number,
  height: number,
  label: number,
) {
  const segments: number[] = [];
  if (width < 2 || height < 2) {
    return segments;
  }

  for (let row = 0; row < height - 1; row += 1) {
    const nextRow = row + 1;
    for (let column = 0; column < width - 1; column += 1) {
      const nextColumn = column + 1;
      const topLeft = labelData[row * width + column] === label;
      const topRight = labelData[row * width + nextColumn] === label;
      const bottomRight = labelData[nextRow * width + nextColumn] === label;
      const bottomLeft = labelData[nextRow * width + column] === label;

      const mask =
        (topLeft ? 8 : 0) |
        (topRight ? 4 : 0) |
        (bottomRight ? 2 : 0) |
        (bottomLeft ? 1 : 0);

      if (mask === 0 || mask === 15) {
        continue;
      }

      const topX = column + 0.5;
      const topY = row;
      const rightX = nextColumn;
      const rightY = row + 0.5;
      const bottomX = column + 0.5;
      const bottomY = nextRow;
      const leftX = column;
      const leftY = row + 0.5;

      switch (mask) {
        case 1:
          appendContourSegment(segments, leftX, leftY, bottomX, bottomY);
          break;
        case 2:
          appendContourSegment(segments, bottomX, bottomY, rightX, rightY);
          break;
        case 3:
          appendContourSegment(segments, leftX, leftY, rightX, rightY);
          break;
        case 4:
          appendContourSegment(segments, topX, topY, rightX, rightY);
          break;
        case 5:
          appendContourSegment(segments, topX, topY, rightX, rightY);
          appendContourSegment(segments, leftX, leftY, bottomX, bottomY);
          break;
        case 6:
          appendContourSegment(segments, topX, topY, bottomX, bottomY);
          break;
        case 7:
          appendContourSegment(segments, topX, topY, leftX, leftY);
          break;
        case 8:
          appendContourSegment(segments, topX, topY, leftX, leftY);
          break;
        case 9:
          appendContourSegment(segments, topX, topY, bottomX, bottomY);
          break;
        case 10:
          appendContourSegment(segments, topX, topY, leftX, leftY);
          appendContourSegment(segments, rightX, rightY, bottomX, bottomY);
          break;
        case 11:
          appendContourSegment(segments, topX, topY, rightX, rightY);
          break;
        case 12:
          appendContourSegment(segments, leftX, leftY, rightX, rightY);
          break;
        case 13:
          appendContourSegment(segments, rightX, rightY, bottomX, bottomY);
          break;
        case 14:
          appendContourSegment(segments, leftX, leftY, bottomX, bottomY);
          break;
        default:
          break;
      }
    }
  }

  return segments;
}

export function getLabelColor(
  label: number,
  paletteId: PaletteId,
  legendMap: Map<number, string>,
) {
  if (paletteId === "legend") {
    const fallbackPalette = paletteMap.contrast;
    return (
      legendMap.get(label) ||
      fallbackPalette[paletteIndexForLabel(label, fallbackPalette.length)]
    );
  }

  const palette = paletteMap[paletteId];
  return palette[paletteIndexForLabel(label, palette.length)];
}

export function buildLegendColorMap(legend: SegmentLegendItem[]) {
  const normalized = new Map<number, string>();
  for (const segment of legend) {
    const id = Number(segment.id);
    const color = String(segment.color || "").trim();
    if (!Number.isFinite(id) || id <= 0 || !isHexColor(color)) {
      continue;
    }
    normalized.set(Math.round(id), color);
  }
  return normalized;
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
  const config = getPlaneDisplayConfig(imageVolume, plane);
  const offscreen = document.createElement("canvas");
  offscreen.width = width;
  offscreen.height = height;
  const offscreenContext = offscreen.getContext("2d");
  const context = canvas.getContext("2d");

  if (!offscreenContext || !context) {
    return;
  }

  const imageData = offscreenContext.createImageData(width, height);
  const overlayData = offscreenContext.createImageData(width, height);
  const labelData = new Int32Array(width * height);
  const presentLabels = new Set<number>();
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
          labelData[row * width + column] = label;
          presentLabels.add(label);
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

  if (maskVolume) {
    for (let row = 0; row < height; row += 1) {
      for (let column = 0; column < width; column += 1) {
        const bufferIndex = row * width + column;
        const label = labelData[bufferIndex];
        if (label <= 0) {
          continue;
        }

        const baseColor = hexToRgb(getLabelColor(label, paletteId, legendMap));
        const vividColor = boostOverlayColor(baseColor);
        const matchingNeighbors = countMatchingNeighbors(
          labelData,
          width,
          height,
          row,
          column,
          label,
        );
        const isBoundary = isBoundaryPixel(
          labelData,
          width,
          height,
          row,
          column,
          label,
        );
        const smoothFactor = matchingNeighbors / 8;
        const alphaScale = isBoundary
          ? 0.32 + smoothFactor * 0.52
          : 0.6 + smoothFactor * 0.34;
        const softAlpha = clamp(
          Math.round(overlayOpacity * 255 * alphaScale),
          22,
          238,
        );

        const pixelIndex = bufferIndex * 4;
        overlayData.data[pixelIndex] = vividColor.r;
        overlayData.data[pixelIndex + 1] = vividColor.g;
        overlayData.data[pixelIndex + 2] = vividColor.b;
        overlayData.data[pixelIndex + 3] = softAlpha;

      }
    }
  }

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

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(offscreen, originX, originY, drawWidth, drawHeight);

  if (maskVolume) {
    const overlayCanvas = document.createElement("canvas");
    overlayCanvas.width = width;
    overlayCanvas.height = height;
    const overlayContext = overlayCanvas.getContext("2d");
    if (overlayContext) {
      overlayContext.putImageData(overlayData, 0, 0);
      context.save();
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.filter = "blur(0.55px) saturate(1.12)";
      context.drawImage(overlayCanvas, originX, originY, drawWidth, drawHeight);
      context.restore();

      context.save();
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.globalAlpha = 0.44;
      context.drawImage(overlayCanvas, originX, originY, drawWidth, drawHeight);
      context.restore();
    }

    if (presentLabels.size > 0) {
      const sortedLabels = Array.from(presentLabels).sort((left, right) => left - right);
      const scaleX = drawWidth / width;
      const scaleY = drawHeight / height;
      const avgScale = Math.max((Math.abs(scaleX) + Math.abs(scaleY)) / 2, 1e-6);
      const white = { r: 255, g: 255, b: 255 };

      context.save();
      context.translate(originX, originY);
      context.scale(scaleX, scaleY);
      context.lineCap = "round";
      context.lineJoin = "round";

      for (const label of sortedLabels) {
        const segments = extractContourSegmentsForLabel(labelData, width, height, label);
        if (!segments.length) {
          continue;
        }

        const baseColor = hexToRgb(getLabelColor(label, paletteId, legendMap));
        const vividColor = boostOverlayColor(baseColor);
        const contourColor = mixColor(vividColor, white, 0.18);
        const crispLineWidth = clamp(1.9 / avgScale, 0.7, 2.4);
        const glowLineWidth = clamp(3.1 / avgScale, 1.1, 3.8);

        context.beginPath();
        for (let index = 0; index < segments.length; index += 4) {
          context.moveTo(segments[index], segments[index + 1]);
          context.lineTo(segments[index + 2], segments[index + 3]);
        }

        context.strokeStyle = `rgba(${contourColor.r}, ${contourColor.g}, ${contourColor.b}, 0.3)`;
        context.lineWidth = glowLineWidth;
        context.stroke();

        context.strokeStyle = `rgba(${contourColor.r}, ${contourColor.g}, ${contourColor.b}, 0.97)`;
        context.lineWidth = crispLineWidth;
        context.stroke();
      }

      context.restore();
    }
  }

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

  const orientation = getPlaneOrientation(imageVolume, plane);
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
  const config = getPlaneDisplayConfig(imageVolume, plane);
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
