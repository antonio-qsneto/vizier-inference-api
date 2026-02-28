import { clamp, type VolumeData, type WindowPreset } from "@/viewer/nifti";

export type VolumeRenderMode = "surface" | "mip";

export interface VolumeRenderProfile {
  id: string;
  label: string;
  mode: VolumeRenderMode;
  threshold: number;
  exposure: number;
  quality: number;
  color: [number, number, number];
}

export interface PreparedVolume3D {
  dims: [number, number, number];
  data: Uint8Array;
  boxSize: [number, number, number];
  maxDimension: number;
}

export interface VolumeCameraState {
  yaw: number;
  pitch: number;
  zoom: number;
  panX: number;
  panY: number;
}

export interface VolumeRenderSettings {
  mode: VolumeRenderMode;
  threshold: number;
  exposure: number;
  quality: number;
  color: [number, number, number];
  targetHeight: number;
}

type Vec3 = [number, number, number];

const CT_VOLUME_PROFILES: VolumeRenderProfile[] = [
  {
    id: "ct-bone",
    label: "CT Bone",
    mode: "surface",
    threshold: 0.58,
    exposure: 1.06,
    quality: 1.12,
    color: [238, 214, 184],
  },
  {
    id: "ct-soft-tissue",
    label: "CT Soft Tissue",
    mode: "surface",
    threshold: 0.24,
    exposure: 0.94,
    quality: 1,
    color: [196, 126, 117],
  },
  {
    id: "ct-mip",
    label: "CT MIP",
    mode: "mip",
    threshold: 0.34,
    exposure: 1.22,
    quality: 1.08,
    color: [203, 220, 255],
  },
];

const MRI_VOLUME_PROFILES: VolumeRenderProfile[] = [
  {
    id: "mri-soft",
    label: "MRI Soft Tissue",
    mode: "surface",
    threshold: 0.18,
    exposure: 1.02,
    quality: 1.04,
    color: [204, 199, 214],
  },
  {
    id: "mri-mip",
    label: "MRI MIP",
    mode: "mip",
    threshold: 0.2,
    exposure: 1.18,
    quality: 1.1,
    color: [188, 207, 245],
  },
];

export function buildVolumeRenderProfiles(modality: string | null | undefined) {
  const normalized = (modality || "").toLowerCase();
  if (normalized.includes("ct")) {
    return CT_VOLUME_PROFILES;
  }

  return MRI_VOLUME_PROFILES;
}

export function getDefaultVolumeRenderProfile(
  modality: string | null | undefined,
) {
  return buildVolumeRenderProfiles(modality)[0];
}

export function prepareVolumeFor3D(
  volume: VolumeData,
  windowRange: WindowPreset,
  maxSide = 160,
) {
  const [dimX, dimY, dimZ] = volume.dims;
  const [spacingX, spacingY, spacingZ] = volume.spacing;
  const maxInputDimension = Math.max(dimX, dimY, dimZ);
  const scaleFactor = Math.min(1, maxSide / maxInputDimension);
  const outDims: [number, number, number] = [
    Math.max(16, Math.round(dimX * scaleFactor)),
    Math.max(16, Math.round(dimY * scaleFactor)),
    Math.max(16, Math.round(dimZ * scaleFactor)),
  ];
  const outData = new Uint8Array(outDims[0] * outDims[1] * outDims[2]);
  const range = Math.max(windowRange.max - windowRange.min, 1e-6);
  const [outX, outY, outZ] = outDims;

  for (let z = 0; z < outZ; z += 1) {
    const sourceZ = Math.round((z / Math.max(outZ - 1, 1)) * (dimZ - 1));
    for (let y = 0; y < outY; y += 1) {
      const sourceY = Math.round((y / Math.max(outY - 1, 1)) * (dimY - 1));
      for (let x = 0; x < outX; x += 1) {
        const sourceX = Math.round((x / Math.max(outX - 1, 1)) * (dimX - 1));
        const sourceIndex = sourceX + sourceY * dimX + sourceZ * dimX * dimY;
        const normalized = clamp(
          (volume.data[sourceIndex] - windowRange.min) / range,
          0,
          1,
        );
        const targetIndex = x + y * outX + z * outX * outY;
        outData[targetIndex] = Math.round(normalized * 255);
      }
    }
  }

  const physicalSize: Vec3 = [
    dimX * spacingX,
    dimY * spacingY,
    dimZ * spacingZ,
  ];
  const maxPhysicalDimension = Math.max(...physicalSize, 1e-6);

  return {
    dims: outDims,
    data: outData,
    boxSize: [
      physicalSize[0] / maxPhysicalDimension,
      physicalSize[1] / maxPhysicalDimension,
      physicalSize[2] / maxPhysicalDimension,
    ],
    maxDimension: Math.max(...outDims),
  } satisfies PreparedVolume3D;
}

