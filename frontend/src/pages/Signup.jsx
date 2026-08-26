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
        "http://127.0.0.1:8000/auth/signup",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },

          // Current backend SignupRequest accepts
          // email and password only.
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

      // Temporary frontend storage until
      // backend User model supports full_name.
      localStorage.setItem(
        "name",
        name
      );

      navigate("/chat");

    } catch (err) {

      console.error(
        "Signup error:",
        err
      );

      setError(
        err.message
      );

    } finally {

      setLoading(false);

    }
  };

  return (
    <div className="auth-page">

      <div className="auth-background-grid"></div>

      <div className="auth-container">

        {/* LEFT SIDE */}

        <div className="auth-visual signup-visual">

          <div className="brand-small">
            <div className="brand-icon">
              ✦
            </div>

            <span>
              QuantAI
            </span>
          </div>

          <div className="signup-visual-content">

            <div className="strategy-orbit">

              <div className="orbit-circle orbit-one"></div>

              <div className="orbit-circle orbit-two"></div>

              <div className="orbit-circle orbit-three"></div>

              <div className="strategy-core">

                <div className="core-chart">
                  ↗
                </div>

                <span>
                  AI
                </span>

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
              <span>
                Trade Smarter.
              </span>
            </h1>

            <p className="visual-description">
              Describe your trading idea in plain language
              and let AI help transform it into a systematic
              strategy.
            </p>

            <div className="workflow-preview">

              <div className="workflow-step">
                <span>01</span>

                <div>
                  <strong>
                    Describe
                  </strong>

                  <small>
                    Your trading idea
                  </small>
                </div>
              </div>

              <div className="workflow-line"></div>

              <div className="workflow-step">
                <span>02</span>

                <div>
                  <strong>
                    Generate
                  </strong>

                  <small>
                    AI strategy logic
                  </small>
                </div>
              </div>

              <div className="workflow-line"></div>

              <div className="workflow-step">
                <span>03</span>

                <div>
                  <strong>
                    Backtest
                  </strong>

                  <small>
                    Historical performance
                  </small>
                </div>
              </div>

            </div>

          </div>

          <div className="visual-footer">
            Designed for systematic traders & AI enthusiasts
          </div>

        </div>

        {/* RIGHT SIDE */}

        <div className="auth-form-section">

          <div className="auth-form-wrapper signup-form-wrapper">

            <div className="mobile-brand">

              <div className="brand-icon">
                ✦
              </div>

              <span>
                QuantAI
              </span>

            </div>

            <div className="form-heading">

              <span className="eyebrow">
                GET STARTED
              </span>

              <h2>
                Create Your Account
              </h2>

              <p>
                Start building and backtesting strategies
                powered by AI.
              </p>

            </div>

            <form onSubmit={handleSubmit}>

              {/* NAME */}

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
                    required
                  />

                </div>

              </div>

              {/* EMAIL */}

              <div className="form-group">

                <label htmlFor="signup-email">
                  Email
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
                    🔒
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
                    🔒
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
                <p
                  style={{
                    color: "#ff5c5c",
                    marginBottom: "12px",
                  }}
                >
                  {error}
                </p>
              )}

              {/* SUBMIT */}

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
                    ? "Creating Account..."
                    : "Create Account"}
                </span>

                <span className="button-arrow">
                  →
                </span>

              </button>

              <div className="divider">

                <span></span>

                <p>
                  or
                </p>

                <span></span>

              </div>

              <button
                type="button"
                className="google-button"
                onClick={() =>
                  console.log(
                    "Google signup"
                  )
                }
              >

                <span className="google-icon">
                  G
                </span>

                Sign up with Google

              </button>

              <div className="switch-auth">

                Already have an account?

                <Link to="/login">
                  Login
                </Link>

              </div>

            </form>

          </div>

        </div>

      </div>

    </div>
  );
}

// import React, { useState } from "react";
// import { Link } from "react-router-dom";
// import "../styles/auth.css";

// export default function Signup() {
//   const [showPassword, setShowPassword] = useState(false);
//   const [showConfirmPassword, setShowConfirmPassword] =
//     useState(false);

//   const [agreeTerms, setAgreeTerms] = useState(false);

//   const handleSubmit = (e) => {
//     e.preventDefault();

//     // Backend registration will be connected here later.
//     console.log("Signup submitted");
//   };

//   return (
//     <div className="auth-page">
//       <div className="auth-background-grid"></div>

//       <div className="auth-container">

//         {/* LEFT SIDE */}

//         <div className="auth-visual signup-visual">

//           <div className="brand-small">
//             <div className="brand-icon">✦</div>
//             <span>QuantAI</span>
//           </div>

//           <div className="signup-visual-content">

//             <div className="strategy-orbit">

//               <div className="orbit-circle orbit-one"></div>

//               <div className="orbit-circle orbit-two"></div>

//               <div className="orbit-circle orbit-three"></div>

//               <div className="strategy-core">

//                 <div className="core-chart">
//                   ↗
//                 </div>

//                 <span>AI</span>

//               </div>

//               <div className="orbit-node node-one">
//                 ✦
//               </div>

//               <div className="orbit-node node-two">
//                 ◇
//               </div>

//               <div className="orbit-node node-three">
//                 ▥
//               </div>

//             </div>


//             <h1>
//               Build Smarter.
//               <br />
//               <span>Trade Smarter.</span>
//             </h1>

//             <p className="visual-description">
//               Describe your trading idea in plain language
//               and let AI help transform it into a systematic
//               strategy.
//             </p>


//             <div className="workflow-preview">

//               <div className="workflow-step">
//                 <span>01</span>
//                 <div>
//                   <strong>Describe</strong>
//                   <small>Your trading idea</small>
//                 </div>
//               </div>

