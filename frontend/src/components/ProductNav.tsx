import { Link } from "react-router-dom";

export function ProductNav() {
  return (
    <nav className="product-nav">
      <Link to="/" className="brand">
        Football Analytics
      </Link>
      <div className="nav-links">
        <Link to="/upload">Upload</Link>
        <Link to="/matches">Matches</Link>
      </div>
    </nav>
  );
}
