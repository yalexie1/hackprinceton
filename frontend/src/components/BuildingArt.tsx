export default function BuildingArt({
  office = false,
  compact = false,
}: {
  office?: boolean;
  compact?: boolean;
}) {
  return (
    <svg
      className={`building-art ${compact ? "compact" : ""}`}
      viewBox="0 0 680 430"
      role="img"
      aria-label={
        office
          ? "Illustration of an office building with rooftop solar"
          : "Illustration of a house with rooftop solar"
      }
    >
      <defs>
        <linearGradient id={office ? "wall-o" : "wall-h"} x2=".3" y2="1">
          <stop stopColor="#eee9d9" />
          <stop offset="1" stopColor="#d1d1bd" />
        </linearGradient>
        <pattern
          id={office ? "grid-o" : "grid-h"}
          width="38"
          height="22"
          patternUnits="userSpaceOnUse"
          patternTransform="skewY(-27)"
        >
          <path
            d="M38 0H0V22"
            fill="none"
            stroke="#b3c2ae"
            strokeOpacity=".23"
          />
        </pattern>
        <linearGradient id={office ? "pane-o" : "pane-h"} x2="1" y2="1">
          <stop stopColor="#608484" />
          <stop offset="1" stopColor="#244d51" />
        </linearGradient>
      </defs>
      <rect width="680" height="430" fill={office ? "#e2e7db" : "#e6eade"} />
      <rect
        width="680"
        height="430"
        fill={`url(#${office ? "grid-o" : "grid-h"})`}
      />
      <ellipse
        cx="361"
        cy="350"
        rx="238"
        ry="51"
        fill="#b1bca5"
        opacity=".35"
      />
      <path d="m97 297 294-158 233 131-294 158Z" fill="#c7d3bc" />
      <path d="m124 288 267-142 207 116-268 146Z" fill="#d7dfcb" />
      <path
        d="m195 237 187-100 157 89v105l-188 99-156-90Z"
        fill={`url(#${office ? "wall-o" : "wall-h"})`}
        transform="translate(0 -36)"
      />
      <path d="m195 201 156 89v104l-156-90Z" fill="#d3d3bf" />
      <path d="m351 290 188-100v105l-188 99Z" fill="#eeeddf" />
      {office ? (
        <>
          <path d="m180 199 199-107 177 99-200 108Z" fill="#667366" />
          <path d="m180 199 176 100v13l-176-99Z" fill="#4c6055" />
          <path d="m356 299 200-108v13L356 312Z" fill="#76836d" />
          {[0, 1, 2, 3].map((i) => (
            <g key={i}>
              <path
                d={`m${211 + i * 32} ${231 + i * 18} 22 12v44l-22-12Z`}
                fill="#477274"
              />
              <path
                d={`m${374 + i * 38} ${305 - i * 20} 26-14v43l-26 14Z`}
                fill="#477274"
              />
            </g>
          ))}
        </>
      ) : (
        <>
          <path d="m175 206 86-122 140 80-49 128Z" fill="#667567" />
          <path d="m261 84 177 17 117 96-154-33Z" fill="#7b8971" />
          <path
            d="m352 292 49-128 154 33-16 18-139-29-36 111Z"
            fill="#4e6558"
          />
          <path d="m195 201 66-95 122 71-32 113Z" fill="#687663" />
          <path d="m239 232 55 31v54l-55-31Z" fill="url(#pane-h)" />
          <path d="m239 258 55 31m-28-42v54" stroke="#e5e7d6" strokeWidth="3" />
          <path d="m392 290 45-24v56l-45 24Z" fill="url(#pane-h)" />
          <path d="m466 251 44-23v56l-44 24Z" fill="url(#pane-h)" />
          <path d="m414 278v56m74-95v56" stroke="#e3e8d5" strokeWidth="3" />
        </>
      )}
      <g transform={office ? "translate(35 -5)" : "translate(0 0)"}>
        {[0, 1, 2].map((i) => (
          <g key={i}>
            {[0, 1].map((j) => (
              <g key={j}>
                <path
                  d={`m${238 + i * 33 + j * 17} ${142 + i * 19 - j * 24} 29 17-14 20-29-17Z`}
                  fill="#254c54"
                  stroke="#9fb9ad"
                  strokeWidth="1.5"
                />
                <path
                  d={`m${245 + i * 33 + j * 17} ${151 + i * 19 - j * 24} 15 9m-13-14-7 10`}
                  fill="none"
                  stroke="#6d9697"
                  strokeWidth=".6"
                />
              </g>
            ))}
          </g>
        ))}
      </g>
      <path d="m393 378 84-44 44 25-84 44Z" fill="#b9c3ad" />
      <g>
        <path d="M137 283v-89" stroke="#708168" strokeWidth="8" />
        <ellipse cx="137" cy="185" rx="35" ry="51" fill="#91a484" />
        <ellipse cx="126" cy="174" rx="25" ry="36" fill="#a5b591" />
        <path d="M571 315v-73" stroke="#708168" strokeWidth="7" />
        <ellipse cx="571" cy="232" rx="29" ry="44" fill="#789773" />
        <ellipse cx="561" cy="221" rx="20" ry="30" fill="#91a986" />
      </g>
      <g fill="#728b66">
        <ellipse cx="190" cy="326" rx="22" ry="13" />
        <ellipse cx="214" cy="341" rx="20" ry="12" />
        <ellipse cx="527" cy="324" rx="22" ry="13" />
      </g>
      <g
        transform="translate(555 46)"
        stroke="#5e7563"
        strokeWidth="1.3"
        fill="none"
      >
        <circle r="21" />
        <path d="M0-14V14m-5-9 5 9 5-9" />
      </g>
      <text x="551" y="20" fill="#5e7563" fontSize="10" fontFamily="sans-serif">
        N
      </text>
    </svg>
  );
}
