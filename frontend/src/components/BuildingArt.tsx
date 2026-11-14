import HouseViewer from "./HouseViewer";

// Property-card previews share the model without nesting interactive controls.
export default function BuildingArt({
  office = false,
}: {
  office?: boolean;
  compact?: boolean;
}) {
  return <HouseViewer office={office} compact />;
}
