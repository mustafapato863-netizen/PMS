import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { ariaSortFor, type SortDirection } from './useTableSort';
import { HEAD_BUTTON_CLASS, HEAD_CELL_CLASS } from './adminTableClasses';

export type SortableHeaderCellProps = {
  /** The column label. It is also the accessible name of the sort button. */
  label: string;
  /** The active direction for this column, or null when it is not the sorted column. */
  direction: SortDirection | null;
  onSort: () => void;
  align?: 'left' | 'right';
};

/**
 * A real column header with a sort button inside it. The direction is shown by the icon's shape and by aria-sort,
 * never by colour alone.
 */
export function SortableHeaderCell({ label, direction, onSort, align = 'left' }: SortableHeaderCellProps) {
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
  return (
    <th scope="col" aria-sort={ariaSortFor(direction)} className={`${HEAD_CELL_CLASS} ${align === 'right' ? 'text-right' : ''}`}>
      <button type="button" onClick={onSort} className={`${HEAD_BUTTON_CLASS} ${align === 'right' ? 'justify-end' : ''}`}>
        <span>{label}</span>
        <Icon size={13} aria-hidden="true" className={direction ? 'text-blue-600 dark:text-blue-400' : 'opacity-60'} />
      </button>
    </th>
  );
}
