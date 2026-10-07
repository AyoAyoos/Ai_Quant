import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import Icon from '../components/Icon.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const OTP_LEN = 6
const RESEND_SECONDS = 30

const LEFT_CANDLES = [
  { h: 56, up: true },
  { h: 92, up: false },
  { h: 44, up: true },
  { h: 76, up: true },
]

const RIGHT_CANDLES = [
  { h: 72, up: false },
  { h: 48, up: true },
  { h: 98, up: true },
  { h: 60, up: false },
  { h: 44, up: true },
]

const SOCIALS = [
  {
    label: 'Continue with Google',
    svg: (
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
    ),
  },
  {
    label: 'Continue with GitHub',
    svg: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
        />
      </svg>
    ),
  },
  {
    label: 'Continue with Apple',
    svg: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.702"
        />
      </svg>
    ),
  },
]

/**
 * Auth — borderless immersive entry (frontend prototype, no backend yet).
 *
 * State machine (React state only, no reloads):
 *   tab:   'signin' | 'signup'            (equal-prominence entry options)
 *   stage: 'form' | 'forgot-email' | 'forgot-otp' | 'reset-done'
 *
 * Sign in / sign up use the existing prototype session (same as before).
 * Social buttons and the forgot-password OTP flow are UI-only until the
 * real APIs exist.
 */
