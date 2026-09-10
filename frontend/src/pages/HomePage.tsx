import { Link } from "react-router-dom";
import { ProductNav } from "../components/ProductNav";

export function HomePage() {
  return (
    <div className="app">
      <ProductNav />
      <section className="hero panel">
        <div className="kicker">Football Analytics</div>
        <h1>Turn your match footage into football intelligence.</h1>
        <p className="hero-copy">
          Upload a match, run the analytics pipeline, and read possession, passing,
          turnovers, and shooting on a professional dashboard.
        </p>
        <div className="hero-actions">
          <Link className="btn primary" to="/upload">
            Upload Match Video
          </Link>
          <Link className="btn ghost" to="/matches">
            View Previous Matches
          </Link>
        </div>
      </section>
    </div>
  );
}
