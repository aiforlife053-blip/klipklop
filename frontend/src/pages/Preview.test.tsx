import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Preview from './Preview';
import { apiGet, apiPost } from '@/lib/api';
import type { ClipSettings } from '@/lib/clip-settings';

vi.mock('@/lib/api', () => ({ apiGet: vi.fn(), apiPost: vi.fn() }));

const defaults: ClipSettings = {
  hook_style: { enabled: true, font_size: 0.054, font_family: 'Plus Jakarta Sans', font_weight: 800, text_color: '#FFD700', outline_color: '#000000', outline_thickness: 1.5, duration: 5, position_x: 0.5, position_y: 0.2 },
  subtitle: { enabled: false, color: '#00BFFF', text_color: '#FFFFFF', size: 0.04, position_x: 0.5, position_y: 0.85, font_family: 'Plus Jakarta Sans', font_weight: 800, outline_color: '#000000', outline_thickness: 1 },
  watermark: { enabled: false, scale: 0.15, opacity: 0.8, position_x: 0.85, position_y: 0.05 },
  credit_watermark: { enabled: false, text: 'sc : {channel}', color: '#FFFFFF', size: 0.032, opacity: 0.55, position_x: 0.06, position_y: 0.23 },
  blur_background: { enabled: false, scale: 1.6, zoom: 1.08, strength: 10 },
  video_layout: { mode: 'normal' },
  screen_size: '9:16',
};
const clips = [
  { clip_id: 'first', title: 'First', description: '', status: 'needs_edit', stream_url: '/first' },
  { clip_id: 'second', title: 'Second', description: '', status: 'needs_edit', stream_url: '/second' },
];
const clipResponse = (clip: typeof clips[number]) => ({ status: 'ok', defaults, clip: { ...clip, source_url: clip.stream_url, source_geometry: { width: 1920, height: 1080, is_landscape: true } } });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => { resolve = resolvePromise; reject = rejectPromise; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.mocked(apiGet).mockImplementation(async (path) => path === '/api/clips' ? { status: 'ok', clips } : clipResponse(path.includes('second') ? clips[1] : clips[0]));
  vi.mocked(apiPost).mockReset();
});

describe('Preview gaming detection', () => {
  it('ignores stale detection after another clip opens', async () => {
    const detection = deferred<{ status: string; facecam: { x: number; y: number; width: number; height: number }; confidence: number }>();
    vi.mocked(apiPost).mockReturnValueOnce(detection.promise);
    render(<MemoryRouter><Preview /></MemoryRouter>);
    await userEvent.click((await screen.findAllByRole('button', { name: 'Edit' }))[0]);
    await userEvent.click(screen.getByRole('tab', { name: 'Layout video' }));
    await userEvent.click(screen.getByRole('button', { name: /Gaming/ }));
    expect(screen.getAllByText('Mendeteksi facecam…')).toHaveLength(2);
    await userEvent.click(screen.getAllByRole('button', { name: 'Edit' })[1]);
    expect(await screen.findByRole('heading', { name: 'Second', level: 2 })).toBeInTheDocument();
    detection.resolve({ status: 'ok', facecam: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 }, confidence: 0.9 });
    await waitFor(() => expect(screen.queryByText('Confidence 90%')).not.toBeInTheDocument());
  });

  it('clears prior ROI and stays invalid after redetection fails', async () => {
    vi.mocked(apiGet).mockImplementation(async (path) => path === '/api/clips' ? { status: 'ok', clips: [clips[0]] } : { ...clipResponse(clips[0]), clip: { ...clipResponse(clips[0]).clip, draft_settings: { video_layout: { mode: 'gaming', facecam_x: 0.1, facecam_y: 0.1, facecam_width: 0.2, facecam_height: 0.2, facecam_confidence: 0.9 } } } });
    const detection = deferred<never>();
    vi.mocked(apiPost).mockReturnValueOnce(detection.promise);
    render(<MemoryRouter><Preview /></MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('tab', { name: 'Layout video' }));
    await userEvent.click(screen.getByRole('button', { name: 'Deteksi ulang' }));
    expect(screen.queryByText('Confidence 90%')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Render Preview Akurat' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Lanjut ke tahap berikutnya' })).toBeDisabled();
    detection.reject(new Error('Deteksi gagal'));
    expect(await screen.findByText('Deteksi gagal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Gaming/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Render Preview Akurat' })).toBeDisabled();
  });
});
