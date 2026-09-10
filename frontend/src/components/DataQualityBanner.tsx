export function DataQualityBanner({ message }: { message: string }) {
  return (
    <aside className="panel banner" role="status">
      {message}
    </aside>
  );
}
