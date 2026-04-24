export default function AssetPreviewPanel({ artifacts }) {
  const assets = artifacts?.visual_assets_bundle?.assets ?? [];

  const viewItems = assets.map((asset) => ({
    id: asset.asset_id,
    type: String(asset.type ?? "unknown").toUpperCase(),
    label: `${asset.asset_id}${Number.isInteger(asset.slide_index) ? ` (slide ${asset.slide_index})` : ""}`
  }));

  return (
    <article className="card">
      <h3>Assets</h3>
      <ul className="assets">
        {viewItems.length === 0 && (
          <li className="asset">
            <span>No assets yet</span>
            <span className="type">-</span>
          </li>
        )}
        {viewItems.map((item) => (
          <li key={item.id} className="asset">
            <span>{item.label}</span>
            <span className="type">{item.type}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