export default function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [tab, setTab] = useState('signin')
  const [stage, setStage] = useState('form')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [recoveryEmail, setRecoveryEmail] = useState('')
  const [otp, setOtp] = useState(() => Array(OTP_LEN).fill(''))
  const [cooldown, setCooldown] = useState(0)
  const [notice, setNotice] = useState('')
  const [errors, setErrors] = useState({})

  const headingRef = useRef(null)
  const otpRefs = useRef([])

  const redirectAfterAuth = () => {
    navigate(location.state?.from?.pathname || '/dashboard', { replace: true })
  }

  // Move screen-reader + keyboard focus to the new heading on every transition.
  useEffect(() => {
    headingRef.current?.focus?.()
  }, [tab, stage])

  // Resend-code cooldown ticker.
  useEffect(() => {
    if (stage !== 'forgot-otp' || cooldown <= 0) return undefined
    const timer = window.setTimeout(() => setCooldown((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [stage, cooldown])

  // Already signed in: skip auth and go back (same redirect as before).
  if (isAuthenticated) {
    return <Navigate to={location.state?.from?.pathname || '/dashboard'} replace />
  }

  const switchTab = (next) => {
    setTab(next)
    setStage('form')
    setErrors({})
    setNotice('')
    setShowPassword(false)
  }

  const goForgot = () => {
    setStage('forgot-email')
    setRecoveryEmail(email)
    setErrors({})
    setNotice('')
  }

  const backToLogin = () => {
    setTab('signin')
    setStage('form')
    setErrors({})
    setNotice('')
  }

  const handleSocial = (label) => {
    setNotice(`${label} is not available in this prototype yet.`)
  }

  const handleSignIn = (event) => {
    event.preventDefault()
    const next = {}
    if (!EMAIL_RE.test(email.trim())) next.email = 'Enter a valid email address.'
    if (!password) next.password = 'Enter your password.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    login(email.trim(), password)
    redirectAfterAuth()
  }

  const handleSignUp = (event) => {
    event.preventDefault()
    const next = {}
    if (!EMAIL_RE.test(email.trim())) next.email = 'Enter a valid email address.'
    if (password.length < 8) next.password = 'Use at least 8 characters.'
    if (confirm !== password) next.confirm = 'Passwords do not match.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    login(email.trim(), password)
    redirectAfterAuth()
  }

  const handleSendOtp = (event) => {
    event.preventDefault()
    if (!EMAIL_RE.test(recoveryEmail.trim())) {
      setErrors({ recoveryEmail: 'Enter a valid email address.' })
      return
    }
    setErrors({})
    setNotice('')
    setOtp(Array(OTP_LEN).fill(''))
    setCooldown(RESEND_SECONDS)
    setStage('forgot-otp')
  }

  const focusOtp = (index) => {
    otpRefs.current[index]?.focus?.()
    otpRefs.current[index]?.select?.()
  }

  const handleOtpChange = (index, value) => {
    const digit = value.replace(/\D/g, '').slice(-1)
    setOtp((prev) => {
      const next = [...prev]
      next[index] = digit
      return next
    })
    setErrors({})
    if (digit && index < OTP_LEN - 1) focusOtp(index + 1)
  }

  const handleOtpKeyDown = (index, event) => {
    if (event.key !== 'Backspace') return
    if (otp[index]) return // clear handled by change; stay put
    if (index > 0) {
      event.preventDefault()
      focusOtp(index - 1)
    }
  }

  const handleOtpPaste = (event) => {
    const digits = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LEN)
    if (!digits) return
    event.preventDefault()
    setOtp(Array.from({ length: OTP_LEN }, (_, i) => digits[i] || ''))
    setErrors({})
    focusOtp(Math.min(digits.length, OTP_LEN - 1))
  }

  const handleVerifyOtp = (event) => {
    event.preventDefault()
    if (otp.some((d) => !d)) {
      setErrors({ otp: 'Enter all 6 digits of the verification code.' })
      return
    }
    setErrors({})
    setStage('reset-done')
  }

  const handleResend = () => {
    if (cooldown > 0) return
    setOtp(Array(OTP_LEN).fill(''))
    setErrors({})
    setNotice('A new code was sent. (Prototype: any 6-digit code works.)')
    setCooldown(RESEND_SECONDS)
    focusOtp(0)
  }

  const stateHeading =
    // eslint-disable-next-line no-nested-ternary
    stage === 'forgot-email'
      ? 'Reset Password'
      : // eslint-disable-next-line no-nested-ternary
        stage === 'forgot-otp'
        ? 'Enter Verification Code'
        : stage === 'reset-done'
          ? "You're Verified"
          : tab === 'signup'
            ? 'Create Account'
            : 'Sign In'

  return (
    <div className="authx">
      <div className="art" aria-hidden="true">
        <svg className="art__trend art__trend--top" viewBox="0 0 1200 160" preserveAspectRatio="none">
          <path
            d="M-20,120 C200,100 340,130 560,80 S880,30 1220,70"
            fill="none"
            stroke="#AF719D"
            strokeWidth="2.5"
            strokeOpacity="0.55"
          />
          <path
            d="M-20,135 C240,120 420,140 640,95 S940,60 1220,95"
            fill="none"
            stroke="#F8B2B2"
            strokeWidth="1.5"
            strokeOpacity="0.4"
            strokeDasharray="7 7"
          />
        </svg>
        <svg
          className="art__trend art__trend--bottom"
          viewBox="0 0 1200 160"
          preserveAspectRatio="none"
        >
          <path
            d="M-20,40 C220,60 420,25 640,70 S940,120 1220,80"
            fill="none"
            stroke="#8B639B"
            strokeWidth="2.5"
            strokeOpacity="0.55"
          />
          <path
            d="M-20,25 C260,45 460,20 700,60 S960,105 1220,60"
            fill="none"
            stroke="#F8B2B2"
            strokeWidth="1.5"
            strokeOpacity="0.35"
            strokeDasharray="7 7"
          />
        </svg>

        <div className="art__candles art__candles--left">
          {LEFT_CANDLES.map((c, i) => (
            <span
              key={i}
              className={`candle${c.up ? ' candle--up' : ' candle--down'}`}
              style={{ height: `${c.h}px` }}
            />
          ))}
        </div>
        <div className="art__candles art__candles--right">
          {RIGHT_CANDLES.map((c, i) => (
            <span
              key={i}
              className={`candle${c.up ? ' candle--up' : ' candle--down'}`}
              style={{ height: `${c.h}px` }}
            />
          ))}
        </div>

        <span className="art__chip art__chip--a">
          <Icon name="trending_up" size={16} />
          +12.4% NIFTY 50
        </span>
        <span className="art__chip art__chip--b">Sharpe 1.84</span>
        <span className="art__chip art__chip--c">
          <Icon name="trending_down" size={16} />
          −2.1% drawdown
        </span>
        <span className="art__chip art__chip--d">CAGR +18.2%</span>

        <span className="art__orb art__orb--a" />
        <span className="art__orb art__orb--b" />
        <span className="art__ring" />
      </div>

      <div className="authx__wrap">
        {stage === 'form' && (
          <div className="authx__tabs" role="tablist" aria-label="Choose an action">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'signup'}
              className={`authx__tab${tab === 'signup' ? ' authx__tab--active' : ''}`}
              onClick={() => switchTab('signup')}
            >
              Create Account
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'signin'}
              className={`authx__tab${tab === 'signin' ? ' authx__tab--active' : ''}`}
              onClick={() => switchTab('signin')}
            >
              Log In
            </button>
          </div>
        )}

        <div className="authx__body" key={`${tab}-${stage}`} aria-live="polite">
          <h1 className="authx__title" id="auth-title" ref={headingRef} tabIndex={-1}>
            {stateHeading}
          </h1>

          {stage === 'forgot-email' && (
            <p className="authx__sub">Enter your email address to receive a verification code.</p>
          )}
          {stage === 'forgot-otp' && (
            <p className="authx__sub">
              We&apos;ve sent a code to <strong>{recoveryEmail.trim()}</strong>.
            </p>
          )}
          {stage === 'reset-done' && (
            <p className="authx__sub">
              Code verified for <strong>{recoveryEmail.trim()}</strong>. This is a UI prototype —
              setting a new password will work once the recovery API exists.
            </p>
          )}

          {stage === 'form' && tab === 'signin' && (
            <form className="authx__form" onSubmit={handleSignIn} noValidate>
              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-email">
                  Email
                </label>
                <input
                  className={`authx__input${errors.email ? ' authx__input--error' : ''}`}
                  id="auth-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'auth-email-err' : undefined}
                />
                {errors.email && (
                  <p className="authx__error" id="auth-email-err" role="alert">
                    {errors.email}
                  </p>
                )}
              </div>

              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-password">
                  Password
                </label>
                <div className={`authx__control${errors.password ? ' authx__control--error' : ''}`}>
                  <input
                    className="authx__control-input"
                    id="auth-password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={errors.password ? 'auth-password-err' : undefined}
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
                {errors.password && (
                  <p className="authx__error" id="auth-password-err" role="alert">
                    {errors.password}
                  </p>
                )}
                <div className="authx__row">
                  <span />
                  <button type="button" className="authx__link" onClick={goForgot}>
                    Forgot Password?
                  </button>
                </div>
              </div>

              <button className="authx__submit" type="submit">
                Sign In
              </button>

              <div className="authx__or" role="separator">
                <span>or continue with</span>
              </div>

              <div className="authx__socials">
                {SOCIALS.map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    className="authx__social"
                    aria-label={s.label}
                    title={s.label}
                    onClick={() => handleSocial(s.label)}
                  >
                    {s.svg}
                  </button>
                ))}
              </div>

              {notice && (
                <p className="authx__notice" role="status">
                  {notice}
                </p>
              )}

              <p className="authx__foot">
                Don&apos;t have an account?{' '}
                <button type="button" className="authx__link" onClick={() => switchTab('signup')}>
                  Create one.
                </button>
              </p>
            </form>
          )}

          {stage === 'form' && tab === 'signup' && (
            <form className="authx__form" onSubmit={handleSignUp} noValidate>
              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-new-email">
                  Email
                </label>
                <input
                  className={`authx__input${errors.email ? ' authx__input--error' : ''}`}
                  id="auth-new-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'auth-new-email-err' : undefined}
                />
                {errors.email && (
                  <p className="authx__error" id="auth-new-email-err" role="alert">
                    {errors.email}
                  </p>
                )}
              </div>

              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-new-password">
                  Password
                </label>
                <div className={`authx__control${errors.password ? ' authx__control--error' : ''}`}>
                  <input
                    className="authx__control-input"
                    id="auth-new-password"
                    name="new-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    placeholder="At least 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={errors.password ? 'auth-new-password-err' : undefined}
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
                {errors.password && (
                  <p className="authx__error" id="auth-new-password-err" role="alert">
                    {errors.password}
                  </p>
                )}
              </div>

              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-confirm">
                  Confirm password
                </label>
                <input
                  className={`authx__input${errors.confirm ? ' authx__input--error' : ''}`}
                  id="auth-confirm"
                  name="confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder="Repeat your password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  aria-invalid={Boolean(errors.confirm)}
                  aria-describedby={errors.confirm ? 'auth-confirm-err' : undefined}
                />
                {errors.confirm && (
                  <p className="authx__error" id="auth-confirm-err" role="alert">
                    {errors.confirm}
                  </p>
                )}
              </div>

              <button className="authx__submit" type="submit">
                Create Account
              </button>

              <div className="authx__or" role="separator">
                <span>or continue with</span>
              </div>

              <div className="authx__socials">
                {SOCIALS.map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    className="authx__social"
                    aria-label={s.label}
                    title={s.label}
                    onClick={() => handleSocial(s.label)}
                  >
                    {s.svg}
                  </button>
                ))}
              </div>

              {notice && (
                <p className="authx__notice" role="status">
                  {notice}
                </p>
              )}

              <p className="authx__foot">
                Already have an account?{' '}
                <button type="button" className="authx__link" onClick={() => switchTab('signin')}>
                  Log in.
                </button>
              </p>
            </form>
          )}

          {stage === 'forgot-email' && (
            <form className="authx__form" onSubmit={handleSendOtp} noValidate>
              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-recovery-email">
                  Email
                </label>
                <input
                  className={`authx__input${errors.recoveryEmail ? ' authx__input--error' : ''}`}
                  id="auth-recovery-email"
                  name="recovery-email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@example.com"
                  value={recoveryEmail}
                  onChange={(e) => setRecoveryEmail(e.target.value)}
                  aria-invalid={Boolean(errors.recoveryEmail)}
                  aria-describedby={errors.recoveryEmail ? 'auth-recovery-err' : undefined}
                />
                {errors.recoveryEmail && (
                  <p className="authx__error" id="auth-recovery-err" role="alert">
                    {errors.recoveryEmail}
                  </p>
                )}
              </div>

              <button className="authx__submit" type="submit">
                Send OTP
              </button>

              <p className="authx__foot">
                <button type="button" className="authx__link" onClick={backToLogin}>
                  Back to Log In
                </button>
              </p>
            </form>
          )}

          {stage === 'forgot-otp' && (
            <form className="authx__form" onSubmit={handleVerifyOtp} noValidate>
              <div className="authx__field">
                <span className="authx__label" id="otp-label">
                  Verification code
                </span>
                <div
                  className="authx__otp"
                  role="group"
                  aria-labelledby="otp-label"
                  aria-describedby={errors.otp ? 'auth-otp-err' : undefined}
                  onPaste={handleOtpPaste}
                >
                  {otp.map((digit, i) => (
                    <input
                      key={i}
                      ref={(el) => {
                        otpRefs.current[i] = el
                      }}
                      className={`authx__otp-box${errors.otp ? ' authx__otp-box--error' : ''}`}
                      type="text"
                      inputMode="numeric"
                      autoComplete={i === 0 ? 'one-time-code' : 'off'}
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleOtpChange(i, e.target.value)}
                      onKeyDown={(e) => handleOtpKeyDown(i, e)}
                      aria-label={`Digit ${i + 1} of ${OTP_LEN}`}
                      aria-invalid={Boolean(errors.otp)}
                    />
                  ))}
                </div>
                {errors.otp && (
                  <p className="authx__error" id="auth-otp-err" role="alert">
                    {errors.otp}
                  </p>
                )}
              </div>

              <button className="authx__submit" type="submit">
                Verify OTP
              </button>

              {notice && (
                <p className="authx__notice" role="status">
                  {notice}
                </p>
              )}

              <p className="authx__foot authx__foot--split">
                <button
                  type="button"
                  className="authx__link"
                  onClick={handleResend}
                  disabled={cooldown > 0}
                >
                  {cooldown > 0 ? `Resend Code (${cooldown}s)` : 'Resend Code'}
                </button>
                <button type="button" className="authx__link" onClick={backToLogin}>
                  Back to Log In
                </button>
              </p>
            </form>
          )}

          {stage === 'reset-done' && (
            <div className="authx__form">
              <div className="authx__success" aria-hidden="true">
                <Icon name="check_circle" size={40} />
              </div>
              <button className="authx__submit" type="button" onClick={backToLogin}>
                Back to Log In
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
