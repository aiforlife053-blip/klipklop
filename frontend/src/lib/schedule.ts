export function defaultWibScheduleTime(now = new Date()): string {
  const target = new Date(now.getTime() + 15 * 60_000);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Jakarta',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(target).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function validateWibSchedule(value: string, now = new Date()): string {
  if (!value) return 'Waktu tayang wajib diisi.';
  const scheduled = new Date(`${value}:00+07:00`);
  if (Number.isNaN(scheduled.getTime())) return 'Waktu upload tidak valid.';
  const min = new Date(now.getTime() + 10 * 60_000);
  if (scheduled.getTime() <= now.getTime()) return 'Waktu upload harus setelah sekarang.';
  if (scheduled.getTime() < min.getTime()) return 'Jadwal minimal 10 menit dari sekarang (WIB).';
  return '';
}
