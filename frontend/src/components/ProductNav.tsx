import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function ProductNav() {
  const { user, ready, logout } = useAuth();
  return (
    <nav className="product-nav">
      <Link to="/" className="brand">
        Football Analytics
      </Link>
      <div className="nav-links">
        {ready && user ? (
          <>
            <Link to="/upload">Upload</Link>
            <Link to="/matches">Matches</Link>
            <span className="nav-user">{user.name || user.email}</span>
            <button className="link-btn" type="button" onClick={logout}>
              Log out
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Sign in</Link>
            <Link to="/signup">Create account</Link>
          </>
        )}
      </div>
    </nav>
  );
}
