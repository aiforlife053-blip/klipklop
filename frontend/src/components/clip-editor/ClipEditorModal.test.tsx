import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ClipEditorModal, type EditorClip } from './ClipEditorModal';
import type { ClipSettings } from '@/lib/clip-settings';

const settings: ClipSettings = {
  hook_style: { enabled: true, font_size: 0.054, font_family: 'Plus Jakarta Sans', font_weight: 800, text_color: '#FFD700', outline_color: '#000000', outline_thickness: 1.5, duration: 5, position_x: 0.5, position_y: 0.2 },
  subtitle: { enabled: false, color: '#00BFFF', text_color: '#FFFFFF', size: 0.04, position_x: 0.5, position_y: 0.85, font_family: 'Plus Jakarta Sans', font_weight: 800, outline_color: '#000000', outline_thickness: 1 },
  watermark: { enabled: false, scale: 0.15, opacity: 0.8, position_x: 0.85, position_y: 0.05 },
  credit_watermark: { enabled: false, text: 'sc : {channel}', color: '#FFFFFF', size: 0.032, opacity: 0.55, position_x: 0.06, position_y: 0.23 },
  blur_background: { enabled: false, scale: 1.6, zoom: 1.08, strength: 10 },
  video_layout: { mode: 'normal' },
  screen_size: '9:16',
};
const clip: EditorClip = { clip_id: 'clip', title: 'Clip', status: 'needs_edit', stream_url: '/video', source_url: '/video', source_geometry: { width: 1920, height: 1080, is_landscape: true } };

function setup(onChange = vi.fn(), onHookTextChange = vi.fn()) {
  render(<ClipEditorModal clip={clip} settings={settings} previewUrl="" previewBusy={false} actionBusy={false} error="" invalid={false} hookText="Hook" backgroundVisible onHookTextChange={onHookTextChange} onClose={vi.fn()} onChange={onChange} onReset={vi.fn()} onPreview={vi.fn()} onSaveDefaults={vi.fn()} onRender={vi.fn()} />);
  return { onChange, onHookTextChange };
}

describe('ClipEditorModal controls', () => {
  it('keeps partial decimal text until blur then commits once', async () => {
    const { onChange } = setup();
    const input = screen.getByRole('textbox', { name: 'Ukuran angka' });
    await userEvent.clear(input);
    await userEvent.type(input, '0,023');
    expect(input).toHaveValue('0,023');
    expect(onChange).not.toHaveBeenCalledWith('hook_style', 'font_size', expect.anything());
    await userEvent.tab();
    expect(onChange).toHaveBeenCalledWith('hook_style', 'font_size', 0.023);
  });

  it('exposes toggles as accessible switches', () => {
    setup();
    expect(screen.getByRole('switch', { name: /Tampilkan hook/ })).toBeChecked();
    expect(screen.getByText('Aktif di hasil video')).toBeInTheDocument();
  });

  it('offers gaming detection controls and clears detection errors', async () => {
    const onVideoLayoutChange = vi.fn();
    const onRedetectGaming = vi.fn();
    const onClearError = vi.fn();
    render(<ClipEditorModal clip={clip} settings={{ ...settings, video_layout: { mode: 'gaming', facecam_x: 0.1, facecam_y: 0.1, facecam_width: 0.2, facecam_height: 0.2, facecam_confidence: 0.84 } }} previewUrl="" previewBusy={false} actionBusy={false} error="Deteksi gagal" invalid={false} hookText="Hook" backgroundVisible={false} gamingDetectionStatus="Facecam terdeteksi." onHookTextChange={vi.fn()} onClose={vi.fn()} onChange={vi.fn()} onVideoLayoutChange={onVideoLayoutChange} onRedetectGaming={onRedetectGaming} onClearError={onClearError} onReset={vi.fn()} onPreview={vi.fn()} onSaveDefaults={vi.fn()} onRender={vi.fn()} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Layout video' }));
    expect(screen.getByRole('button', { name: /Gaming/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Confidence 84%')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Deteksi ulang' }));
    await userEvent.click(screen.getByRole('button', { name: 'Hapus error' }));
    expect(onRedetectGaming).toHaveBeenCalledOnce();
    expect(onClearError).toHaveBeenCalledOnce();
    expect(screen.queryByRole('tab', { name: 'Latar' })).not.toBeInTheDocument();
  });

  it('blocks close button and Escape while gaming detection runs', async () => {
    const onClose = vi.fn();
    render(<ClipEditorModal clip={clip} settings={{ ...settings, video_layout: { mode: 'gaming' } }} previewUrl="" previewBusy={false} actionBusy={false} error="" invalid hookText="Hook" backgroundVisible={false} gamingDetectionBusy onHookTextChange={vi.fn()} onClose={onClose} onChange={vi.fn()} onReset={vi.fn()} onPreview={vi.fn()} onSaveDefaults={vi.fn()} onRender={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Tutup editor' })).toBeDisabled();
    await userEvent.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps textarea focus while the parent rerenders for every character', async () => {
    function Harness() {
      const [hookText, setHookText] = useState('');
      return <ClipEditorModal clip={clip} settings={settings} previewUrl="" previewBusy={false} actionBusy={false} error="" invalid={false} hookText={hookText} backgroundVisible onHookTextChange={setHookText} onClose={() => undefined} onChange={vi.fn()} onReset={vi.fn()} onPreview={vi.fn()} onSaveDefaults={vi.fn()} onRender={vi.fn()} />;
    }
    render(<Harness />);
    const textarea = screen.getByRole('textbox', { name: 'Teks hook' });
    await userEvent.type(textarea, 'Tiga kata utuh');
    expect(textarea).toHaveValue('Tiga kata utuh');
    expect(textarea).toHaveFocus();
  });
});
