function Topbar({ title }) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <p>AI-powered quantitative trading workspace</p>
      </div>

      <div className="topbar-actions">
        <button className="icon-button">⌕</button>
        <button className="icon-button">🔔</button>

        <div className="profile">
          <div className="avatar">S</div>
          <span>Shraddha</span>
        </div>
      </div>
    </header>
  );
}

export default Topbar;