/** Enter / Space preview · O (or Ctrl/Cmd+Enter) open report — on ticker control. */
export function handleTickerRowKeyDown(e, { onPreview, onOpen }) {
  if (e.key === 'Enter') {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) onOpen();
    else onPreview();
    return;
  }
  if (e.key === ' ') {
    e.preventDefault();
    onPreview();
    return;
  }
  if (e.key === 'o' && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    onOpen();
  }
}

/**
 * Park focus on the ticker before opening preview/sheet so the focus trap
 * records it as previousFocus (restore on Esc). Call synchronously before setState.
 */
export function focusTickerButton(tickerId) {
  if (!tickerId) return;
  document.getElementById(tickerId)?.focus({ preventScroll: true });
}
