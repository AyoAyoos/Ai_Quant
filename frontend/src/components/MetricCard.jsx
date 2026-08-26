function MetricCard({ label, value, change, type }) {
  return (
    <div className="metric-card">
      <div className="metric-header">
        <span>{label}</span>
        <span className={`metric-indicator ${type || ""}`}>●</span>
      </div>

      <h3>{value}</h3>

      {change && (
        <p className={type === "danger" ? "negative" : "positive"}>
          {change}
        </p>
      )}
    </div>
  );
}

export default MetricCard;