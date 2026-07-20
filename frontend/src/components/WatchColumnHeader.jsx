/**
 * Registry / watchlist watch column header.
 * Word label WATCH; row cells stay ★/☆ (same WatchToggle action as the sheet).
 */
export default function WatchColumnHeader({
  title = 'Watch — get alerts when checks or ratios flip',
}) {
  return (
    <th
      className="nier-check-col nier-col-watch"
      scope="col"
      title={title}
      aria-label="Watch"
    >
      <span className="nier-watch-col-label" aria-hidden="true">
        WATCH
      </span>
    </th>
  );
}
