import LandingPage from './LandingPage.jsx'

/**
 * Documentation — preserves the existing landing-page content verbatim.
 *
 * PAGE SPLIT ONLY: the "HOW IT WORKS / SYSTEM PIPELINE / CAPABILITIES /
 * THREAT MITIGATION / CORE INFRASTRUCTURE / DEVELOPER SETUP / SCOPE & INTENT /
 * TECH STACK" sections already written in LandingPage.jsx move here unchanged,
 * so the dashboard (/) can stay a quick overview. No text, number or workflow
 * is edited — this wrapper only re-homes the page under /docs.
 */
export default function DocsPage() {
  return <LandingPage />
}
