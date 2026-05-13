export function buildQuantityResult({
  acceptedDetectionAreaM2,
  addedCorrectionAreaM2,
  subtractedCorrectionAreaM2,
  confirmedHeightM,
}) {
  const final_area_m2 =
    Number(acceptedDetectionAreaM2 || 0) +
    Number(addedCorrectionAreaM2 || 0) -
    Number(subtractedCorrectionAreaM2 || 0)
  const volume_m3 = final_area_m2 * Number(confirmedHeightM || 0)
  return {
    calculation_source: 'deterministic_quantity_engine',
    final_area_m2,
    volume_m3,
  }
}