//               <div className="workflow-line"></div>

//               <div className="workflow-step">
//                 <span>02</span>
//                 <div>
//                   <strong>Generate</strong>
//                   <small>AI strategy logic</small>
//                 </div>
//               </div>

//               <div className="workflow-line"></div>

//               <div className="workflow-step">
//                 <span>03</span>
//                 <div>
//                   <strong>Backtest</strong>
//                   <small>Historical performance</small>
//                 </div>
//               </div>

//             </div>

//           </div>

//           <div className="visual-footer">
//             Designed for systematic traders & AI enthusiasts
//           </div>

//         </div>


//         {/* RIGHT SIDE */}

//         <div className="auth-form-section">

//           <div className="auth-form-wrapper signup-form-wrapper">

//             <div className="mobile-brand">

//               <div className="brand-icon">✦</div>

//               <span>QuantAI</span>

//             </div>


//             <div className="form-heading">

//               <span className="eyebrow">
//                 GET STARTED
//               </span>

//               <h2>Create Your Account</h2>

//               <p>
//                 Start building and backtesting strategies
//                 powered by AI.
//               </p>

//             </div>


//             <form onSubmit={handleSubmit}>

//               {/* FULL NAME */}

//               <div className="form-group">

//                 <label htmlFor="name">
//                   Full Name
//                 </label>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     ◯
//                   </span>

//                   <input
//                     id="name"
//                     type="text"
//                     placeholder="Enter your full name"
//                     required
//                   />

//                 </div>

//               </div>


//               {/* EMAIL */}

//               <div className="form-group">

//                 <label htmlFor="signup-email">
//                   Email
//                 </label>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     ✉
//                   </span>

//                   <input
//                     id="signup-email"
//                     type="email"
//                     placeholder="Enter your email"
//                     required
//                   />

//                 </div>

//               </div>


//               {/* PASSWORD */}

//               <div className="form-group">

//                 <label htmlFor="signup-password">
//                   Password
//                 </label>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     🔒
//                   </span>

//                   <input
//                     id="signup-password"
//                     type={
//                       showPassword
//                         ? "text"
//                         : "password"
//                     }
//                     placeholder="Create a password"
//                     minLength="8"
//                     required
//                   />

//                   <button
//                     type="button"
//                     className="password-toggle"
//                     onClick={() =>
//                       setShowPassword(!showPassword)
//                     }
//                   >
//                     {showPassword ? "◉" : "○"}
//                   </button>

//                 </div>

//               </div>


//               {/* CONFIRM PASSWORD */}

//               <div className="form-group">

//                 <label htmlFor="confirm-password">
//                   Confirm Password
//                 </label>

//                 <div className="input-wrapper">

//                   <span className="input-icon">
//                     🔒
//                   </span>

//                   <input
//                     id="confirm-password"
//                     type={
//                       showConfirmPassword
//                         ? "text"
//                         : "password"
//                     }
//                     placeholder="Confirm your password"
//                     minLength="8"
//                     required
//                   />

//                   <button
//                     type="button"
//                     className="password-toggle"
//                     onClick={() =>
//                       setShowConfirmPassword(
//                         !showConfirmPassword
//                       )
//                     }
//                   >
//                     {showConfirmPassword ? "◉" : "○"}
//                   </button>

//                 </div>

//               </div>


//               {/* TERMS */}

//               <div className="terms-row">

//                 <label className="checkbox-container">

//                   <input
//                     type="checkbox"
//                     checked={agreeTerms}
//                     onChange={(e) =>
//                       setAgreeTerms(e.target.checked)
//                     }
//                     required
//                   />

//                   <span className="custom-checkbox"></span>

//                 </label>

//                 <p>
//                   I agree to the{" "}
//                   <button
//                     type="button"
//                     className="inline-link"
//                   >
//                     Terms of Service
//                   </button>{" "}
//                   and{" "}
//                   <button
//                     type="button"
//                     className="inline-link"
//                   >
//                     Privacy Policy
//                   </button>
//                 </p>

//               </div>


//               {/* SIGN UP BUTTON */}

//               <button
//                 type="submit"
//                 className="primary-button"
//                 disabled={!agreeTerms}
//               >

//                 <span>Create Account</span>

//                 <span className="button-arrow">
//                   →
//                 </span>

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
//                   console.log("Google signup")
//                 }
//               >

//                 <span className="google-icon">
//                   G
//                 </span>

//                 Sign up with Google

//               </button>


//               {/* LOGIN */}

//               <div className="switch-auth">

//                 Already have an account?

//                 <Link to="/login">
//                   Login
//                 </Link>

//               </div>

//             </form>


//             <div className="security-note">

//               <span>🔒</span>

//               <div>

//                 <strong>Secure by design</strong>

//                 <small>
//                   Your credentials are protected.
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

//             <strong>
//               AI Strategy Generation
//             </strong>

//             <small>
//               Turn ideas into trading logic
//             </small>

//           </div>

//         </div>


//         <div className="website-feature">

//           <span>▥</span>

//           <div>

//             <strong>
//               Historical Backtesting
//             </strong>

//             <small>
//               Evaluate your strategy
//             </small>

//           </div>

//         </div>


//         <div className="website-feature">

//           <span>◇</span>

//           <div>

//             <strong>
//               Paper Trading
//             </strong>

//             <small>
//               Practice without real money
//             </small>

//           </div>

//         </div>


//         <div className="website-feature">

//           <span>🔒</span>

//           <div>

//             <strong>
//               Secure Account
//             </strong>

//             <small>
//               Your data stays protected
//             </small>

//           </div>

//         </div>

//       </div>

//     </div>
//   );
// }