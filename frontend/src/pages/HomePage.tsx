import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ProductNav } from "../components/ProductNav";

export function HomePage() {
  const { user } = useAuth();
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
          <Link className="btn primary" to={user ? "/upload" : "/signup"}>
            {user ? "Upload Match Video" : "Create account"}
          </Link>
          <Link className="btn ghost" to={user ? "/matches" : "/login"}>
            {user ? "View Previous Matches" : "Sign in"}
          </Link>
        </div>
      </section>
    </div>
  );
}
