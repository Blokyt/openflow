// Indicateur de chargement plein écran, partagé par le shell (App) et les
// providers (EntityContext) pour éviter la duplication du markup.
import PageLoader from './PageLoader';

export default function Spinner() {
  return <PageLoader fullScreen />;
}
