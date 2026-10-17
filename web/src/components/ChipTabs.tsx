import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import { type KeyboardEvent } from 'react';

export interface ChipTab<T extends string> {
  value: T;
  label: string;
}

/** The id of a tab, and the panel it controls, so a page can label its panel with `aria-labelledby`. */
export const chipTabId = (idPrefix: string, value: string) => `${idPrefix}-tab-${value}`;
export const chipPanelId = (idPrefix: string) => `${idPrefix}-panel`;

/**
 * A row of chip-shaped tabs with real tab behaviour: one stop in the tab order, the arrow keys (and
 * Home / End) move between tabs, and a screen reader hears "tab, selected, 1 of 2".
 * The page marks the content below it as `role="tabpanel"` with `id={chipPanelId(idPrefix)}`.
 */
export function ChipTabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  idPrefix,
}: {
  tabs: ChipTab<T>[];
  value: T;
  onChange: (next: T) => void;
  label: string;
  idPrefix: string;
}) {
  const move = (index: number) => {
    const next = tabs[(index + tabs.length) % tabs.length];
    onChange(next.value);
    document.getElementById(chipTabId(idPrefix, next.value))?.focus();
  };
  const onKeyDown = (event: KeyboardEvent, index: number) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') move(index + 1);
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') move(index - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(tabs.length - 1);
    else return;
    event.preventDefault();
  };
  return (
    <Stack direction="row" spacing={1} role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const selected = tab.value === value;
        return (
          <Chip
            key={tab.value}
            id={chipTabId(idPrefix, tab.value)}
            role="tab"
            aria-selected={selected}
            aria-controls={chipPanelId(idPrefix)}
            tabIndex={selected ? 0 : -1}
            label={tab.label}
            color={selected ? 'primary' : 'default'}
            variant={selected ? 'filled' : 'outlined'}
            onClick={() => onChange(tab.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          />
        );
      })}
    </Stack>
  );
}
