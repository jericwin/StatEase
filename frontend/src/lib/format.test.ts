import { describe, expect, it } from 'vitest'
import { formatP, formatR, formatValue } from './format'

describe('formatP', () => {
  it('never shows p = .000', () => {
    expect(formatP(0.0000004)).toBe('< .001')
    expect(formatP(0.0000004, 'apa', true)).toBe('p < .001')
    expect(formatP(0.0004, 'academic')).toBe('< 0.001')
  })
  it('drops the leading zero in APA style only', () => {
    expect(formatP(0.0234)).toBe('.023')
    expect(formatP(0.0234, 'academic')).toBe('0.023')
    expect(formatP(0.0234, 'apa', true)).toBe('p = .023')
  })
  it('handles boundaries and missing values', () => {
    expect(formatP(1)).toBe('1.000')
    expect(formatP(0.001)).toBe('.001')
    expect(formatP(null)).toBe('—')
    expect(formatP(Number.NaN)).toBe('—')
  })
})

describe('formatValue', () => {
  it('rounds for display only and respects format', () => {
    expect(formatValue(3.14159, 'num', 2)).toBe('3.14')
    expect(formatValue(1234567, 'int')).toBe('1,234,567')
    expect(formatValue(-0.4567, 'r', 2)).toBe('-.46')
    expect(formatValue(45.678, 'pct')).toBe('45.7')
    expect(formatValue(null, 'num')).toBe('')
  })
  it('formats bounded coefficients without leading zero in APA style', () => {
    expect(formatR(0.81, 2)).toBe('.81')
    expect(formatR(0.81, 2, 'academic')).toBe('0.81')
  })
})