function addVec3(left: Vec3, right: Vec3): Vec3 {
  return [left[0] + right[0], left[1] + right[1], left[2] + right[2]];
}

function subtractVec3(left: Vec3, right: Vec3): Vec3 {
  return [left[0] - right[0], left[1] - right[1], left[2] - right[2]];
}

function scaleVec3(vector: Vec3, factor: number): Vec3 {
  return [vector[0] * factor, vector[1] * factor, vector[2] * factor];
}

function dotVec3(left: Vec3, right: Vec3) {
  return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

function crossVec3(left: Vec3, right: Vec3): Vec3 {
  return [
    left[1] * right[2] - left[2] * right[1],
    left[2] * right[0] - left[0] * right[2],
    left[0] * right[1] - left[1] * right[0],
  ];
}

function lengthVec3(vector: Vec3) {
  return Math.hypot(vector[0], vector[1], vector[2]);
}

function normalizeVec3(vector: Vec3): Vec3 {
  const length = lengthVec3(vector);
  if (!length) {
    return [0, 0, 0];
  }
  return scaleVec3(vector, 1 / length);
}

function samplePreparedVolume(
  volume: PreparedVolume3D,
  u: number,
  v: number,
  w: number,
) {
  const [dimX, dimY, dimZ] = volume.dims;
  const x = clamp(u, 0, 1) * (dimX - 1);
  const y = clamp(v, 0, 1) * (dimY - 1);
  const z = clamp(w, 0, 1) * (dimZ - 1);
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const z0 = Math.floor(z);
  const x1 = Math.min(x0 + 1, dimX - 1);
  const y1 = Math.min(y0 + 1, dimY - 1);
  const z1 = Math.min(z0 + 1, dimZ - 1);
  const tx = x - x0;
  const ty = y - y0;
  const tz = z - z0;

  const getValue = (sampleX: number, sampleY: number, sampleZ: number) =>
    volume.data[sampleX + sampleY * dimX + sampleZ * dimX * dimY] / 255;

  const c000 = getValue(x0, y0, z0);
  const c100 = getValue(x1, y0, z0);
  const c010 = getValue(x0, y1, z0);
  const c110 = getValue(x1, y1, z0);
  const c001 = getValue(x0, y0, z1);
  const c101 = getValue(x1, y0, z1);
  const c011 = getValue(x0, y1, z1);
  const c111 = getValue(x1, y1, z1);

  const c00 = c000 * (1 - tx) + c100 * tx;
  const c10 = c010 * (1 - tx) + c110 * tx;
  const c01 = c001 * (1 - tx) + c101 * tx;
  const c11 = c011 * (1 - tx) + c111 * tx;
  const c0 = c00 * (1 - ty) + c10 * ty;
  const c1 = c01 * (1 - ty) + c11 * ty;

  return c0 * (1 - tz) + c1 * tz;
}

function computeVolumeNormal(
  volume: PreparedVolume3D,
  u: number,
  v: number,
  w: number,
) {
  const du = 1 / Math.max(volume.dims[0] - 1, 1);
  const dv = 1 / Math.max(volume.dims[1] - 1, 1);
  const dw = 1 / Math.max(volume.dims[2] - 1, 1);
  const gx =
    samplePreparedVolume(volume, u + du, v, w) -
    samplePreparedVolume(volume, u - du, v, w);
  const gy =
    samplePreparedVolume(volume, u, v + dv, w) -
    samplePreparedVolume(volume, u, v - dv, w);
  const gz =
    samplePreparedVolume(volume, u, v, w + dw) -
    samplePreparedVolume(volume, u, v, w - dw);

  return normalizeVec3([
    gx / Math.max(volume.boxSize[0], 1e-6),
    gy / Math.max(volume.boxSize[1], 1e-6),
    gz / Math.max(volume.boxSize[2], 1e-6),
  ]);
}

function intersectRayWithBox(
  origin: Vec3,
  direction: Vec3,
  minPoint: Vec3,
  maxPoint: Vec3,
) {
  let tMin = -Infinity;
  let tMax = Infinity;

  for (let axis = 0; axis < 3; axis += 1) {
    const rayOrigin = origin[axis];
    const rayDirection = direction[axis];
    const boxMin = minPoint[axis];
    const boxMax = maxPoint[axis];

    if (Math.abs(rayDirection) < 1e-6) {
      if (rayOrigin < boxMin || rayOrigin > boxMax) {
        return null;
      }
      continue;
    }

    let near = (boxMin - rayOrigin) / rayDirection;
    let far = (boxMax - rayOrigin) / rayDirection;

    if (near > far) {
      [near, far] = [far, near];
    }

    tMin = Math.max(tMin, near);
    tMax = Math.min(tMax, far);

    if (tMin > tMax) {
      return null;
    }
  }

  if (tMax < 0) {
    return null;
  }

  return {
    start: Math.max(tMin, 0),
    end: tMax,
  };
}

function buildSurfaceColor(
  sample: number,
  normal: Vec3,
  rayDirection: Vec3,
  lightDirection: Vec3,
  profileColor: [number, number, number],
  exposure: number,
) {
  const viewDirection = scaleVec3(rayDirection, -1);
  const facingNormal =
    dotVec3(normal, viewDirection) < 0 ? scaleVec3(normal, -1) : normal;
  const diffuse = Math.max(dotVec3(facingNormal, lightDirection), 0);
  const halfVector = normalizeVec3(addVec3(lightDirection, viewDirection));
  const specular = Math.pow(Math.max(dotVec3(facingNormal, halfVector), 0), 24);
  const rim = Math.pow(
    1 - Math.max(dotVec3(facingNormal, viewDirection), 0),
    2,
  );
  const shade = 0.24 + diffuse * 0.94 + specular * 0.22 + rim * 0.16;
  const intensity = exposure * (0.55 + sample * 0.65) * shade;

  return [
    clamp(profileColor[0] * intensity, 0, 255),
    clamp(profileColor[1] * intensity, 0, 255),
    clamp(profileColor[2] * intensity, 0, 255),
  ];
}

function buildMipColor(
  sample: number,
  threshold: number,
  color: [number, number, number],
  exposure: number,
) {
  const mapped = clamp(
    (sample - threshold) / Math.max(1 - threshold, 1e-6),
    0,
    1,
  );
  const intensity = (0.25 + mapped * 0.95) * exposure;

  return [
    clamp(color[0] * intensity, 0, 255),
    clamp(color[1] * intensity, 0, 255),
    clamp(color[2] * intensity, 0, 255),
  ];
}

function yieldToBrowser() {
  return new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

export async function renderPreparedVolumeToCanvas(options: {
  canvas: HTMLCanvasElement;
  preparedVolume: PreparedVolume3D;
  camera: VolumeCameraState;
  settings: VolumeRenderSettings;
  shouldAbort: () => boolean;
}) {
  const { canvas, preparedVolume, camera, settings, shouldAbort } = options;
  const context = canvas.getContext("2d");

  if (!context) {
    return;
  }

  const aspect = canvas.width / Math.max(canvas.height, 1);
  const renderHeight = Math.max(180, settings.targetHeight);
  const renderWidth = Math.max(180, Math.round(renderHeight * aspect));
  const offscreen = document.createElement("canvas");
  offscreen.width = renderWidth;
  offscreen.height = renderHeight;
  const offscreenContext = offscreen.getContext("2d");

  if (!offscreenContext) {
    return;
  }

  const image = offscreenContext.createImageData(renderWidth, renderHeight);
  const { boxSize, maxDimension } = preparedVolume;
  const boxMin: Vec3 = [-boxSize[0] / 2, -boxSize[1] / 2, -boxSize[2] / 2];
  const boxMax: Vec3 = [boxSize[0] / 2, boxSize[1] / 2, boxSize[2] / 2];
  const distance = 1.65 / camera.zoom;
  const cameraTargetBase: Vec3 = [0, 0, 0];
  const cameraOrbitOffset: Vec3 = [
    Math.sin(camera.yaw) * Math.cos(camera.pitch) * distance,
    Math.sin(camera.pitch) * distance,
    Math.cos(camera.yaw) * Math.cos(camera.pitch) * distance,
  ];
  const cameraPositionBase = addVec3(cameraTargetBase, cameraOrbitOffset);
  const forwardBase = normalizeVec3(
    subtractVec3(cameraTargetBase, cameraPositionBase),
  );
  const rightBase = normalizeVec3(
    crossVec3(
      forwardBase,
      Math.abs(forwardBase[1]) > 0.98 ? [0, 0, 1] : [0, 1, 0],
    ),
  );
  const upBase = normalizeVec3(crossVec3(rightBase, forwardBase));
  const panOffset = addVec3(
    scaleVec3(rightBase, camera.panX),
    scaleVec3(upBase, camera.panY),
  );
  const cameraTarget = addVec3(cameraTargetBase, panOffset);
  const cameraPosition = addVec3(cameraPositionBase, panOffset);
  const forward = normalizeVec3(subtractVec3(cameraTarget, cameraPosition));
  const right = normalizeVec3(
    crossVec3(forward, Math.abs(forward[1]) > 0.98 ? [0, 0, 1] : [0, 1, 0]),
  );
  const up = normalizeVec3(crossVec3(right, forward));
  const fovScale = Math.tan((36 * Math.PI) / 180 / 2);
  const lightDirection = normalizeVec3([0.35, 0.45, 1]);
  const rayStep =
    1 /
    Math.max(
      maxDimension *
        settings.quality *
        (settings.mode === "surface" ? 0.92 : 0.66),
      1,
    );

  for (let y = 0; y < renderHeight; y += 1) {
    if (shouldAbort()) {
      return;
    }

    const ndcY = (1 - ((y + 0.5) / renderHeight) * 2) * fovScale;

    for (let x = 0; x < renderWidth; x += 1) {
      const ndcX = (((x + 0.5) / renderWidth) * 2 - 1) * aspect * fovScale;
      const rayDirection = normalizeVec3(
        addVec3(addVec3(forward, scaleVec3(right, ndcX)), scaleVec3(up, ndcY)),
      );
      const hit = intersectRayWithBox(
        cameraPosition,
        rayDirection,
        boxMin,
        boxMax,
      );
      const outputIndex = (y * renderWidth + x) * 4;

      image.data[outputIndex] = 0;
      image.data[outputIndex + 1] = 0;
      image.data[outputIndex + 2] = 0;
      image.data[outputIndex + 3] = 255;

      if (!hit) {
        continue;
      }

      if (settings.mode === "mip") {
        let maximumSample = 0;

        for (let t = hit.start; t <= hit.end; t += rayStep) {
          const point = addVec3(cameraPosition, scaleVec3(rayDirection, t));
          const u = (point[0] - boxMin[0]) / boxSize[0];
          const v = (point[1] - boxMin[1]) / boxSize[1];
          const w = (point[2] - boxMin[2]) / boxSize[2];
          maximumSample = Math.max(
            maximumSample,
            samplePreparedVolume(preparedVolume, u, v, w),
          );
        }

        if (maximumSample > settings.threshold) {
          const [red, green, blue] = buildMipColor(
            maximumSample,
            settings.threshold,
            settings.color,
            settings.exposure,
          );
          image.data[outputIndex] = red;
          image.data[outputIndex + 1] = green;
          image.data[outputIndex + 2] = blue;
        }

        continue;
      }

      for (let t = hit.start; t <= hit.end; t += rayStep) {
        const point = addVec3(cameraPosition, scaleVec3(rayDirection, t));
        const u = (point[0] - boxMin[0]) / boxSize[0];
        const v = (point[1] - boxMin[1]) / boxSize[1];
        const w = (point[2] - boxMin[2]) / boxSize[2];
        const sample = samplePreparedVolume(preparedVolume, u, v, w);

        if (sample < settings.threshold) {
          continue;
        }

        const normal = computeVolumeNormal(preparedVolume, u, v, w);
        const [red, green, blue] = buildSurfaceColor(
          sample,
          normal,
          rayDirection,
          lightDirection,
          settings.color,
          settings.exposure,
        );

        image.data[outputIndex] = red;
        image.data[outputIndex + 1] = green;
        image.data[outputIndex + 2] = blue;
        break;
      }
    }

    if (y % 10 === 0) {
      await yieldToBrowser();
    }
  }

  if (shouldAbort()) {
    return;
  }

  offscreenContext.putImageData(image, 0, 0);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#000000";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.imageSmoothingEnabled = true;
  context.drawImage(offscreen, 0, 0, canvas.width, canvas.height);
}
