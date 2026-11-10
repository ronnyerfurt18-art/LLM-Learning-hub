// How a module calls its numbered parts ("Einheit", "Session", …). Set per module; the API serves it as unit_label.
type Labelled = { unit_label?: string | null } | null | undefined;

const PLURALS: Record<string, string> = { Einheit: 'Einheiten', Session: 'Sessions', Kapitel: 'Kapitel', Lektion: 'Lektionen', Woche: 'Wochen' };

export const UNIT_LABELS = Object.keys(PLURALS);

export function hasOwnUnitLabel(item: Labelled): boolean {
  return !!item?.unit_label && item.unit_label !== 'Einheit';
}

// The fallback keeps each page's established wording for ordinary course units.
export function unitLabel(item: Labelled, fallback = 'Einheit'): string {
  return hasOwnUnitLabel(item) ? item!.unit_label! : fallback;
}

export function unitLabelPlural(item: Labelled, fallback = 'Einheiten'): string {
  return hasOwnUnitLabel(item) ? PLURALS[item!.unit_label!] || item!.unit_label! : fallback;
}
