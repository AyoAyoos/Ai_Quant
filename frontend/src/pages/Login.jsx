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
        "http://127.0.0.1:8000/auth/login",
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
          data.detail || "Login failed. Please check your credentials."
        );
      }

      console.log("Login successful:", data);

      if (rememberMe) {
        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user_id", data.user_id);
        localStorage.setItem("email", data.email);
      } else {
        sessionStorage.setItem("access_token", data.access_token);
        sessionStorage.setItem("user_id", data.user_id);
        sessionStorage.setItem("email", data.email);
      }

      navigate("/chat");
    } catch (err) {
      console.error("Login error:", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-background-grid"></div>

      <div className="auth-container">

        {/* LEFT SIDE */}
        <div className="auth-visual login-visual">

          <div className="brand-small">
            <div className="brand-icon">✦</div>
            <span>QuantAI</span>
          </div>

          <div className="visual-content">

            <div className="ai-symbol">
              <div className="ai-brain">
                <span>AI</span>
              </div>
            </div>

            <h1>
              AI-Powered
              <br />
              <span>Quant Trading</span>
            </h1>

            <p className="visual-description">
              Turn your trading ideas into strategies,
              backtest them, and explore paper trading
              with the power of AI.
            </p>

            <div className="trading-chart">
              <div className="chart-grid"></div>

              <div className="candles">
                <div className="candle candle-1"><span></span></div>
                <div className="candle candle-2"><span></span></div>
                <div className="candle candle-3"><span></span></div>
                <div className="candle candle-4"><span></span></div>
                <div className="candle candle-5"><span></span></div>
                <div className="candle candle-6"><span></span></div>
                <div className="candle candle-7"><span></span></div>
                <div className="candle candle-8"><span></span></div>
                <div className="candle candle-9"><span></span></div>
                <div className="candle candle-10"><span></span></div>
              </div>

              <div className="chart-line"></div>
            </div>

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
                  <small>Historical data</small>
                </div>
              </div>

              <div className="feature-item">
                <span className="feature-icon">◇</span>
                <div>
                  <strong>Paper Trading</strong>
                  <small>Risk-free testing</small>
                </div>
              </div>

            </div>

          </div>

          <div className="visual-footer">
            Built for smarter systematic trading
          </div>

        </div>

        {/* RIGHT SIDE */}
        <div className="auth-form-section">

          <div className="auth-form-wrapper">

            <div className="mobile-brand">
              <div className="brand-icon">✦</div>
              <span>QuantAI</span>
            </div>

            <div className="form-heading">
              <span className="eyebrow">WELCOME BACK</span>
              <h2>Welcome Back</h2>
              <p>Login to continue your trading journey.</p>
            </div>

            <form onSubmit={handleSubmit}>

              <div className="form-group">
                <label htmlFor="email">
                  Email
                </label>

                <div className="input-wrapper">
                  <span className="input-icon">✉</span>

                  <input
                    id="email"
                    type="email"
                    placeholder="Enter your email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

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
                  <span className="input-icon">🔒</span>

                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() =>
                      setShowPassword(!showPassword)
                    }
                  >
                    {showPassword ? "◉" : "○"}
                  </button>
                </div>
              </div>

              <div className="remember-row">

                <label className="checkbox-container">

                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) =>
                      setRememberMe(e.target.checked)
                    }
                  />

                  <span className="custom-checkbox"></span>

                  Remember me
                </label>

              </div>

              {error && (
                <p
                  style={{
                    color: "#ff5c5c",
                    marginBottom: "12px",
                  }}
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                className="primary-button"
                disabled={loading}
              >
                <span>
                  {loading ? "Logging in..." : "Login"}
                </span>

                <span className="button-arrow">→</span>
              </button>

              <div className="divider">
                <span></span>
                <p>or</p>
                <span></span>
              </div>

              <button
                type="button"
                className="google-button"
                onClick={() =>
                  console.log("Google login")
                }
              >
                <span className="google-icon">G</span>
                Continue with Google
              </button>

              <div className="switch-auth">
                Don't have an account?

                <Link to="/signup">
                  Sign up
                </Link>
              </div>

            </form>

            <div className="security-note">
              <span>🔒</span>

              <div>
                <strong>Your data is secure</strong>

                <small>
                  We protect your account and trading data.
                </small>
              </div>
            </div>

          </div>

        </div>

      </div>

    </div>
  );
}
// import React, { useState } from "react";
// import { Link } from "react-router-dom";
// import "../styles/auth.css";

// export default function Login() {
//   const [showPassword, setShowPassword] = useState(false);
//   const [rememberMe, setRememberMe] = useState(false);

//   const handleSubmit = (e) => {
//     e.preventDefault();

//     // Backend authentication will be connected here later.
//     console.log("Login submitted");
//   };

//   return (
//     <div className="auth-page">
//       <div className="auth-background-grid"></div>

//       <div className="auth-container">

//         {/* LEFT SIDE */}
//         <div className="auth-visual login-visual">

//           <div className="brand-small">
//             <div className="brand-icon">✦</div>
//             <span>QuantAI</span>
//           </div>

//           <div className="visual-content">

//             <div className="ai-symbol">
//               <div className="ai-brain">
//                 <span>AI</span>
//               </div>
//             </div>

//             <h1>
//               AI-Powered
//               <br />
//               <span>Quant Trading</span>
//             </h1>

