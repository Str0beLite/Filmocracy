// Dev-only: step through screens while nothing is wired to the backend.
// Hidden in production builds.

import { Link, useLocation, useNavigate } from 'react-router';
import { ChevronLeft, ChevronRight, LayoutGrid } from 'lucide-react';
import { nextPath } from '../lib/flow';

export function DevBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  if (!import.meta.env.DEV) return null;
  return (
    <nav className="devbar" aria-label="Dev screen controls">
      <button onClick={() => navigate(-1)} aria-label="Previous screen">
        <ChevronLeft aria-hidden="true" />
      </button>
      <button onClick={async () => navigate(await nextPath(pathname))} aria-label="Next screen">
        <ChevronRight aria-hidden="true" />
      </button>
      <Link to="/" aria-label="All screens">
        <LayoutGrid aria-hidden="true" />
      </Link>
    </nav>
  );
}
