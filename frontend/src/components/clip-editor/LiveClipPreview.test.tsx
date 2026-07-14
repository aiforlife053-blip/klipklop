import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LiveClipPreview } from './LiveClipPreview';
import type { ClipEditorContract, ClipSettings } from '@/lib/clip-settings';

const contract: ClipEditorContract = { source_url: '/source', source_geometry: { width: 1920, height: 1080, is_landscape: true }, subtitle_cues: [{ start: 0, end: 1, text: 'SATU DUA', words: [{ text: 'SATU', start: 0, end: 0.3, active_from: 0, active_until: 0.3 }, { text: 'DUA', start: 0.35, end: 0.7, active_from: 0.3, active_until: 0.7 }], active_word_indexes: [0, 1], capability: 'word_highlight' }], subtitle_capability: 'word_highlight', subtitle_reason: '', watermark_url: '/watermark', watermark_revision: 'rev', resolved_credit_text: 'sc : channel' };
const settings: ClipSettings = { hook_style: { enabled: true, duration: 5, position_x: 0.5, position_y: 0.2, font_size: 0.054, text_color: '#FFD700', outline_color: '#000000', outline_thickness: 1.5 }, subtitle: { enabled: true, position_x: 0.5, position_y: 0.85, size: 0.04, text_color: '#FFFFFF', color: '#00BFFF', outline_color: '#000000', outline_thickness: 1 }, watermark: { enabled: true, position_x: 0.85, position_y: 0.05, scale: 0.15, opacity: 0.8 }, credit_watermark: { enabled: true, position_x: 0.06, position_y: 0.23, size: 0.032, color: '#FFFFFF', opacity: 0.55 }, blur_background: { enabled: false, scale: 1.6 }, screen_size: '9:16' };

describe('LiveClipPreview', () => {
  it('highlights active cue word without preview API calls', () => {
    vi.stubGlobal('fetch', vi.fn());
    render(<LiveClipPreview contract={contract} settings={settings} hookText="Hook" currentTime={0.45} source="/source" onTimeChange={vi.fn()} />);
    expect(screen.getByText('DUA')).toHaveStyle({ color: '#00BFFF' });
    expect(screen.getByTestId('live-hook')).toHaveTextContent('Hook');
    expect(screen.getByTestId('live-hook')).not.toHaveClass('uppercase');
    expect(screen.getByTestId('live-preview')).toHaveClass('h-[62dvh]');
    expect(screen.getByLabelText('Live preview')).not.toHaveStyle({ transform: 'scale(1.6)' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
