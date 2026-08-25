import { describe, expect, it } from 'vitest'
import { draftToNormalizedRect, normalizedToDisplayRect } from './coordinates'

describe('draftToNormalizedRect', () => {
  it('produces the identical normalized rect regardless of displayed view size', () => {
    // Same natural image (the persisted preview PNG never changes), same
    // *proportional* drag, but the browser is showing it at two very
    // different sizes -- this is exactly "preview displayed at another
    // size" from the R3 coordinate-contract requirement.
    const naturalSize = { width: 1684, height: 1191 }

    const viewSizeA = { width: 842, height: 595.5 } // shown at half natural size
    const draftA = { startX: 84.2, startY: 59.55, endX: 168.4, endY: 119.1 } // 10%..20% of viewA

    const viewSizeB = { width: 400, height: 283.03 } // shown much smaller, different aspect rounding
    const draftB = { startX: 40, startY: 28.303, endX: 80, endY: 56.606 } // same 10%..20% of viewB

    const rectA = draftToNormalizedRect(draftA, naturalSize, viewSizeA)
    const rectB = draftToNormalizedRect(draftB, naturalSize, viewSizeB)

    expect(rectA).not.toBeNull()
    expect(rectA.x).toBeCloseTo(0.1, 5)
    expect(rectA.y).toBeCloseTo(0.1, 5)
    expect(rectA.width).toBeCloseTo(0.1, 5)
    expect(rectA.height).toBeCloseTo(0.1, 5)

    // The two draws represent the same page-relative selection at two
    // different preview sizes -- the stored normalized rect must match.
    expect(rectB.x).toBeCloseTo(rectA.x, 5)
    expect(rectB.y).toBeCloseTo(rectA.y, 5)
    expect(rectB.width).toBeCloseTo(rectA.width, 5)
    expect(rectB.height).toBeCloseTo(rectA.height, 5)
  })

  it('returns null for a drag smaller than the minimum threshold', () => {
    const result = draftToNormalizedRect(
      { startX: 10, startY: 10, endX: 11, endY: 11 },
      { width: 1000, height: 1000 },
      { width: 1000, height: 1000 }
    )
    expect(result).toBeNull()
  })

  it('returns null when natural or view size is not yet known (image not loaded)', () => {
    const draft = { startX: 0, startY: 0, endX: 50, endY: 50 }
    expect(draftToNormalizedRect(draft, { width: 0, height: 0 }, { width: 500, height: 500 })).toBeNull()
    expect(draftToNormalizedRect(draft, { width: 500, height: 500 }, { width: 0, height: 0 })).toBeNull()
  })

  it('clamps a selection that would otherwise extend past the image edge', () => {
    const naturalSize = { width: 1000, height: 1000 }
    const viewSize = { width: 1000, height: 1000 }
    // Drag starts near the right edge and overshoots past it.
    const draft = { startX: 950, startY: 10, endX: 1200, endY: 60 }
    const rect = draftToNormalizedRect(draft, naturalSize, viewSize)
    expect(rect.x + rect.width).toBeLessThanOrEqual(1)
  })
})

describe('normalizedToDisplayRect', () => {
  it('scales a normalized rect to the given view size only, ignoring natural size entirely', () => {
    const normRect = { x: 0.25, y: 0.5, width: 0.1, height: 0.2 }

    const small = normalizedToDisplayRect(normRect, { width: 400, height: 300 })
    expect(small).toEqual({ left: 100, top: 150, width: 40, height: 60 })

    const large = normalizedToDisplayRect(normRect, { width: 2000, height: 1500 })
    expect(large).toEqual({ left: 500, top: 750, width: 200, height: 300 })
  })

  it('returns null without a view size', () => {
    expect(normalizedToDisplayRect({ x: 0, y: 0, width: 0.1, height: 0.1 }, { width: 0, height: 0 })).toBeNull()
  })
})
