import type { SegmentLegendItem } from "@/types/api";

export const DEMO_STUDY_ID = "demo";
export const DEMO_STUDY_VIEWER_HREF = `/studies/${DEMO_STUDY_ID}/viewer`;
export const DEMO_STUDY_CREATED_AT = "2099-01-01T00:00:00.000Z";

export const DEMO_STUDY_CASE_TITLE = "Demo: Esclerose múltipla";
export const DEMO_STUDY_PATIENT_NAME = "Paciente demo - Esclerose múltipla";
export const DEMO_STUDY_CATEGORY = "head_esclerose_multipla";
export const DEMO_STUDY_MODALITY = "MRI";

export const DEMO_STUDY_IMAGE_URL = "/site/demo/original_image.nii.gz";
export const DEMO_STUDY_MASK_URL = "/site/demo/mask.nii.gz";

export const DEMO_STUDY_SEGMENTS_LEGEND: SegmentLegendItem[] = [
  {
    id: 1,
    label: "Lesão de esclerose múltipla",
    prompt: "multiple sclerosis lesion",
    voxels: 0,
    fraction: 0,
    percentage: 0,
    color: "#0a84ff",
  },
];

export const DEMO_STUDY_ANALYSIS =
  "Este é um estudo de demonstração para visualização de segmentação de lesão de esclerose múltipla.";
