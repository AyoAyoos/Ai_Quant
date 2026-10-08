import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
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
  const { isAuthenticated, login, signup, verifySignupOtp, resendSignupOtp } = useAuth()
  const location = useLocation()

  const [tab, setTab] = useState('signup')
  const [stage, setStage] = useState('form')

  const [fullName, setFullName] = useState('')
  const [contact, setContact] = useState('+91 ')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [recoveryEmail, setRecoveryEmail] = useState('')
  const [signupEmail, setSignupEmail] = useState('')
  const [otp, setOtp] = useState(() => Array(OTP_LEN).fill(''))
  const [cooldown, setCooldown] = useState(0)
  const [notice, setNotice] = useState('')
  const [errors, setErrors] = useState({})
  const [authBusy, setAuthBusy] = useState(false)

  const headingRef = useRef(null)
  const otpRefs = useRef([])

  const redirectAfterAuth = () => {
    // Full reload, not a client-side navigate: every page holds user data in
    // useState initialized once on mount, so only a fresh boot guarantees no
    // stale state from a previous account survives the switch.
    window.location.assign(location.state?.from?.pathname || '/dashboard')
  }

  // Move screen-reader + keyboard focus to the new heading on every transition.
  useEffect(() => {
    headingRef.current?.focus?.()
  }, [tab, stage])

  // Resend-code cooldown ticker.
  useEffect(() => {
    if ((stage !== 'forgot-otp' && stage !== 'signup-otp') || cooldown <= 0) return undefined
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

  const handleSignIn = async (event) => {
    event.preventDefault()
    const next = {}
    if (!EMAIL_RE.test(email.trim())) next.email = 'Enter a valid email address.'
    if (!password) next.password = 'Enter your password.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    setAuthBusy(true)
    const result = await login(email.trim(), password)
    setAuthBusy(false)
    if (!result.ok) {
      setErrors({ form: result.message || 'Sign-in failed. Check your credentials.' })
      return
    }
    redirectAfterAuth()
  }

  const handleSignUp = async (event) => {
    event.preventDefault()
    const next = {}
    if (!fullName.trim()) next.fullName = 'Enter your full name.'
    if ((contact.match(/\d/g) || []).length < 12) next.contact = 'Enter a valid 10-digit mobile number.'
    if (!EMAIL_RE.test(email.trim())) next.email = 'Enter a valid email address.'
    if (password.length < 8) next.password = 'Use at least 8 characters.'
    if (confirm !== password) next.confirm = 'Passwords do not match.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    setAuthBusy(true)
    const result = await signup(email.trim(), password, fullName.trim())
    setAuthBusy(false)
    if (!result.ok) {
      setErrors({ form: result.message || 'Sign-up failed. Try again.' })
      return
    }
    if (result.session) {
      // Confirm-email OFF (or prototype): instant session, straight in.
      redirectAfterAuth()
      return
    }
    // Confirm-email ON: Supabase mailed a 6-digit OTP — stay on the page
    // and show the verification step instead of redirecting.
    setSignupEmail(email.trim())
    setOtp(Array(OTP_LEN).fill(''))
    setErrors({})
    setNotice('')
    setCooldown(0)
    setStage('signup-otp')
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

  const handleContactChange = (value) => {
    // Lock the +91 country prefix: if the user deletes into it, restore the
    // prefix and keep whatever digits they typed as the local number.
    if (!value.startsWith('+91')) {
      const digits = value.replace(/\D/g, '')
      const local = digits.startsWith('91') ? digits.slice(2) : digits
      setContact(local ? `+91 ${local}` : '+91 ')
      return
    }
    setContact(value)
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

  const handleVerifySignupOtp = async (event) => {
    event.preventDefault()
    if (otp.some((d) => !d)) {
      setErrors({ otp: 'Enter all 6 digits of the verification code.' })
      return
    }
    setAuthBusy(true)
    const result = await verifySignupOtp(signupEmail, otp.join(''))
    setAuthBusy(false)
    if (!result.ok) {
      setErrors({ otp: result.message || 'That code didn’t work. Check it and try again.' })
      return
    }
    redirectAfterAuth()
  }

  const handleResendSignupOtp = async () => {
    if (cooldown > 0) return
    setAuthBusy(true)
    const result = await resendSignupOtp(signupEmail)
    setAuthBusy(false)
    if (!result.ok) {
      setErrors({ otp: result.message || 'Could not resend the code. Try again.' })
      return
    }
    setOtp(Array(OTP_LEN).fill(''))
    setErrors({})
    setNotice('A new code was sent to your email.')
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
        : stage === 'signup-otp'
          ? 'Verify Your Email'
          : stage === 'reset-done'
            ? "You're Verified"
            : tab === 'signup'
              ? 'Create Account'
              : 'Sign In'

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
          {stage === 'signup-otp' && (
            <p className="authx__sub">
              We sent a 6-digit code to <strong>{signupEmail}</strong>. Enter
              it below to verify your account.
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

              {errors.form && (
                <p className="authx__error" role="alert">
                  {errors.form}
                </p>
              )}
              <button className="authx__submit" type="submit" disabled={authBusy}>
                {authBusy ? 'Signing In…' : 'Sign In'}
              </button>

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
                <label className="authx__label" htmlFor="auth-full-name">
                  Full Name
                </label>
                <input
                  className={`authx__input${errors.fullName ? ' authx__input--error' : ''}`}
                  id="auth-full-name"
                  name="full-name"
                  type="text"
                  autoComplete="name"
                  placeholder="John Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  aria-invalid={Boolean(errors.fullName)}
                  aria-describedby={errors.fullName ? 'auth-full-name-err' : undefined}
                />
                {errors.fullName && (
                  <p className="authx__error" id="auth-full-name-err" role="alert">
                    {errors.fullName}
                  </p>
                )}
              </div>

              <div className="authx__field">
                <label className="authx__label" htmlFor="auth-contact">
                  Contact Number
                </label>
                <input
                  className={`authx__input${errors.contact ? ' authx__input--error' : ''}`}
                  id="auth-contact"
                  name="contact"
                  type="tel"
                  autoComplete="tel"
                  placeholder="+91 98765 43210"
                  value={contact}
                  onChange={(e) => handleContactChange(e.target.value)}
                  aria-invalid={Boolean(errors.contact)}
                  aria-describedby={errors.contact ? 'auth-contact-err' : undefined}
                />
                {errors.contact && (
                  <p className="authx__error" id="auth-contact-err" role="alert">
                    {errors.contact}
                  </p>
                )}
              </div>

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

              {errors.form && (
                <p className="authx__error" role="alert">
                  {errors.form}
                </p>
              )}
              <button className="authx__submit" type="submit" disabled={authBusy}>
                {authBusy ? 'Creating Account…' : 'Create Account'}
              </button>

              <p className="authx__foot">
                Already have an account?{' '}
                <button type="button" className="authx__link" onClick={() => switchTab('signin')}>
                  Sign In
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

          {stage === 'signup-otp' && (
            <form className="authx__form" onSubmit={handleVerifySignupOtp} noValidate>
              <div className="authx__field">
                <span className="authx__label" id="signup-otp-label">
                  Verification code
                </span>
                <div
                  className="authx__otp"
                  role="group"
                  aria-labelledby="signup-otp-label"
                  aria-describedby={errors.otp ? 'auth-signup-otp-err' : undefined}
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
                  <p className="authx__error" id="auth-signup-otp-err" role="alert">
                    {errors.otp}
                  </p>
                )}
              </div>

              <button className="authx__submit" type="submit" disabled={authBusy}>
                {authBusy ? 'Verifying…' : 'Verify Account'}
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
                  onClick={handleResendSignupOtp}
                  disabled={cooldown > 0 || authBusy}
                >
                  {cooldown > 0 ? `Resend Code (${cooldown}s)` : 'Resend Code'}
                </button>
                <button
                  type="button"
                  className="authx__link"
                  onClick={() => {
                    setStage('form')
                    setErrors({})
                    setNotice('')
                  }}
                >
                  Back to Sign Up
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

      <div className="authx__panel authx__panel--art">
        <div className="art" aria-hidden="true">
          <svg className="art__quant" viewBox="0 0 600 760" preserveAspectRatio="xMidYMid slice">
            <defs>
              <linearGradient id="art-line" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stopColor="#F8B2B2" />
                <stop offset="1" stopColor="#AF719D" />
              </linearGradient>
              <linearGradient id="art-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#AF719D" stopOpacity="0.35" />
                <stop offset="1" stopColor="#AF719D" stopOpacity="0" />
              </linearGradient>
              <pattern id="art-grid" width="48" height="48" patternUnits="userSpaceOnUse">
                <path d="M48 0H0V48" fill="none" stroke="#8B639B" strokeOpacity="0.28" />
              </pattern>
            </defs>
            <rect x="0" y="0" width="600" height="760" fill="url(#art-grid)" />
            <path
              d="M0,560 C80,540 140,480 220,460 S380,380 460,300 S560,180 620,120 L620,760 L0,760 Z"
              fill="url(#art-area)"
            />
            <path
              d="M0,560 C80,540 140,480 220,460 S380,380 460,300 S560,180 620,120"
              fill="none"
              stroke="url(#art-line)"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <path
              d="M0,620 C120,600 240,620 360,560 S520,500 620,460"
              fill="none"
              stroke="#8B639B"
              strokeWidth="2.5"
              strokeDasharray="8 8"
              strokeOpacity="0.8"
            />
            <g>
              <circle cx="220" cy="460" r="7" fill="#F8B2B2" />
              <circle cx="220" cy="460" r="14" fill="none" stroke="#F8B2B2" strokeOpacity="0.5" />
              <circle cx="380" cy="376" r="7" fill="#F8B2B2" />
              <circle cx="380" cy="376" r="14" fill="none" stroke="#F8B2B2" strokeOpacity="0.5" />
              <circle cx="500" cy="252" r="8" fill="#AF719D" />
              <circle cx="500" cy="252" r="16" fill="none" stroke="#AF719D" strokeOpacity="0.5" />
              <line x1="220" y1="460" x2="380" y2="376" stroke="#F8B2B2" strokeOpacity="0.45" />
              <line x1="380" y1="376" x2="500" y2="252" stroke="#F8B2B2" strokeOpacity="0.45" />
              <line x1="220" y1="460" x2="220" y2="640" stroke="#8B639B" strokeOpacity="0.5" strokeDasharray="4 5" />
              <line x1="380" y1="376" x2="380" y2="640" stroke="#8B639B" strokeOpacity="0.5" strokeDasharray="4 5" />
              <line x1="500" y1="252" x2="500" y2="640" stroke="#8B639B" strokeOpacity="0.5" strokeDasharray="4 5" />
            </g>
            <g opacity="0.9">
              <rect x="60" y="600" width="18" height="44" rx="4" fill="#F8B2B2" opacity="0.85" />
              <rect x="86" y="584" width="18" height="60" rx="4" fill="#8B639B" />
              <rect x="112" y="610" width="18" height="34" rx="4" fill="#F8B2B2" opacity="0.85" />
              <rect x="138" y="576" width="18" height="68" rx="4" fill="#F8B2B2" opacity="0.85" />
              <rect x="164" y="596" width="18" height="48" rx="4" fill="#8B639B" />
              <rect x="410" y="580" width="18" height="64" rx="4" fill="#F8B2B2" opacity="0.85" />
              <rect x="436" y="604" width="18" height="40" rx="4" fill="#8B639B" />
              <rect x="462" y="570" width="18" height="74" rx="4" fill="#F8B2B2" opacity="0.85" />
              <rect x="488" y="594" width="18" height="50" rx="4" fill="#8B639B" />
            </g>
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

          <div className="art__engine">
            <span className="art__engine-label">AI Strategy Engine</span>
            <span className="art__engine-formula">Sharpe = (Rₚ − Rƒ) / σₚ · RSI-14 · MACD · SMA-200</span>
            <span className="art__engine-sub">Backtest · Analyse · Paper Trade</span>
          </div>

          <span className="art__orb art__orb--a" />
          <span className="art__orb art__orb--b" />
          <span className="art__ring" />
        </div>
      </div>
    </div>
  )
}
