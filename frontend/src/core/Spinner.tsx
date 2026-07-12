// Indicateur de chargement plein écran, partagé par le shell (App) et les
// providers (EntityContext) pour éviter la duplication du markup.
export default function Spinner() {
  return (
    <div className="flex items-center justify-center h-screen bg-black">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
    </div>
  );
}
