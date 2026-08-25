import { describe, expect, it } from 'vitest'
import { buildQuantityResult } from './quantityEngine'

describe('buildQuantityResult', () => {
  it('final_area_m2 = accepted + added - subtracted', () => {
    const result = buildQuantityResult({
      acceptedDetectionAreaM2: 10,
      addedCorrectionAreaM2: 2.5,
      subtractedCorrectionAreaM2: 1.5,
      confirmedHeightM: 0,
    })
    expect(result.final_area_m2).toBe(11)
  })

  it('volume_m3 = final_area_m2 x confirmed_height_m', () => {
    const result = buildQuantityResult({
      acceptedDetectionAreaM2: 10,
      addedCorrectionAreaM2: 0,
      subtractedCorrectionAreaM2: 0,
      confirmedHeightM: 3,
    })
    expect(result.final_area_m2).toBe(10)
    expect(result.volume_m3).toBe(30)
  })

  it('combines both formulas together', () => {
    const result = buildQuantityResult({
      acceptedDetectionAreaM2: 20,
      addedCorrectionAreaM2: 5,
      subtractedCorrectionAreaM2: 3,
      confirmedHeightM: 2.5,
    })
    // final_area_m2 = 20 + 5 - 3 = 22 ; volume_m3 = 22 * 2.5 = 55
    expect(result.final_area_m2).toBe(22)
    expect(result.volume_m3).toBe(55)
  })

  it('treats missing/undefined inputs as zero rather than NaN', () => {
    const result = buildQuantityResult({})
    expect(result.final_area_m2).toBe(0)
    expect(result.volume_m3).toBe(0)
  })

  it('reports the deterministic calculation source', () => {
    const result = buildQuantityResult({
      acceptedDetectionAreaM2: 1,
      addedCorrectionAreaM2: 0,
      subtractedCorrectionAreaM2: 0,
      confirmedHeightM: 1,
    })
    expect(result.calculation_source).toBe('deterministic_quantity_engine')
  })
})
