import { useEffect, useId, useRef, useState } from 'react';

/**
 * Themed dropdown — native <select> popups cannot inherit page CSS.
 * Keyboard: ArrowUp/Down, Home/End, Enter/Space, Escape.
 */
export default function NierSelect({
  label,
  value,
  options = [],
  onChange,
  placeholder = 'All',
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const rootRef = useRef(null);
  const menuRef = useRef(null);
  const labelId = useId();
  const listId = useId();
  const optionIdPrefix = useId();

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const selected = options.find((o) => o.value === value);
  const display = selected?.label ?? placeholder;
  const activeDescendant =
    open && highlight >= 0 ? `${optionIdPrefix}-${highlight}` : undefined;

  useEffect(() => {
    if (!open) return undefined;
    setHighlight(selectedIndex >= 0 ? selectedIndex : 0);
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open || highlight < 0 || !menuRef.current) return;
    const el = document.getElementById(`${optionIdPrefix}-${highlight}`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [open, highlight, optionIdPrefix]);

  const moveHighlight = (delta) => {
    if (!options.length) return;
    setHighlight((prev) => {
      const base = prev < 0 ? selectedIndex : prev;
      return (base + delta + options.length) % options.length;
    });
  };

  const choose = (opt) => {
    onChange?.(opt.value);
    setOpen(false);
  };

  const onTriggerKeyDown = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      moveHighlight(e.key === 'ArrowDown' ? 1 : -1);
    } else if (e.key === 'Home' && open) {
      e.preventDefault();
      setHighlight(0);
    } else if (e.key === 'End' && open) {
      e.preventDefault();
      setHighlight(options.length - 1);
    } else if ((e.key === 'Enter' || e.key === ' ') && open) {
      e.preventDefault();
      const opt = options[highlight] ?? options[selectedIndex];
      if (opt) choose(opt);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className={`nier-filter-field${open ? ' is-open' : ''}`} ref={rootRef}>
      {label && (
        <span id={labelId}>{label}</span>
      )}
      <button
        type="button"
        className="nier-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-labelledby={label ? labelId : undefined}
        aria-label={label || undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="nier-select-value">{display}</span>
        <span className="nier-select-caret" aria-hidden="true" />
      </button>
      {open && (
        <ul
          ref={menuRef}
          id={listId}
          className="nier-select-menu"
          role="listbox"
          aria-labelledby={label ? labelId : undefined}
          aria-activedescendant={activeDescendant}
        >
          {options.map((opt, idx) => {
            const active = opt.value === value;
            const focused = idx === highlight;
            return (
              <li key={`${opt.value}::${opt.label}`} role="presentation">
                <button
                  type="button"
                  id={`${optionIdPrefix}-${idx}`}
                  role="option"
                  aria-selected={active}
                  tabIndex={-1}
                  className={[
                    'nier-select-option',
                    active ? 'is-active' : '',
                    focused ? 'is-focused' : '',
                  ].filter(Boolean).join(' ')}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => choose(opt)}
                >
                  {opt.label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
