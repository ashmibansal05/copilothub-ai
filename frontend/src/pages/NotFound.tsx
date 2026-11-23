import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-5xl font-extrabold text-brand-600">404</p>
      <h1 className="text-xl font-bold">This page does not exist</h1>
      <Link to="/dashboard" className="btn-primary">Go to the dashboard</Link>
    </div>
  );
}