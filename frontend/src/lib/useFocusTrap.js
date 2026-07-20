import { useEffect, useRef } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function listFocusable(root) {
  return [...root.querySelectorAll(FOCUSABLE_SELECTOR)].filter((el) => {
    if (el.getAttribute('aria-hidden') === 'true') return false;
    // offsetParent is null for fixed/positioned-hidden; also check visibility
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    return true;
  });
}

/**
 * Trap Tab inside `containerRef` while `active`. Moves focus in on activate;
 * restores the previously focused element on deactivate.
 */
export default function useFocusTrap(containerRef, { active, onEscape } = {}) {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    const root = containerRef.current;
    if (!root) return undefined;

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    if (!root.hasAttribute('tabindex')) {
      root.tabIndex = -1;
    }

    const focusInitial = () => {
      const items = listFocusable(root);
      const preferred =
        root.querySelector('[data-sheet-initial-focus]') ||
        items.find((el) => el.matches('button, [href], input, select, textarea')) ||
        items[0];
      (preferred || root).focus();
    };

    const raf = requestAnimationFrame(focusInitial);

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onEscapeRef.current?.();
        return;
      }
      if (e.key !== 'Tab') return;

      const items = listFocusable(root);
      if (items.length === 0) {
        e.preventDefault();
        root.focus();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      const activeEl = document.activeElement;

      if (e.shiftKey) {
        if (activeEl === first || activeEl === root) {
          e.preventDefault();
          last.focus();
        }
      } else if (activeEl === last) {
        e.preventDefault();
        first.focus();
      }
    };

    // Capture so Tab can't leak to inert-sibling chrome before we cycle
    root.addEventListener('keydown', onKeyDown);

    return () => {
      cancelAnimationFrame(raf);
      root.removeEventListener('keydown', onKeyDown);
      const prev = previousFocusRef.current;
      previousFocusRef.current = null;
      if (prev && document.contains(prev) && typeof prev.focus === 'function') {
        prev.focus();
      }
    };
  }, [active, containerRef]);
}
