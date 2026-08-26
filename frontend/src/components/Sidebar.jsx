function Sidebar({ activePage, setActivePage }) {
  const menuItems = [
    { name: "Dashboard", icon: "▦" },
    { name: "AI Chat", icon: "✦" },
    { name: "Strategy", icon: "⌁" },
    { name: "Backtesting", icon: "◒" },
    { name: "Analytics", icon: "⌁" },
  ];

  return (
    <aside className="sidebar">

      <div className="logo">
        <div className="logo-mark">Q</div>

        <div>
          <h2>AI QUANT</h2>
          <span>Quant Intelligence</span>
        </div>
      </div>


      <nav className="sidebar-nav">

        {menuItems.map((item) => (
          <button
            key={item.name}
            className={`nav-item ${
              activePage === item.name ? "active" : ""
            }`}
            onClick={() => setActivePage(item.name)}
          >
            <span className="nav-icon">
              {item.icon}
            </span>

            <span>{item.name}</span>
          </button>
        ))}

      </nav>


      <div className="sidebar-bottom">

        {/* SETTINGS */}
        <button
          className={`nav-item ${
            activePage === "Settings" ? "active" : ""
          }`}
          onClick={() => setActivePage("Settings")}
        >
          <span className="nav-icon">⚙</span>
          <span>Settings</span>
        </button>


        {/* USER */}
        <div className="user-card">

          <div className="avatar">
            S
          </div>

          <div>
            <strong>Shraddha</strong>
            <span>Student Researcher</span>
          </div>

        </div>

      </div>

    </aside>
  );
}

export default Sidebar;