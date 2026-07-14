import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
  busy?: boolean;
}

export function ConfirmModal({ isOpen, title, message, onConfirm, onCancel, confirmText = 'Ya, Hapus', cancelText = 'Batal', busy = false }: ConfirmModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel();
      if (event.key === 'Tab' && !event.shiftKey && document.activeElement === confirmRef.current) { event.preventDefault(); cancelRef.current?.focus(); }
      if (event.key === 'Tab' && event.shiftKey && document.activeElement === cancelRef.current) { event.preventDefault(); confirmRef.current?.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => { document.removeEventListener('keydown', onKeyDown); previousFocus?.focus(); };
  }, [busy, isOpen, onCancel]);

  useEffect(() => { if (isOpen && busy) dialogRef.current?.focus(); }, [busy, isOpen]);

  if (!isOpen) return null;
  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-background/90 p-4" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId}>
      <button type="button" disabled={busy} className="absolute inset-0 cursor-default disabled:cursor-wait" onClick={onCancel} aria-label="Tutup konfirmasi" />
      <section ref={dialogRef} tabIndex={-1} className="relative w-full max-w-sm rounded-2xl border border-line bg-card p-6 focus:outline-none">
        <h2 id={titleId} className="font-display text-lg font-bold text-foreground">{title}</h2>
        <p id={descriptionId} className="mt-2 text-sm leading-relaxed text-muted">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button ref={cancelRef} type="button" disabled={busy} onClick={onCancel} className="rounded-lg border border-line px-4 py-2 text-sm font-bold text-foreground hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card disabled:opacity-50">{cancelText}</button>
          <button ref={confirmRef} type="button" disabled={busy} onClick={onConfirm} className="rounded-lg bg-destructive px-4 py-2 text-sm font-bold text-white hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-destructive focus:ring-offset-2 focus:ring-offset-card disabled:opacity-50">{busy ? 'Menghapus...' : confirmText}</button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
