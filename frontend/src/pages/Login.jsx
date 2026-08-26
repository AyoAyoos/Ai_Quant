function Login() {
  return (
    <div className="login-page">

      <div className="login-brand">
        <div className="logo-mark">Q</div>

        <h1>AI QUANT</h1>

        <p>
          Quant Intelligence Platform
        </p>

        <div className="login-tagline">
          Turn your trading ideas into
          <strong> intelligent strategies.</strong>
        </div>
      </div>


      <div className="login-card">

        <div className="login-header">
          <p className="eyebrow">WELCOME BACK</p>

          <h2>Sign in to AI Quant</h2>

          <p>
            Continue building and analyzing your trading strategies.
          </p>
        </div>


        <form>

          <div className="form-group">
            <label>Email Address</label>

            <input
              type="email"
              placeholder="you@example.com"
            />
          </div>


          <div className="form-group">
            <label>Password</label>

            <input
              type="password"
              placeholder="Enter your password"
            />
          </div>


          <div className="login-options">

            <label className="remember">
              <input type="checkbox" />
              Remember me
            </label>

            <button type="button" className="forgot-button">
              Forgot password?
            </button>

          </div>


          <button
            type="button"
            className="primary-button login-button"
          >
            Sign In →
          </button>

        </form>


        <div className="divider">
          <span>OR</span>
        </div>


        <button className="google-button">
          Continue with Google
        </button>


        <p className="signup-text">
          Don't have an account?
          <button className="signup-button">
            Create account
          </button>
        </p>

      </div>


      <div className="login-footer">
        Educational prototype • Paper trading only • No guaranteed returns
      </div>

    </div>
  );
}

export default Login;