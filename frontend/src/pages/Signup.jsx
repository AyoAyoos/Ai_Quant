import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../styles/auth.css";

export default function Signup() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] =
    useState(false);

  const [agreeTerms, setAgreeTerms] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (!agreeTerms) {
      setError(
        "Please accept the Terms of Service and Privacy Policy."
      );
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        "http://localhost:8000/auth/signup",
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
            "Account creation failed. Please try again."
        );
      }

      console.log("Signup successful:", data);

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

      // Temporary frontend-only storage
      // until backend supports full_name.
      localStorage.setItem(
        "name",
        name
      );

      navigate("/chat");
    } catch (err) {
      console.error("Signup error:", err);

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

        <section className="auth-visual signup-visual">
          <div className="brand-small">
            <div className="brand-icon">AQ</div>

            <div className="brand-text">
              <strong>AI QUANT</strong>
              <small>Quant Intelligence</small>
            </div>
          </div>

          <div className="signup-visual-content">
            <div className="login-status-badge">
              <span className="status-dot"></span>
              AI-DRIVEN STRATEGY WORKSPACE
            </div>

            {/* STRATEGY ORBIT */}
            <div className="strategy-orbit">
              <div className="orbit-circle orbit-one"></div>
              <div className="orbit-circle orbit-two"></div>
              <div className="orbit-circle orbit-three"></div>

              <div className="strategy-core">
                <div className="core-chart">
                  ↗
                </div>

                <span>AI</span>
              </div>

              <div className="orbit-node node-one">
                ✦
              </div>

              <div className="orbit-node node-two">
                ◇
              </div>

              <div className="orbit-node node-three">
                ▥
              </div>
            </div>

            <h1>
              Build Smarter.
              <br />
              <span>Trade Smarter.</span>
            </h1>

            <p className="visual-description">
              Describe your trading idea in plain language and
              use AI to transform it into a structured
              quantitative strategy.
            </p>

            {/* WORKFLOW */}
            <div className="workflow-preview">
              <div className="workflow-step">
                <span>01</span>

                <div>
                  <strong>Describe</strong>
                  <small>Trading idea</small>
                </div>
              </div>

              <div className="workflow-line"></div>

              <div className="workflow-step">
                <span>02</span>

                <div>
                  <strong>Generate</strong>
                  <small>AI strategy</small>
                </div>
              </div>

              <div className="workflow-line"></div>

              <div className="workflow-step">
                <span>03</span>

                <div>
                  <strong>Backtest</strong>
                  <small>Performance</small>
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
          <div className="auth-form-wrapper signup-form-wrapper">
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
                CREATE YOUR WORKSPACE
              </span>

              <h2>Create your account</h2>

              <p>
                Join AI QUANT and start building
                data-driven trading strategies.
              </p>
            </div>

            <form onSubmit={handleSubmit}>
              {/* FULL NAME */}
              <div className="form-group">
                <label htmlFor="name">
                  Full Name
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ◯
                  </span>

                  <input
                    id="name"
                    type="text"
                    placeholder="Enter your full name"
                    value={name}
                    onChange={(e) =>
                      setName(e.target.value)
                    }
                    autoComplete="name"
                    required
                  />
                </div>
              </div>

              {/* EMAIL */}
              <div className="form-group">
                <label htmlFor="signup-email">
                  Email Address
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ✉
                  </span>

                  <input
                    id="signup-email"
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
                <label htmlFor="signup-password">
                  Password
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ◈
                  </span>

                  <input
                    id="signup-password"
                    type={
                      showPassword
                        ? "text"
                        : "password"
                    }
                    placeholder="Create a password"
                    minLength={8}
                    value={password}
                    onChange={(e) =>
                      setPassword(e.target.value)
                    }
                    autoComplete="new-password"
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

              {/* CONFIRM PASSWORD */}
              <div className="form-group">
                <label htmlFor="confirm-password">
                  Confirm Password
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">
                    ◈
                  </span>

                  <input
                    id="confirm-password"
                    type={
                      showConfirmPassword
                        ? "text"
                        : "password"
                    }
                    placeholder="Confirm your password"
                    minLength={8}
                    value={confirmPassword}
                    onChange={(e) =>
                      setConfirmPassword(
                        e.target.value
                      )
                    }
                    autoComplete="new-password"
                    required
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() =>
                      setShowConfirmPassword(
                        !showConfirmPassword
                      )
                    }
                    aria-label={
                      showConfirmPassword
                        ? "Hide confirm password"
                        : "Show confirm password"
                    }
                  >
                    {showConfirmPassword
                      ? "◉"
                      : "○"}
                  </button>
                </div>
              </div>

              {/* TERMS */}
              <div className="terms-row">
                <label className="checkbox-container">
                  <input
                    type="checkbox"
                    checked={agreeTerms}
                    onChange={(e) =>
                      setAgreeTerms(
                        e.target.checked
                      )
                    }
                  />

                  <span className="custom-checkbox"></span>
                </label>

                <p>
                  I agree to the{" "}

                  <button
                    type="button"
                    className="inline-link"
                  >
                    Terms of Service
                  </button>

                  {" "}and{" "}

                  <button
                    type="button"
                    className="inline-link"
                  >
                    Privacy Policy
                  </button>
                </p>
              </div>

              {/* ERROR */}
              {error && (
                <div className="auth-error">
                  <span>!</span>
                  <p>{error}</p>
                </div>
              )}

              {/* CREATE ACCOUNT */}
              <button
                type="submit"
                className="primary-button"
                disabled={
                  !agreeTerms ||
                  loading
                }
              >
                <span>
                  {loading
                    ? "Creating account..."
                    : "Create Account"}
                </span>

                <span className="button-arrow">
                  →
                </span>
              </button>

              {/* LOGIN */}
              <div className="switch-auth">
                Already have an account?

                <Link to="/login">
                  Sign in
                </Link>
              </div>
            </form>

            {/* SECURITY NOTE */}
            <div className="security-note">
              <span className="security-icon">
                ✓
              </span>

              <div>
                <strong>
                  Secure account setup
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