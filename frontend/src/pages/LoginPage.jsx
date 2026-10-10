import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import { FIXED_EMAIL, FIXED_PASSWORD, useAuth } from '../context/AuthContext.jsx'

/**
 * Dummy login — no auth provider. Only the fixed local credential passes:
 *   admin@local / admin
 */
export default function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (isAuthenticated) {
    return <Navigate to={location.state?.from?.pathname || '/dashboard'} replace />
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter the login email and password.')
      return
    }
    setBusy(true)
    const result = await login(email, password)
    setBusy(false)
    if (!result.ok) {
      setError(result.message || 'Sign-in failed.')
      return
    }
    setError('')
    window.location.assign(location.state?.from?.pathname || '/dashboard')
  }

  return (
    <div className="authx">
      <div className="authx__panel authx__panel--form">
        <Link className="authx__brand" to="/" aria-label="QuantNiti home">
          <img
            className="authx__brand-logo"
            src="/svg/logo-horizontal/logo-horizontal-on-dark.svg"
            alt="QuantNiti"
            width={124}
            height={30}
          />
        </Link>

        <div className="authx__wrap">
          <div className="authx__body" aria-live="polite">
            <h1 className="authx__title" tabIndex={-1}>
              Sign In
            </h1>
            <p className="authx__sub">
              Local login — use <strong>{FIXED_EMAIL}</strong> / <strong>{FIXED_PASSWORD}</strong>.
            </p>

            <form className="authx__form" onSubmit={handleSubmit} noValidate>
              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-email">
                  Email
                </label>
                <input
                  className="authx__input"
                  id="auth-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  placeholder={FIXED_EMAIL}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-password">
                  Password
                </label>
                <div className="authx__control">
                  <input
                    className="authx__control-input"
                    id="auth-password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder={FIXED_PASSWORD}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    className="authx__peek"
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                  >
                    <Icon name={showPassword ? 'visibility_off' : 'visibility'} size={19} />
                  </button>
                </div>
              </div>

              {error && (
                <p className="authx__error" role="alert">
                  {error}
                </p>
              )}
              <button className="authx__submit" type="submit" disabled={busy}>
                {busy ? 'Signing In…' : 'Sign In'}
              </button>
            </form>
          </div>
        </div>
      </div>

      <div className="authx__panel authx__panel--art">
        <div className="art" aria-hidden="true">
          <span className="art__orb art__orb--a" />
          <span className="art__orb art__orb--b" />
          <span className="art__ring" />
        </div>
      </div>
    </div>
  )
}
