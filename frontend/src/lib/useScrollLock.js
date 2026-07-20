import { useEffect } from 'react';

/**
 * Lock document scroll while `active` (e.g. mobile preview sheet).
 * Uses position:fixed + scrollY restore so iOS Safari can't rubber-band the page under the modal.
 *
 * Pass `restoreYRef` when a dismiss path should land somewhere other than the
 * captured Y (e.g. Open report → 0 so Back is not clipped above the fold).
 * Set `restoreYRef.current` before deactivating the lock; cleanup consumes and clears it.
 *
 * @param {boolean} active
 * @param {{ restoreYRef?: { current: number | null } }} [options]
 */
export default function useScrollLock(active, options = {}) {
  const { restoreYRef } = options;

  useEffect(() => {
    if (!active) return undefined;

    const { documentElement, body } = document;
    const scrollY = window.scrollY;
    const prevHtmlOverflow = documentElement.style.overflow;
    const prevBody = {
      overflow: body.style.overflow,
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
    };

    documentElement.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    body.style.position = 'fixed';
    body.style.top = `-${scrollY}px`;
    body.style.left = '0';
    body.style.right = '0';
    body.style.width = '100%';

    return () => {
      documentElement.style.overflow = prevHtmlOverflow;
      body.style.overflow = prevBody.overflow;
      body.style.position = prevBody.position;
      body.style.top = prevBody.top;
      body.style.left = prevBody.left;
      body.style.right = prevBody.right;
      body.style.width = prevBody.width;
      const override = restoreYRef?.current;
      if (override != null && Number.isFinite(override)) {
        restoreYRef.current = null;
        window.scrollTo(0, override);
      } else {
        window.scrollTo(0, scrollY);
      }
    };
  }, [active, restoreYRef]);
}
