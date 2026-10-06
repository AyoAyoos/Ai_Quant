import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Login — frontend-prototype credentials form.
 *
 * Any non-empty email/password passes. On success the user is sent back to
 * the route that bounced them here (location.state.from) or to the dashboard.
 */
export default function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')

  // Already signed in: skip the form and go to the dashboard (or back to the saved page).
  if (isAuthenticated) {
    return <Navigate to={location.state?.from?.pathname || '/dashboard'} replace />
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter your email address and password to log in.')
      return
    }
    setError('')
    login(email.trim(), password)
    void remember
    navigate(location.state?.from?.pathname || '/dashboard', { replace: true })
  }

  return (
    <div className="auth-wrap">
      <div className="auth-col">
        <Link className="auth-back" to="/">
          <Icon name="arrow_back" size={18} />
          Back 
        </Link>
        <section className="auth-card" aria-labelledby="login-title">
        <svg className="auth-logo" viewBox="0 0 64 52" aria-hidden="true" focusable="false">
          <path d="M32 34 50 50H14Z" fill="#d9c6e2" />
          <path d="M32 18 46 38H18Z" fill="#af719d" />
          <path d="M32 2 42 20H22Z" fill="#8b639b" />
        </svg>
        <h1 className="auth-title" id="login-title">
          Log In to Your Account
        </h1>

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="field">
            <label className="field__label" htmlFor="login-email">
              Email Address
            </label>
            <div className="field__control">
              <input
                className="field__input"
                id="login-email"
                name="email"
                type="email"
                autoComplete="username"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="login-password">
              Password
            </label>
            <div className="field__control">
              <input
                className="field__input"
                id="login-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                className="auth-toggle"
                type="button"
                onClick={() => setShowPassword((visible) => !visible)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
              >
                <Icon name={showPassword ? 'visibility_off' : 'visibility'} size={19} />
              </button>
            </div>
          </div>

          <div className="auth-row">
            <label className="auth-check" htmlFor="login-remember">
              <input
                id="login-remember"
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              Remember Me
            </label>
            <Link className="auth-link" to="/login">
              Forgot Password?
            </Link>
          </div>

          <button className="auth-submit" type="submit">
            Log in
          </button>
          {error && (
            <p className="field__error" role="alert">
              {error}
            </p>
          )}

          <div className="auth-divider" role="separator" aria-orientation="horizontal">
            <span>OR</span>
          </div>

          <button className="auth-google" type="button">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path
                fill="#4285F4"
                d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47c-.29 1.48-1.14 2.73-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.27 14.29c-.25-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.98-3.09z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75z"
              />
            </svg>
            Sign in with Google
          </button>
        </form>

        <p className="auth-foot">
          Don&apos;t have an account? <Link to="/login">Sign up</Link>
        </p>
        </section>
      </div>
    </div>
  )
}
