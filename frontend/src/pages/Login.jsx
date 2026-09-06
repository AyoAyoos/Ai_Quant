import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../styles/auth.css";

export default function Login() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError("");
    setLoading(true);

    try {
      const response = await fetch(
        "http://localhost:8000/auth/login",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
            password,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail ||
            "Login failed. Please check your credentials."
        );
      }

      console.log("Login successful:", data);

      if (rememberMe) {
        localStorage.setItem(
          "access_token",
          data.access_token
        );
        localStorage.setItem(
          "user_id",
          data.user_id
        );
        localStorage.setItem(
          "email",
          data.email
        );
      } else {
        sessionStorage.setItem(
          "access_token",
          data.access_token
        );
        sessionStorage.setItem(
          "user_id",
          data.user_id
        );
        sessionStorage.setItem(
          "email",
          data.email
        );
      }

      navigate("/chat");
    } catch (err) {
      console.error("Login error:", err);

      if (err instanceof TypeError) {
        setError(
          "Unable to connect to the server. Please make sure the backend is running."
        );
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-background-grid"></div>

      <div className="auth-container">
        {/* ================= LEFT SIDE ================= */}

        <section className="auth-visual login-visual">
          <div className="brand-small">
            <div className="brand-icon">AQ</div>

            <div className="brand-text">
              <strong>AI QUANT</strong>
              <small>Quant Intelligence</small>
            </div>
          </div>

          <div className="visual-content">
            <div className="login-status-badge">
              <span className="status-dot"></span>
              AI-POWERED QUANT PLATFORM
            </div>

            <div className="ai-symbol">
              <div className="ai-brain">
                <span>AI</span>
              </div>
            </div>

            <h1>
              Intelligent Trading.
              <br />
              <span>Powered by AI.</span>
            </h1>

            <p className="visual-description">
              Transform trading ideas into systematic strategies,
              backtest them using historical data and explore
              quantitative trading through AI.
            </p>

            {/* TRADING CHART */}
            <div className="trading-chart">
              <div className="chart-grid"></div>

              <div className="chart-top-row">
                <div>
                  <small>NIFTY 50</small>
                  <strong>Market Intelligence</strong>
                </div>

                <span className="market-status">
                  ● LIVE
                </span>
              </div>

              <div className="candles">
                <div className="candle candle-1"></div>
                <div className="candle candle-2"></div>
                <div className="candle candle-3"></div>
                <div className="candle candle-4"></div>
                <div className="candle candle-5"></div>
                <div className="candle candle-6"></div>
                <div className="candle candle-7"></div>
                <div className="candle candle-8"></div>
                <div className="candle candle-9"></div>
                <div className="candle candle-10"></div>
              </div>

              <div className="chart-line"></div>
            </div>

            {/* FEATURES */}
            <div className="feature-row">
              <div className="feature-item">
                <span className="feature-icon">✦</span>

                <div>
                  <strong>AI Strategy</strong>
                  <small>Natural language</small>
                </div>
              </div>

              <div className="feature-item">
                <span className="feature-icon">▥</span>

                <div>
                  <strong>Backtesting</strong>
                  <small>Historical analysis</small>
                </div>
              </div>

              <div className="feature-item">
                <span className="feature-icon">↗</span>

                <div>
                  <strong>Analytics</strong>
                  <small>Quant insights</small>
                </div>
              </div>
            </div>
          </div>

          <div className="visual-footer">
            AI QUANT • Quant Intelligence Platform
          </div>
        </section>

        {/* ================= RIGHT SIDE ================= */}

        <section className="auth-form-section">
          <div className="auth-form-wrapper">
            {/* MOBILE BRAND */}
            <div className="mobile-brand">
              <div className="brand-icon">AQ</div>

              <div className="brand-text">
                <strong>AI QUANT</strong>
                <small>Quant Intelligence</small>
              </div>
            </div>

            {/* HEADING */}
            <div className="form-heading">
              <span className="eyebrow">
                SECURE ACCESS
              </span>

              <h2>Welcome back</h2>

              <p>
                Sign in to access your AI Quant workspace.
              </p>
            </div>

            <form onSubmit={handleSubmit}>
              {/* EMAIL */}
              <div className="form-group">
                <label htmlFor="email">
                  Email Address
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ✉
                  </span>

                  <input
                    id="email"
                    type="email"
                    placeholder="Enter your email"
                    value={email}
                    onChange={(e) =>
                      setEmail(e.target.value)
                    }
                    autoComplete="email"
                    required
                  />
                </div>
              </div>

              {/* PASSWORD */}
              <div className="form-group">
                <div className="label-row">
                  <label htmlFor="password">
                    Password
                  </label>

                  <button
                    type="button"
                    className="forgot-password"
                    onClick={() =>
                      console.log("Forgot password")
                    }
                  >
                    Forgot Password?
                  </button>
                </div>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ◈
                  </span>

                  <input
                    id="password"
                    type={
                      showPassword
                        ? "text"
                        : "password"
                    }
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) =>
                      setPassword(e.target.value)
                    }
                    autoComplete="current-password"
                    required
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() =>
                      setShowPassword(
                        !showPassword
                      )
                    }
                    aria-label={
                      showPassword
                        ? "Hide password"
                        : "Show password"
                    }
                  >
                    {showPassword ? "◉" : "○"}
                  </button>
                </div>
              </div>

              {/* REMEMBER ME */}
              <div className="remember-row">
                <label className="checkbox-container">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) =>
                      setRememberMe(
                        e.target.checked
                      )
                    }
                  />

                  <span className="custom-checkbox"></span>

                  Remember me
                </label>
              </div>

              {/* ERROR */}
              {error && (
                <div className="auth-error">
                  <span>!</span>
                  <p>{error}</p>
                </div>
              )}

              {/* LOGIN */}
              <button
                type="submit"
                className="primary-button"
                disabled={loading}
              >
                <span>
                  {loading
                    ? "Signing in..."
                    : "Sign In"}
                </span>

                <span className="button-arrow">
                  →
                </span>
              </button>

              {/* SIGNUP */}
              <div className="switch-auth">
                New to AI QUANT?

                <Link to="/signup">
                  Create account
                </Link>
              </div>
            </form>

            {/* SECURITY */}
            <div className="security-note">
              <span className="security-icon">
                ✓
              </span>

              <div>
                <strong>
                  Secure authentication
                </strong>

                <small>
                  Your account information is protected.
                </small>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}