import type { BigPictureNode, LearningPagesPackage } from './types';
import { hasOwnUnitLabel, unitLabel, unitLabelPlural } from './unitLabel';

// A concept can cite several course units; its position in the map is not a unit number.
export function conceptUnits(bundle: LearningPagesPackage, concept: BigPictureNode): number[] {
  const units = new Set(bundle.lessons.filter(lesson => concept.lesson_ids?.includes(lesson.id)).map(lesson => lesson.unit));
  // Modules with their own unit label (e.g. video sessions) are not numbered like the course-letter files.
  if (!hasOwnUnitLabel(bundle)) {
    for (const source of concept.sources) {
      const match = source.path.split('/').pop()?.match(/^(\d+)-(\d+)-/);
      if (match?.[1] === bundle.module_number) units.add(Number(match[2]));
    }
  }
  return [...units].filter(unit => bundle.overview.units.some(item => item.unit === unit)).sort((a, b) => a - b);
}

export function unitCaption(bundle: LearningPagesPackage, units: number[]): string {
  if (!units.length) return 'Einheitenübergreifend';
  const label = units.length === 1 ? unitLabel(bundle, 'Lerneinheit') : unitLabelPlural(bundle, 'Lerneinheiten');
  return `${label} ${units.join(', ')}`;
}
