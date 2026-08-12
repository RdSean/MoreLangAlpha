import { Link } from 'react-router-dom';

function Legal() {
  return (
    <div
      className="h-screen overflow-y-auto py-12 px-4 sm:px-6 lg:px-8"
      style={{ backgroundColor: 'var(--color-bg-page)', color: 'var(--color-text-primary)' }}
    >
      <article className="mx-auto max-w-3xl">
        <header className="mb-10 border-b pb-6" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <Link
            to="/"
            className="text-sm hover:underline"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            &larr; Back to LangAlpha
          </Link>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Legal &amp; Attribution</h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Open-source licenses and third-party credits for the hosted LangAlpha service.
          </p>
        </header>

        <div className="space-y-10 text-base leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold tracking-tight mb-3">Other credits</h2>
            <p>
              LangAlpha is built on React, Vite, FastAPI, PostgreSQL, Redis, and many
              other open-source projects. The complete list of dependencies and their
              licenses is available in the{' '}
              <a
                href="https://github.com/ginlix/langalpha"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                langalpha repository
              </a>
              .
            </p>
            <p className="mt-3 text-sm">
              See also our{' '}
              <Link to="/privacy" className="underline">
                Privacy Policy
              </Link>
              .
            </p>
          </section>
        </div>
      </article>
    </div>
  );
}

export default Legal;
