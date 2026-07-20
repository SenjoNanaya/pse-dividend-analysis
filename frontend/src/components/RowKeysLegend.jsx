/** Visible keyboard hint for the focused ticker control on registry / watchlist rows. */
export default function RowKeysLegend({ id = 'table-row-keys' }) {
  return (
    <p id={id} className="nier-kbd-legend" role="note">
      <span className="nier-kbd-legend-label">Ticker keys</span>
      {' '}
      <kbd className="nier-kbd">Enter</kbd>
      {' / '}
      <kbd className="nier-kbd">Space</kbd>
      {' preview · '}
      <kbd className="nier-kbd">O</kbd>
      {' open report'}
    </p>
  );
}
