function Settings({ theme, changeTheme }) {
  return (
    <div className="settings-page">

      {/* HEADER */}
      <section className="settings-header">
        <div>
          <p className="eyebrow">PLATFORM SETTINGS</p>

          <h2>Customize your workspace.</h2>

          <p>
            Manage your profile, trading preferences, notifications, and
            platform experience.
          </p>
        </div>
      </section>


      <div className="settings-layout">

        {/* SETTINGS NAVIGATION */}
        <div className="settings-nav">

          <button className="settings-nav-item active">
            Profile
          </button>

          <button className="settings-nav-item">
            Trading Preferences
          </button>

          <button className="settings-nav-item">
            Notifications
          </button>

          <button className="settings-nav-item">
            Appearance
          </button>

        </div>


        {/* SETTINGS CONTENT */}
        <div className="settings-content">


          {/* ================= PROFILE ================= */}

          <section className="panel settings-panel">

            <div className="section-title">

              <div className="section-number">
                01
              </div>

              <div>
                <h3>Profile</h3>

                <p>
                  Manage your account information.
                </p>
              </div>

            </div>


            <div className="profile-row">

              <div className="profile-avatar">
                S
              </div>

              <div>
                <h3>Shraddha</h3>

                <p>
                  Student Researcher
                </p>
              </div>

            </div>


            <div className="settings-form">

              <div className="form-group">

                <label>
                  Full Name
                </label>

                <input
                  type="text"
                  defaultValue="Shraddha"
                />

              </div>


              <div className="form-group">

                <label>
                  Email
                </label>

                <input
                  type="email"
                  defaultValue="student@example.com"
                />

              </div>

            </div>


            <button className="primary-button">
              Save Changes
            </button>

          </section>



          {/* ================= TRADING PREFERENCES ================= */}

          <section className="panel settings-panel">

            <div className="section-title">

              <div className="section-number">
                02
              </div>

              <div>

                <h3>
                  Trading Preferences
                </h3>

                <p>
                  Set default preferences for strategy creation.
                </p>

              </div>

            </div>


            <div className="settings-form">

              <div className="form-group">

                <label>
                  Default Market
                </label>

                <select defaultValue="NIFTY 50">

                  <option>
                    NIFTY 50
                  </option>

                  <option>
                    BANKNIFTY
                  </option>

                  <option>
                    FINNIFTY
                  </option>

                </select>

              </div>


              <div className="form-group">

                <label>
                  Default Timeframe
                </label>

                <select defaultValue="5 Minutes">

                  <option>
                    5 Minutes
                  </option>

                  <option>
                    15 Minutes
                  </option>

                  <option>
                    1 Hour
                  </option>

                  <option>
                    Daily
                  </option>

                </select>

              </div>


              <div className="form-group">

                <label>
                  Risk Preference
                </label>

                <select defaultValue="Medium">

                  <option>
                    Low
                  </option>

                  <option>
                    Medium
                  </option>

                  <option>
                    High
                  </option>

                </select>

              </div>

            </div>

          </section>



          {/* ================= NOTIFICATIONS ================= */}

          <section className="panel settings-panel">

            <div className="section-title">

              <div className="section-number">
                03
              </div>

              <div>

                <h3>
                  Notifications
                </h3>

                <p>
                  Control the alerts you receive.
                </p>

              </div>

            </div>


            <div className="toggle-row">

              <div>

                <strong>
                  Backtest completed
                </strong>

                <p>
                  Notify when a backtest finishes.
                </p>

              </div>

              <input
                type="checkbox"
                defaultChecked
              />

            </div>


            <div className="toggle-row">

              <div>

                <strong>
                  Strategy insights
                </strong>

                <p>
                  Receive AI-generated strategy insights.
                </p>

              </div>

              <input
                type="checkbox"
                defaultChecked
              />

            </div>


            <div className="toggle-row">

              <div>

                <strong>
                  Risk alerts
                </strong>

                <p>
                  Notify when strategy risk increases.
                </p>

              </div>

              <input
                type="checkbox"
              />

            </div>

          </section>



          {/* ================= APPEARANCE ================= */}

          <section className="panel settings-panel">

            <div className="section-title">

              <div className="section-number">
                04
              </div>

              <div>

                <h3>
                  Appearance
                </h3>

                <p>
                  Customize the look of your workspace.
                </p>

              </div>

            </div>


            {/* THEME OPTIONS */}

            <div className="theme-options">


              {/* QUANT DARK */}

              <div
                className={`theme-option ${
                  theme === "quant-dark"
                    ? "selected"
                    : ""
                }`}
                onClick={() =>
                  changeTheme("quant-dark")
                }
              >

                <div className="theme-preview dark-preview"></div>

                <span>
                  Quant Dark
                </span>

                {theme === "quant-dark" && (
                  <small>
                    ✓ Active
                  </small>
                )}

              </div>



              {/* CLEAN LIGHT */}

              <div
                className={`theme-option ${
                  theme === "clean-light"
                    ? "selected"
                    : ""
                }`}
                onClick={() =>
                  changeTheme("clean-light")
                }
              >

                <div className="theme-preview light-preview"></div>

                <span>
                  Clean Light
                </span>

                {theme === "clean-light" && (
                  <small>
                    ✓ Active
                  </small>
                )}

              </div>



              {/* MIDNIGHT BLUE */}

              <div
                className={`theme-option ${
                  theme === "midnight-blue"
                    ? "selected"
                    : ""
                }`}
                onClick={() =>
                  changeTheme("midnight-blue")
                }
              >

                <div className="theme-preview midnight-preview"></div>

                <span>
                  Midnight Blue
                </span>

                {theme === "midnight-blue" && (
                  <small>
                    ✓ Active
                  </small>
                )}

              </div>


            </div>

          </section>

        </div>

      </div>

    </div>
  );
}

export default Settings;