//             <p className="visual-description">
//               Turn your trading ideas into strategies,
//               backtest them, and explore paper trading
//               with the power of AI.
//             </p>

//             <div className="trading-chart">

//               <div className="chart-grid"></div>

//               <div className="candles">

//                 <div className="candle candle-1">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-2">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-3">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-4">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-5">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-6">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-7">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-8">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-9">
//                   <span></span>
//                 </div>

//                 <div className="candle candle-10">
//                   <span></span>
//                 </div>

//               </div>

//               <div className="chart-line"></div>
//             </div>

//             <div className="feature-row">

//               <div className="feature-item">
//                 <span className="feature-icon">✦</span>
//                 <div>
//                   <strong>AI Strategy</strong>
//                   <small>Natural language</small>
//                 </div>
//               </div>

//               <div className="feature-item">
//                 <span className="feature-icon">▥</span>
//                 <div>
//                   <strong>Backtesting</strong>
//                   <small>Historical data</small>
//                 </div>
//               </div>

//               <div className="feature-item">
//                 <span className="feature-icon">◇</span>
//                 <div>
//                   <strong>Paper Trading</strong>
//                   <small>Risk-free testing</small>
//                 </div>
//               </div>

//             </div>

//           </div>

//           <div className="visual-footer">
//             Built for smarter systematic trading
//           </div>

//         </div>


//         {/* RIGHT SIDE */}
//         <div className="auth-form-section">

//           <div className="auth-form-wrapper">

//             <div className="mobile-brand">
//               <div className="brand-icon">✦</div>
//               <span>QuantAI</span>
//             </div>

//             <div className="form-heading">
//               <span className="eyebrow">WELCOME BACK</span>

//               <h2>Welcome Back</h2>

//               <p>
//                 Login to continue your trading journey.
//               </p>
//             </div>


//             <form onSubmit={handleSubmit}>

//               {/* EMAIL */}

//               <div className="form-group">

//                 <label htmlFor="email">
//                   Email
//                 </label>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     ✉
//                   </span>

//                   <input
//                     id="email"
//                     type="email"
//                     placeholder="Enter your email"
//                     required
//                   />

//                 </div>

//               </div>


//               {/* PASSWORD */}

//               <div className="form-group">

//                 <div className="label-row">

//                   <label htmlFor="password">
//                     Password
//                   </label>

//                   <button
//                     type="button"
//                     className="forgot-password"
//                     onClick={() =>
//                       console.log("Forgot password")
//                     }
//                   >
//                     Forgot Password?
//                   </button>

//                 </div>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     🔒
//                   </span>

//                   <input
//                     id="password"
//                     type={showPassword ? "text" : "password"}
//                     placeholder="Enter your password"
//                     required
//                   />

//                   <button
//                     type="button"
//                     className="password-toggle"
//                     onClick={() =>
//                       setShowPassword(!showPassword)
//                     }
//                     aria-label="Toggle password visibility"
//                   >
//                     {showPassword ? "◉" : "○"}
//                   </button>

//                 </div>

//               </div>


//               {/* REMEMBER ME */}

//               <div className="remember-row">

//                 <label className="checkbox-container">

//                   <input
//                     type="checkbox"
//                     checked={rememberMe}
//                     onChange={(e) =>
//                       setRememberMe(e.target.checked)
//                     }
//                   />

//                   <span className="custom-checkbox"></span>

//                   Remember me

//                 </label>

//               </div>


//               {/* LOGIN BUTTON */}

//               <button
//                 type="submit"
//                 className="primary-button"
//               >
//                 <span>Login</span>
//                 <span className="button-arrow">→</span>
//               </button>


//               {/* DIVIDER */}

//               <div className="divider">
//                 <span></span>
//                 <p>or</p>
//                 <span></span>
//               </div>


//               {/* GOOGLE */}

//               <button
//                 type="button"
//                 className="google-button"
//                 onClick={() =>
//                   console.log("Google login")
//                 }
//               >
//                 <span className="google-icon">G</span>
//                 Continue with Google
//               </button>


//               {/* SIGN UP */}

//               <div className="switch-auth">

//                 Don't have an account?

//                 <Link to="/signup">
//                   Sign up
//                 </Link>

//               </div>

//             </form>


//             <div className="security-note">

//               <span>🔒</span>

//               <div>
//                 <strong>Your data is secure</strong>
//                 <small>
//                   We protect your account and trading data.
//                 </small>
//               </div>

//             </div>

//           </div>

//         </div>

//       </div>


//       {/* BOTTOM FEATURES */}

//       <div className="website-features">

//         <div className="website-feature">
//           <span>✦</span>
//           <div>
//             <strong>AI Strategy Generation</strong>
//             <small>
//               Describe your trading idea naturally
//             </small>
//           </div>
//         </div>

//         <div className="website-feature">
//           <span>▥</span>
//           <div>
//             <strong>Backtesting Engine</strong>
//             <small>
//               Evaluate strategies on historical data
//             </small>
//           </div>
//         </div>

//         <div className="website-feature">
//           <span>◇</span>
//           <div>
//             <strong>Paper Trading</strong>
//             <small>
//               Test strategies without real money
//             </small>
//           </div>
//         </div>

//         <div className="website-feature">
//           <span>🔒</span>
//           <div>
//             <strong>Secure & Private</strong>
//             <small>
//               Your account and strategies stay protected
//             </small>
//           </div>
//         </div>

//       </div>

//     </div>
//   );
// }


