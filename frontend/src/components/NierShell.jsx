export default function NierShell({ children, landing = false, className = '' }) {
  return (
    <div className={`nier-shell${landing ? ' nier-landing' : ''} ${className}`.trim()}>
      <a href="#main-content" className="nier-skip-link">
        Skip to main content
      </a>
      <div className="nier-ornament" aria-hidden="true" />
      <div className="nier-shell-body">{children}</div>
      <div className="nier-ornament nier-ornament--flip" aria-hidden="true" />
    </div>
  );
}
