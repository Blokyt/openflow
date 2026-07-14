// Composant de chargement partagé avec support inline et plein écran.
// Utilisé par les routes suspendues (React Suspense) et les chargements de données.

interface PageLoaderProps {
  /** If true, renders as a full-page centered loader. Otherwise renders inline. */
  fullScreen?: boolean;
  /** Optional text to display below the spinner. */
  message?: string;
}

export default function PageLoader({ fullScreen = true, message }: PageLoaderProps) {
  const containerClass = fullScreen
    ? "flex flex-col items-center justify-center h-screen bg-black"
    : "flex flex-col items-center justify-center py-12";

  return (
    <div className={containerClass}>
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent-sand" />
      {message && (
        <p className="mt-4 text-sm text-text-secondary">{message}</p>
      )}
    </div>
  );
}
