import { describe, expect, it } from 'vitest';
import { defaultWibScheduleTime, validateWibSchedule } from './schedule';

describe('schedule helpers', () => {
  it('defaults at least 10 minutes ahead in WIB clock form', () => {
    const now = new Date('2026-07-17T03:00:00.000Z'); // 10:00 WIB
    const value = defaultWibScheduleTime(now);
    expect(value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(validateWibSchedule(value, now)).toBe('');
  });

  it('rejects schedules under 10 minutes', () => {
    const now = new Date('2026-07-17T03:00:00.000Z');
    expect(validateWibSchedule('2026-07-17T10:05', now)).toContain('10 menit');
    expect(validateWibSchedule('2026-07-17T09:59', now)).toContain('setelah sekarang');
    expect(validateWibSchedule('', now)).toContain('wajib');
  });
});
