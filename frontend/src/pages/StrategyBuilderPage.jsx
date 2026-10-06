import StrategyBuilder from '../components/StrategyBuilder/StrategyBuilder.jsx'

/**
 * Strategy Builder page — single-page structured strategy creation.
 * Accessible at /studio/builder
 */
export default function StrategyBuilderPage() {
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head__text">
          <nav className="breadcrumb" aria-label="Breadcrumb">
            <a href="/studio">Studio</a>
            <span aria-hidden="true">/</span>
            <span>Strategy Builder</span>
          </nav>
          <h1 className="page-title">Strategy Builder</h1>
          <p className="page-lede">
            Create a trading strategy using a structured form. Configure market, style, indicators,
            conditions and risk — all on one page.
          </p>
        </div>
      </div>
      <StrategyBuilder />
    </div>
  )
}