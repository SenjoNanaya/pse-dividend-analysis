/** Shared Watch / Unwatch copy for star toggles (registry, preview, watchlist). */

export function watchToggleCopy(ticker, { watched = false, disabled = false, max } = {}) {
  const name = ticker || 'company';
  if (disabled) {
    const cap = max != null ? ` (max ${max})` : '';
    return {
      ariaLabel: `Watchlist full${cap}. Cannot watch ${name}`,
      title: `Watchlist full${cap}`,
    };
  }
  if (watched) {
    return {
      ariaLabel: `Unwatch ${name}`,
      title: `Unwatch ${name} (★) — stop signal alerts`,
    };
  }
  return {
    ariaLabel: `Watch ${name}`,
    title: `Watch ${name} (☆ → ★) for signal alerts`,
  };
}
