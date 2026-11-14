/**
 * The Leto mark: the sun over a roofline.
 *
 * Leto is Apollo's mother, and Apollo is the sun - which is also the product, since the plan
 * ends by sizing solar to the energy a building still needs after everything cheaper is done.
 * It replaces a generic cube icon that said nothing about either.
 *
 * Drawn on a 24-unit grid with `currentColor` and the same 1.7 stroke as the icon set it sits
 * beside, so it inherits the brand mark's colour and lines up with the rest of the sidebar.
 * The geometry is deliberately coarse: it has to stay legible at 23px in the sidebar and at
 * favicon size, where a finer sun would turn into a smudge.
 */
export default function LetoMark({
  size = 23,
  strokeWidth = 1.7,
}: {
  size?: number;
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* the sun */}
      <circle cx="12" cy="7.4" r="3.1" />
      <path d="M12 1.7v1.2M12 11.9v1.2M6.6 7.4H5.4M18.6 7.4h-1.2M8.2 3.6l.85.85M15.8 3.6l-.85.85" />
      {/* the roof it falls on */}
      <path d="M3 19.4 12 13l9 6.4" />
      <path d="M5.6 17.6v4.7h12.8v-4.7" />
    </svg>
  );
}
