import { Bot, GitMerge, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router-dom";
import ApiStatus from "../components/ApiStatus";
import { useAuth } from "../contexts/AuthContext";

const features = [
  {
    icon: Users,
    title: "Shared agent sessions",
    text: "Several people watch and steer the same running AI agent in real time.",
  },
  {
    icon: GitMerge,
    title: "Structured interventions",
    text: "Feedback like “don't use Wikipedia” becomes an active constraint the agent obeys.",
  },
  {
    icon: ShieldCheck,
    title: "Human approval & safety",
    text: "Conflicts are surfaced to people, and key actions wait for explicit approval.",
  },
];

export default function Landing() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <span className="flex items-center gap-2 text-lg font-bold">
          <Bot className="h-7 w-7 text-brand-600" /> CoPilotHub AI
        </span>
        <div className="flex items-center gap-2">
          {user ? (
            <Link to="/dashboard" className="btn-primary">Dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="btn-secondary">Log in</Link>
              <Link to="/register" className="btn-primary">Get started</Link>
            </>
          )}
        </div>
      </nav>

      <section className="mx-auto max-w-4xl px-4 py-20 text-center">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
          Control AI agents <span className="text-brand-600">together</span>, while they work
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600">
          A collaborative human-in-the-loop platform where teams guide long-running AI agents
          with structured, auditable interventions.
        </p>
        <div className="mt-8 flex justify-center">
          <ApiStatus />
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-5 px-4 pb-20 sm:grid-cols-3">
        {features.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <Icon className="h-6 w-6 text-brand-600" />
            <h3 className="mt-3 font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-slate-600">{text}</p>
          </div>
        ))}
      </section>
    </div>
  );
}