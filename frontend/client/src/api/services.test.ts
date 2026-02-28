import { describe, expect, it } from "vitest";
import {
  buildStudyUploadFormData,
  pickUploadFieldName,
} from "@/api/services";

describe("pickUploadFieldName", () => {
  it("maps ZIP uploads to dicom_zip", () => {
    expect(pickUploadFieldName("study.zip")).toBe("dicom_zip");
  });

  it("maps NPZ uploads to npz_file", () => {
    expect(pickUploadFieldName("study.npz")).toBe("npz_file");
  });

  it("maps NIfTI uploads to nifti_file", () => {
    expect(pickUploadFieldName("study.nii.gz")).toBe("nifti_file");
  });
});

describe("buildStudyUploadFormData", () => {
  it("writes modality and category_id exactly as backend expects", () => {
    const formData = buildStudyUploadFormData({
      file: new File(["demo"], "brain.nii.gz"),
      caseIdentification: "CASE-001",
      patientName: "Maria Silva",
      age: 58,
      examSource: "Hospital Sao Pedro",
      examModality: "MRI",
      categoryId: "head",
    });

    expect(formData.get("exam_modality")).toBe("MRI");
    expect(formData.get("category_id")).toBe("head");
    expect(formData.get("patient_name")).toBe("Maria Silva");
  });
});
