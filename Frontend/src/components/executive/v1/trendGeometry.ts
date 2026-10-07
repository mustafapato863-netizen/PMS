/** Pure SVG geometry shared by the interactive hero and static function cards. */
export interface SegmentPoint {
  index: number;
  value: number;
}

export function splitSeries(values: Array<number | null>): SegmentPoint[][] {
  const result: SegmentPoint[][] = [];
  let current: SegmentPoint[] = [];
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      if (current.length) result.push(current);
      current = [];
    } else {
      current.push({ index, value });
    }
  });
  if (current.length) result.push(current);
  return result;
}

export function smoothPath(points: SegmentPoint[], x: (index: number) => number, y: (value: number) => number): string {
  return points.reduce((path, point, index) => {
    const pointX = x(point.index);
    const pointY = y(point.value);
    if (index === 0) return 'M' + pointX.toFixed(1) + ' ' + pointY.toFixed(1);
    const previous = points[index - 1];
    const controlOffset = (pointX - x(previous.index)) / 3;
    return path + ' C' + (x(previous.index) + controlOffset).toFixed(1) + ' ' + y(previous.value).toFixed(1)
      + ', ' + (pointX - controlOffset).toFixed(1) + ' ' + pointY.toFixed(1)
      + ', ' + pointX.toFixed(1) + ' ' + pointY.toFixed(1);
  }, '');
}
